#!/usr/bin/env python3
"""Intégration des catalogues/API publiques utiles au site.

Ce script complète le site avec des sources techniques fiables :
- catalogue open source api.gouv.fr depuis GitHub ;
- API data.gouv.fr datasets/dataservices ;
- API FHIR Annuaire Santé et endpoints documentés par l'ANS ;
- point d'entrée MCP data.gouv.fr pour futures recherches IA.

Important : ces fiches vont dans `public_api_sources` et `api_source_articles`,
pas dans `articles`, afin de ne pas polluer les dossiers d'actualité.
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
FHIR_ENDPOINTS = ["metadata", "Practitioner", "PractitionerRole", "Organization", "HealthcareService", "Device"]

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
    req = urllib.request.Request(url, headers={"Accept": "application/json, application/vnd.github+json, */*;q=0.5", "User-Agent": "maidis-ccam-hub/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def fetch_text(url: str, timeout: int = 35) -> str:
    req = urllib.request.Request(url, headers={"Accept": "text/plain, text/markdown, text/html, application/json, */*;q=0.5", "User-Agent": "maidis-ccam-hub/1.0"})
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
        value = value.strip().strip('"').strip("'")
        if key.strip() and value:
            data[key.strip()] = value
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
            if not is_health_related(f"{name} {download_url}"):
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
    queries = ["santé remboursement", "CCAM actes médicaux", "médicaments remboursement", "PMSI MCO OpenCCAM", "terminologies de santé", "annuaire santé FHIR"]
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for query in queries:
        encoded = urllib.parse.quote(query)
        for template, kind in [(DATA_GOUV_DATASETS, "dataset"), (DATA_GOUV_DATASERVICES, "dataservice")]:
            try:
                url = template.format(query=encoded)
                payload = fetch_json(url)
                results = payload.get("data", []) if isinstance(payload, dict) else []
                for item in results:
                    title = first_non_empty(item.get("title"), item.get("name"), item.get("slug"), query)
                    page = first_non_empty(item.get("page"), item.get("uri"), item.get("url"), item.get("self_web_url"))
                    if not page and item.get("slug"):
                        page = f"https://www.data.gouv.fr/fr/datasets/{item.get('slug')}/" if kind == "dataset" else f"https://www.data.gouv.fr/fr/dataservices/{item.get('slug')}/"
                    description = compact_text(first_non_empty(item.get("description"), item.get("tagline"), item.get("acronym"), ""))[:900]
                    key = page or title
                    if key in seen or not is_health_related(f"{title} {description} {query}"):
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
                return "ok", first_non_empty(payload.get("resourceType"), "json ok")
            return "ok", "json reçu"
        return "ok", compact_text(fetch_text(url, timeout=20)[:240])
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
    app["api_source_articles"] = []
    app.setdefault("meta", {})["public_api_sources"] = {
        "generated": now_fr(),
        "total": len(sources),
        "known": len(known),
        "api_gouv": len(api_gouv),
        "data_gouv": len(data_gouv),
        "errors": (api_errors + data_errors)[:12],
        "note": "Ces sources sont affichées dans sources.html et ne sont pas mélangées aux dossiers d’actualité.",
    }
    save_app(app)
    update_status("ok" if sources else "empty", {
        "total": len(sources),
        "known": len(known),
        "api_gouv": len(api_gouv),
        "data_gouv": len(data_gouv),
        "articles_added": 0,
        "errors": (api_errors + data_errors)[:12],
        "message": "Catalogue public API/sources intégré dans public_api_sources uniquement.",
    })
    print(f"Sources API publiques intégrées : {len(sources)} ; aucun article dossier ajouté")


if __name__ == "__main__":
    main()
