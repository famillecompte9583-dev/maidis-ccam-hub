#!/usr/bin/env python3
"""Intégration des catalogues/API publiques utiles au site.

Ce script complète les dossiers de veille avec des sources techniques fiables :
- catalogue open source api.gouv.fr depuis GitHub ;
- API data.gouv.fr datasets/dataservices ;
- API FHIR Annuaire Santé et endpoints documentés par l'ANS ;
- point d'entrée MCP data.gouv.fr pour futures recherches IA.

Il n'utilise pas de scraping anti-bot : uniquement GitHub raw/API, API publiques
ou endpoints documentés. Les résultats sont ajoutés à app-data.json dans :
- public_api_sources : catalogue affichable ;
- articles : dossiers techniques relisibles par Gemini.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
from typing import Any
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APP_PATH = DATA_DIR / "app-data.json"
STATUS_PATH = DATA_DIR / "sync-status.json"
PARIS = ZoneInfo("Europe/Paris")

MAX_API_GOUV_FILES = 260
MAX_CATALOG_ITEMS = 36
MAX_DATA_GOUV_ITEMS = 18
SOURCE_TEXT_LIMIT = 24000

HEALTH_TERMS = [
    "sante", "santé", "medical", "médical", "medicament", "médicament", "fhir",
    "annuaire-sante", "annuaire santé", "assurance maladie", "remboursement", "ccam",
    "pmsi", "atih", "scan sante", "scansante", "professionnel de santé", "professionnels de santé",
    "drees", "ir-desir", "snir", "terminologie", "terminologies de santé", "ans", "esante",
]

API_GOUV_CONTENTS = "https://api.github.com/repos/betagouv/api.gouv.fr/contents/_data/api?ref=master"
DATA_GOUV_DATASETS = "https://www.data.gouv.fr/api/1/datasets/?q={query}&page_size=6"
DATA_GOUV_DATASERVICES = "https://www.data.gouv.fr/api/1/dataservices/?q={query}&page_size=6"
MCP_ENDPOINT = "https://mcp.data.gouv.fr/mcp"
FHIR_BASE = "https://gateway.api.esante.gouv.fr/fhir/v2"
FHIR_ENDPOINTS = [
    "metadata",
    "Practitioner",
    "PractitionerRole",
    "Organization",
    "HealthcareService",
    "Device",
]

KNOWN_PUBLIC_APIS = [
    {
        "id": "annuaire-sante-fhir",
        "title": "API FHIR Annuaire Santé",
        "provider": "Agence du Numérique en Santé",
        "category": "FHIR / Annuaire Santé",
        "url": "https://github.com/ansforge/annuaire-sante-fhir-documentation",
        "doc_url": "https://ansforge.github.io/annuaire-sante-fhir-documentation/",
        "api_url": f"{FHIR_BASE}/metadata",
        "summary": "API REST FHIR R4 permettant de consulter en JSON les données publiques de l’Annuaire Santé : Practitioner, PractitionerRole, Organization, HealthcareService, Device.",
        "use_case": "Enrichir le site avec une rubrique sources/API et, plus tard, rechercher des structures ou services de santé sans dépendre d'un scraping HTML.",
    },
    {
        "id": "datagouv-mcp",
        "title": "Serveur MCP data.gouv.fr",
        "provider": "data.gouv.fr",
        "category": "MCP / Open Data",
        "url": "https://github.com/datagouv/datagouv-mcp",
        "doc_url": "https://github.com/datagouv/datagouv-mcp",
        "api_url": MCP_ENDPOINT,
        "summary": "Serveur MCP officiel pour rechercher, explorer et analyser les jeux de données de data.gouv.fr avec un assistant IA.",
        "use_case": "Préparer une veille augmentée par IA : découverte de datasets santé, assurance maladie, PMSI, OpenCCAM, médicaments, terminologies.",
    },
    {
        "id": "api-gouv-catalogue",
        "title": "Catalogue api.gouv.fr",
        "provider": "DINUM / beta.gouv",
        "category": "Catalogue API publiques",
        "url": "https://github.com/betagouv/api.gouv.fr",
        "doc_url": "https://api.gouv.fr/",
        "api_url": API_GOUV_CONTENTS,
        "summary": "Catalogue open source des API produites par les administrations, avec description, documentation technique et modalités d'accès.",
        "use_case": "Découvrir automatiquement des API santé pertinentes et maintenir une liste de sources techniques fiable pour le site.",
    },
]


def now_fr() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS).isoformat(timespec="seconds")


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def slugify(text: str) -> str:
    replacements = str.maketrans("éèêëàâäçîïôöùûüÿñ", "eeeeaaaciioouuuyn")
    text = text.lower().translate(replacements)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:90] or "source-api"


def load_app() -> dict[str, Any]:
    if not APP_PATH.exists() or APP_PATH.stat().st_size == 0:
        raise SystemExit("data/app-data.json absent ou vide")
    return json.loads(APP_PATH.read_text(encoding="utf-8"))


def save_app(app: dict[str, Any]) -> None:
    APP_PATH.write_text(json.dumps(app, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "app-data.js").write_text("window.CCAM_APP_DATA = " + json.dumps(app, ensure_ascii=False) + ";\n", encoding="utf-8")


def update_status(status: str, details: dict[str, Any]) -> None:
    if STATUS_PATH.exists() and STATUS_PATH.stat().st_size:
        try:
            payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    else:
        payload = {}
    payload["public_api_sources"] = {"status": status, "generated": now_fr(), **details}
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_json(url: str, timeout: int = 35) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, application/vnd.github+json, */*;q=0.5",
            "User-Agent": "maidis-ccam-hub/1.0 (+https://github.com/famillecompte9583-dev/maidis-ccam-hub)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def fetch_text(url: str, timeout: int = 35) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "text/plain, text/markdown, text/html, application/json, */*;q=0.5",
            "User-Agent": "maidis-ccam-hub/1.0 (+https://github.com/famillecompte9583-dev/maidis-ccam-hub)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def compact_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def is_health_related(text: str) -> bool:
    low = text.lower()
    return any(term in low for term in HEALTH_TERMS)


def parse_front_matter(markdown: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return data
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            data[key] = value
    return data


def first_non_empty(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def api_gouv_catalog() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    out: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    try:
        files = fetch_json(API_GOUV_CONTENTS)
        if not isinstance(files, list):
            raise ValueError("réponse GitHub inattendue")
    except Exception as exc:
        return [], [{"source": "api.gouv.fr GitHub contents", "error": f"{type(exc).__name__}: {exc}"}]

    for file_info in files[:MAX_API_GOUV_FILES]:
        try:
            name = file_info.get("name", "")
            download_url = file_info.get("download_url", "")
            if not name.endswith(".md") or not download_url:
                continue
            quick = f"{name} {download_url}"
            if not is_health_related(quick):
                # on évite de télécharger tout le catalogue quand le nom n'a aucun signal santé.
                continue
            raw = fetch_text(download_url)
            if not is_health_related(raw):
                continue
            meta = parse_front_matter(raw)
            title = first_non_empty(meta.get("title"), meta.get("name"), name.replace(".md", "").replace("api-", "API "))
            summary = compact_text(first_non_empty(meta.get("tagline"), meta.get("description"), raw[:900]))[:700]
            doc = first_non_empty(meta.get("doc_tech_link"), meta.get("doc_tech_external"), meta.get("external_site"), meta.get("link"), download_url)
            access = first_non_empty(meta.get("is_open"), meta.get("access"), meta.get("account_link"), meta.get("datapass_link"), "à vérifier dans la fiche api.gouv.fr")
            out.append({
                "id": f"api-gouv-{slugify(title)}",
                "title": title,
                "provider": first_non_empty(meta.get("producer"), "api.gouv.fr"),
                "category": "Catalogue api.gouv.fr",
                "url": download_url,
                "doc_url": doc,
                "api_url": doc,
                "summary": summary or "Fiche API publique référencée par api.gouv.fr et détectée comme pertinente pour le domaine santé.",
                "access": access,
                "source_kind": "github-api-gouv-catalog",
                "source_text_excerpt": compact_text(raw[:SOURCE_TEXT_LIMIT]),
            })
            if len(out) >= MAX_CATALOG_ITEMS:
                break
            time.sleep(0.15)
        except Exception as exc:
            errors.append({"source": file_info.get("name", "api.gouv.fr"), "error": f"{type(exc).__name__}: {exc}"})
    return out, errors


def data_gouv_search() -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    queries = [
        "santé remboursement",
        "CCAM actes médicaux",
        "médicaments remboursement",
        "PMSI MCO OpenCCAM",
        "terminologies de santé",
        "annuaire santé FHIR",
    ]
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for query in queries:
        encoded = urllib.parse.quote(query)
        for template, kind in [(DATA_GOUV_DATASETS, "dataset"), (DATA_GOUV_DATASERVICES, "dataservice")]:
            url = template.format(query=encoded)
            try:
                payload = fetch_json(url)
                results = payload.get("data", []) if isinstance(payload, dict) else []
                for item in results:
                    title = first_non_empty(item.get("title"), item.get("name"), item.get("slug"), query)
                    page = first_non_empty(item.get("page"), item.get("uri"), item.get("url"), item.get("self_web_url"))
                    if not page and item.get("slug"):
                        page = f"https://www.data.gouv.fr/fr/datasets/{item.get('slug')}/" if kind == "dataset" else f"https://www.data.gouv.fr/fr/dataservices/{item.get('slug')}/"
                    description = compact_text(first_non_empty(item.get("description"), item.get("tagline"), item.get("acronym"), ""))[:900]
                    key = page or title
                    if key in seen:
                        continue
                    text = f"{title} {description} {query}"
                    if not is_health_related(text):
                        continue
                    seen.add(key)
                    items.append({
                        "id": f"data-gouv-{slugify(title)}",
                        "title": title,
                        "provider": "data.gouv.fr",
                        "category": "data.gouv.fr " + kind,
                        "url": page or "https://www.data.gouv.fr/",
                        "doc_url": page or "https://www.data.gouv.fr/",
                        "api_url": url,
                        "summary": description or f"Résultat data.gouv.fr détecté pour la requête : {query}.",
                        "access": "open data ou modalités précisées sur data.gouv.fr",
                        "source_kind": f"data-gouv-{kind}",
                        "source_text_excerpt": description or title,
                    })
                    if len(items) >= MAX_DATA_GOUV_ITEMS:
                        return items, errors
                time.sleep(0.2)
            except Exception as exc:
                errors.append({"source": f"data.gouv.fr {kind} {query}", "error": f"{type(exc).__name__}: {exc}"})
    return items, errors


def check_url(url: str, expect_json: bool = False) -> tuple[str, str]:
    try:
        if expect_json:
            payload = fetch_json(url, timeout=20)
            if isinstance(payload, dict):
                label = first_non_empty(payload.get("resourceType"), payload.get("software", {}).get("name") if isinstance(payload.get("software"), dict) else "", "json ok")
                return "ok", label
            return "ok", "json reçu"
        text = fetch_text(url, timeout=20)
        return "ok", compact_text(text[:240])
    except Exception as exc:
        return "warning", f"{type(exc).__name__}: {exc}"


def known_sources_with_status() -> list[dict[str, Any]]:
    out = []
    for item in KNOWN_PUBLIC_APIS:
        status, detail = check_url(item["api_url"], expect_json=item["id"] == "annuaire-sante-fhir")
        clone = {**item, "live_status": status, "live_detail": detail, "source_kind": "known-public-api"}
        if item["id"] == "annuaire-sante-fhir":
            endpoints = []
            for endpoint in FHIR_ENDPOINTS:
                endpoint_url = f"{FHIR_BASE}/{endpoint}" if endpoint != "metadata" else f"{FHIR_BASE}/metadata"
                ep_status, ep_detail = check_url(endpoint_url, expect_json=True)
                endpoints.append({"name": endpoint, "url": endpoint_url, "status": ep_status, "detail": ep_detail[:180]})
                time.sleep(0.12)
            clone["endpoints"] = endpoints
        out.append(clone)
    return out


def source_to_html(source: dict[str, Any]) -> str:
    endpoints = source.get("endpoints") or []
    endpoint_html = ""
    if endpoints:
        endpoint_html = "<h2>Endpoints contrôlés</h2><ul>" + "".join(
            f"<li><strong>{esc(ep.get('name'))}</strong> — {esc(ep.get('status'))} — <a href=\"{esc(ep.get('url'))}\" target=\"_blank\" rel=\"noopener noreferrer\">endpoint</a></li>"
            for ep in endpoints
        ) + "</ul>"
    return "".join([
        f"<p>Cette fiche source est générée automatiquement pour documenter une API ou un catalogue exploitable par l'annuaire.</p>",
        "<h2>Utilité pour le site</h2>",
        f"<p>{esc(source.get('use_case') or source.get('summary') or '')}</p>",
        "<h2>Source et accès</h2>",
        "<ul>",
        f"<li><strong>Fournisseur :</strong> {esc(source.get('provider'))}</li>",
        f"<li><strong>Catégorie :</strong> {esc(source.get('category'))}</li>",
        f"<li><strong>Accès :</strong> {esc(source.get('access') or 'à vérifier dans la documentation officielle')}</li>",
        f"<li><strong>État de contrôle :</strong> {esc(source.get('live_status') or 'non contrôlé')} {esc(source.get('live_detail') or '')}</li>",
        "</ul>",
        endpoint_html,
        "<h2>Liens utiles</h2>",
        "<ul>",
        f"<li><a href=\"{esc(source.get('url'))}\" target=\"_blank\" rel=\"noopener noreferrer\">Page source</a></li>",
        f"<li><a href=\"{esc(source.get('doc_url') or source.get('url'))}\" target=\"_blank\" rel=\"noopener noreferrer\">Documentation</a></li>",
        f"<li><a href=\"{esc(source.get('api_url') or source.get('url'))}\" target=\"_blank\" rel=\"noopener noreferrer\">Endpoint ou référence technique</a></li>",
        "</ul>",
    ])


def make_articles_from_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    articles = []
    for source in sources[:18]:
        title = source.get("title") or "Source API publique"
        source_text = "\n".join([
            f"Titre : {title}",
            f"Fournisseur : {source.get('provider', '')}",
            f"Catégorie : {source.get('category', '')}",
            f"Résumé : {source.get('summary', '')}",
            f"Cas d'usage : {source.get('use_case', '')}",
            f"Accès : {source.get('access', '')}",
            f"URL : {source.get('url', '')}",
            f"Documentation : {source.get('doc_url', '')}",
            f"Endpoint : {source.get('api_url', '')}",
            f"État : {source.get('live_status', '')} {source.get('live_detail', '')}",
            source.get("source_text_excerpt", ""),
        ])[:SOURCE_TEXT_LIMIT]
        articles.append({
            "id": "source-" + slugify(title),
            "title": title,
            "date": dt.date.today().isoformat(),
            "source": source.get("provider") or "Source API publique",
            "source_url": source.get("url") or source.get("doc_url") or source.get("api_url"),
            "category": "Sources & API",
            "tag": "Sources & API",
            "summary": source.get("summary") or "Source technique détectée pour enrichir la veille et les dossiers du site.",
            "content_html": source_to_html(source),
            "codes": [],
            "codes_detectes": [],
            "extracted_chars": len(source_text),
            "source_text_excerpt": source_text,
            "confidence": "Haute" if source.get("live_status") == "ok" else "Moyenne",
            "generation": {
                "mode": "public-api-catalog-integration",
                "generated": now_fr(),
                "grounding": "api_gouv_github_data_gouv_rest_ans_fhir_mcp_metadata",
            },
        })
    return articles


def merge_articles(existing: list[dict[str, Any]], additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {article.get("id"): article for article in existing if isinstance(article, dict) and article.get("id")}
    for article in additions:
        by_id[article["id"]] = article
    return list(by_id.values())


def main() -> None:
    app = load_app()
    known = known_sources_with_status()
    api_gouv, api_errors = api_gouv_catalog()
    data_gouv, data_errors = data_gouv_search()
    sources = []
    seen = set()
    for source in known + api_gouv + data_gouv:
        key = source.get("id") or source.get("url") or source.get("title")
        if key in seen:
            continue
        seen.add(key)
        sources.append(source)

    app["public_api_sources"] = sources
    api_articles = make_articles_from_sources(sources)
    app["articles"] = merge_articles(app.get("articles", []), api_articles)
    app.setdefault("meta", {})["public_api_sources"] = {
        "generated": now_fr(),
        "total": len(sources),
        "known": len(known),
        "api_gouv": len(api_gouv),
        "data_gouv": len(data_gouv),
        "errors": (api_errors + data_errors)[:12],
    }
    save_app(app)
    update_status("ok" if sources else "empty", {
        "total": len(sources),
        "known": len(known),
        "api_gouv": len(api_gouv),
        "data_gouv": len(data_gouv),
        "articles_added": len(api_articles),
        "errors": (api_errors + data_errors)[:12],
        "message": "Catalogue public API/sources intégré : api.gouv.fr, data.gouv.fr, FHIR Annuaire Santé et MCP data.gouv.",
    })
    print(f"Sources API publiques intégrées : {len(sources)} ; articles ajoutés : {len(api_articles)}")


if __name__ == "__main__":
    main()
