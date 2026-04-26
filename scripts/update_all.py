#!/usr/bin/env python3
"""Reconstruit la base embarquée du site.

Objectifs :
- récupérer la CCAM open data ;
- recalculer les champs utiles au paramétrage Maidis ;
- récupérer une veille institutionnelle côté serveur ;
- produire data/app-data.json et data/app-data.js utilisables hors ligne.

Le script privilégie des sources publiques et institutionnelles. Il utilise des
reprises réseau propres, des en-têtes HTTP réalistes et un repli local pour que
la mise à jour ne casse pas le site lorsqu'une source externe refuse ou limite
une requête.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache" / "pdf"

CCAM_URL = "https://data.smartidf.services/api/records/1.0/download/?dataset=healthref-france-ccam&format=json"

RSS_FEEDS: list[tuple[str, str]] = [
    # Sources RSS institutionnelles uniquement.
]

AMELI_DOC_PAGES: list[tuple[str, str]] = [
    (
        "convention_dentistes",
        "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028",
    ),
    (
        "calendrier_convention",
        "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles",
    ),
    (
        "ccam_medecins",
        "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam",
    ),
]

STATIC_NEWS = [
    {
        "source": "Ameli",
        "title": "Tarifs conventionnels et honoraires limites dentaires",
        "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs",
        "tag": "Tarifs",
    },
    {
        "source": "Ameli",
        "title": "Matériaux et actes prothétiques inclus dans l'offre 100 % Santé dentaire",
        "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire",
        "tag": "100 % Santé",
    },
    {
        "source": "Ameli",
        "title": "CCAM : codage des actes médicaux et téléchargement des versions PDF/Excel",
        "url": "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam",
        "tag": "CCAM",
    },
]

RAC0 = set(
    "HBKD140 HBKD212 HBKD213 HBKD244 HBKD300 HBKD396 HBKD431 HBKD462 "
    "HBLD031 HBLD032 HBLD033 HBLD035 HBLD038 HBLD083 HBLD090 HBLD101 "
    "HBLD123 HBLD138 HBLD148 HBLD203 HBLD215 HBLD224 HBLD231 HBLD232 "
    "HBLD259 HBLD262 HBLD349 HBLD350 HBLD364 HBLD370 HBLD474 HBLD490 "
    "HBLD634 HBLD680 HBLD734 HBLD785".split()
)
MOD = set("HBLD040 HBLD043 HBLD073 HBLD131 HBLD158 HBLD227 HBLD332 HBLD486 HBLD491 HBLD724 HBLD745".split())

PROTH_TERMS = [
    "couronne dentaire",
    "prothese dentaire",
    "prothèse dentaire",
    "prothese amovible",
    "prothèse amovible",
    "bridge",
    "inlay core",
    "infrastructure coronoradiculaire",
]
DENTAL_TERMS = [
    "dentaire",
    "dent",
    "bucco",
    "bouche",
    "mandibul",
    "maxill",
    "gingiv",
    "parodont",
    "pulpe",
    "carie",
    "racine",
    "couronne",
    "prothese dentaire",
    "prothèse dentaire",
    "bridge",
    "incisive",
    "canine",
    "molaire",
    "premolaire",
    "prémolaire",
    "edent",
    "édent",
    "occlus",
    "arcade dentaire",
    "alveol",
    "alvéol",
    "orthodont",
    "endodont",
    "detartrage",
    "détartrage",
    "inlay",
    "onlay",
    "plaque base résine",
    "scellement prophylactique",
    "sillons",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
]


def today() -> str:
    return dt.date.today().isoformat()


def fetch(url: str, *, timeout: int = 60, retries: int = 4) -> bytes:
    """Télécharge une ressource avec reprises et en-têtes HTTP compatibles navigateur."""
    last_error: Exception | None = None
    for attempt in range(retries):
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml,application/json,application/pdf,*/*;q=0.8",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
        }
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {403, 408, 409, 425, 429, 500, 502, 503, 504}:
                raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(min(2 ** attempt, 10) + random.random())
    if last_error:
        raise last_error
    raise RuntimeError(f"Téléchargement impossible : {url}")


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return round(float(str(value).replace(",", ".")), 2)
    except Exception:
        return None


def is_dentalish(libelle: str) -> bool:
    text = (libelle or "").lower()
    return any(term in text for term in DENTAL_TERMS)


def is_panier_scope(code: str, libelle: str) -> bool:
    text = (libelle or "").lower()
    return code in RAC0 or code in MOD or any(term in text for term in PROTH_TERMS)


def classify_panier(code: str, libelle: str) -> tuple[str, str, str]:
    if code in RAC0:
        return "RAC 0 / 100 % Santé", "Haute", "Code prothétique reconnu dans le panier sans reste à charge."
    if code in MOD:
        return "RAC modéré / tarif maîtrisé", "Haute", "Code prothétique reconnu dans le panier à honoraires maîtrisés."
    if is_panier_scope(code, libelle):
        return (
            "Tarif libre ou à vérifier",
            "Moyenne",
            "Acte prothétique/bucco-dentaire détecté, mais non présent dans les listes embarquées RAC 0/modéré.",
        )
    return (
        "Hors périmètre panier 100 % Santé",
        "Haute",
        "Les paniers 100 % Santé concernent les prothèses dentaires : couronnes, bridges et prothèses amovibles. Cet acte n'entre pas dans ce périmètre.",
    )


def normalize_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    fields = raw.get("fields", raw)
    code = str(fields.get("code", "")).strip()
    libelle = str(fields.get("libelle", "")).strip()
    brss = to_float(fields.get("tarif_1") or fields.get("tarif_base") or fields.get("brss"))
    if not code or brss is None:
        return None
    dental = is_dentalish(libelle)
    scope = is_panier_scope(code, libelle)
    panier, certitude, reason = classify_panier(code, libelle)
    taux = 60 if dental or scope else 70
    amo = round(brss * taux / 100, 2)
    return {
        "code": code,
        "activite": str(fields.get("activite", "")),
        "phase": str(fields.get("phase", "")),
        "libelle": libelle,
        "brss": brss,
        "tarif_secteur_1_optam": brss,
        "taux_amo_standard": taux,
        "montant_amo_standard": amo,
        "panier_100_sante": panier,
        "certitude_panier": certitude,
        "justification_panier": reason,
        "perimetre_panier_100_sante": scope,
        "hors_perimetre_panier": not scope,
        "domaine": "Bucco-dentaire / stomatologie" if dental or scope else "Médical CCAM",
        "accord_prealable": fields.get("accord_prealable") or "",
        "code_maidis_suggere": f"{code}-{fields.get('activite', '')}-{fields.get('phase', '')}",
        "notes_parametrage": "Taux et montant AMO indicatifs : à ajuster selon contexte patient (ALD, maternité, AT/MP, C2S, Alsace-Moselle, DOM), majorations et règles Maidis.",
    }


def load_local_records() -> list[dict[str, Any]]:
    path = DATA_DIR / "app-data.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("records", [])
    except Exception as exc:  # noqa: BLE001
        print("Lecture des données locales impossible", exc)
        return []


def load_ccam_records() -> list[dict[str, Any]]:
    try:
        raw = json.loads(fetch(CCAM_URL).decode("utf-8"))
        if isinstance(raw, dict) and "records" in raw:
            raw = raw["records"]
        records = [record for record in (normalize_record(item) for item in raw) if record]
        if records:
            return records
    except Exception as exc:  # noqa: BLE001
        print("Impossible de récupérer la CCAM en ligne, utilisation du repli local", exc)
    return load_local_records()


def read_rss() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source, url in RSS_FEEDS:
        try:
            root = ET.fromstring(fetch(url))
            for item in root.findall(".//item")[:5]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                date = (item.findtext("pubDate") or today()).strip()
                if title and link:
                    items.append({"date": date, "source": source, "title": title, "url": link, "tag": "RSS"})
        except Exception as exc:  # noqa: BLE001
            print("RSS ignoré", source, exc)
    items.extend({"date": today(), **item} for item in STATIC_NEWS)
    return items[:20]


def extract_pdf_links(page_url: str, html_text: str) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+\.pdf(?:\?[^\"']*)?)[\"'][^>]*>(?P<title>.*?)</a>", re.I | re.S)
    for match in pattern.finditer(html_text):
        href = html.unescape(match.group("href").strip())
        title = re.sub(r"<[^>]+>", " ", match.group("title"))
        title = re.sub(r"\s+", " ", html.unescape(title)).strip() or pathlib.Path(href).name
        links.append((title, urllib.parse.urljoin(page_url, href)))
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for title, url in links:
        if url not in seen:
            unique.append((title, url))
            seen.add(url)
    return unique


def safe_pdf_filename(url: str) -> str:
    name = pathlib.Path(urllib.parse.urlparse(url).path).name or "document.pdf"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def download_pdf(url: str) -> pathlib.Path | None:
    try:
        data = fetch(url)
        if not data.startswith(b"%PDF"):
            print("Document ignoré, contenu non PDF", url)
            return None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / safe_pdf_filename(url)
        path.write_bytes(data)
        return path
    except Exception as exc:  # noqa: BLE001
        print("Échec téléchargement", url, exc)
        return None


def extract_codes_from_pdf(path: pathlib.Path) -> set[str]:
    codes: set[str] = set()
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                codes.update(re.findall(r"\b[A-Z]{4}[0-9]{3}\b", text))
    except Exception as exc:  # noqa: BLE001
        print("Analyse PDF impossible", path, exc)
    return codes


def summarize_pdf(path: pathlib.Path, max_chars: int = 300) -> str:
    try:
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            text = " ".join((page.extract_text() or "") for page in pdf.pages[:3])
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars] + ("…" if len(text) > max_chars else "")
    except Exception:
        return ""


def fetch_ameli_documents(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    new_codes: set[str] = set()
    for _name, page_url in AMELI_DOC_PAGES:
        try:
            page = fetch(page_url).decode("utf-8", errors="ignore")
            for title, pdf_url in extract_pdf_links(page_url, page):
                local_pdf = download_pdf(pdf_url)
                codes_found: set[str] = set()
                summary = ""
                if local_pdf:
                    codes_found = extract_codes_from_pdf(local_pdf)
                    summary = summarize_pdf(local_pdf)
                    new_codes.update(codes_found)
                docs.append({
                    "date": today(),
                    "source": "Ameli",
                    "title": title,
                    "url": pdf_url,
                    "tag": "Document",
                    "summary": summary,
                    "codes": sorted(codes_found),
                })
        except Exception as exc:  # noqa: BLE001
            print("Ameli docs ignorés", page_url, exc)

    existing_codes = {record["code"] for record in records}
    for code in sorted(new_codes - existing_codes):
        records.append({
            "code": code,
            "activite": "",
            "phase": "",
            "libelle": "Code issu d'un document Ameli (détails à vérifier)",
            "brss": None,
            "tarif_secteur_1_optam": None,
            "taux_amo_standard": None,
            "montant_amo_standard": None,
            "panier_100_sante": "À vérifier",
            "certitude_panier": "Basse",
            "justification_panier": "Code non présent dans la base CCAM, détecté dans un document Ameli.",
            "perimetre_panier_100_sante": False,
            "hors_perimetre_panier": True,
            "domaine": "Médical CCAM",
            "accord_prealable": "",
            "code_maidis_suggere": f"{code}--",
            "notes_parametrage": "Code détecté automatiquement à partir d'un document Ameli. Complétez manuellement ses informations.",
        })
    return docs


def build_meta(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "generated": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "timezone": dt.datetime.now().astimezone().tzinfo.tzname(None),
        "total": len(records),
        "medical": sum(1 for r in records if r["domaine"] == "Médical CCAM"),
        "bucco_dentaire": sum(1 for r in records if r["domaine"] != "Médical CCAM"),
        "hors_perimetre_panier": sum(1 for r in records if r["hors_perimetre_panier"]),
        "rac0": sum(1 for r in records if str(r["panier_100_sante"]).startswith("RAC 0")),
        "modere": sum(1 for r in records if str(r["panier_100_sante"]).startswith("RAC modéré")),
        "source": "CCAM open data + règles Ameli 100 % Santé + veille institutionnelle",
        "version": "v4-maidis-robuste",
    }


def main() -> None:
    records = load_ccam_records()
    news_items = (read_rss() + fetch_ameli_documents(records))[:40]
    app = {
        "meta": build_meta(records),
        "records": records,
        "news": news_items,
        "profiles": {"medical_standard": 70, "dental_standard": 60, "user_example": 70},
    }
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "app-data.json").write_text(json.dumps(app, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "app-data.js").write_text("window.CCAM_APP_DATA = " + json.dumps(app, ensure_ascii=False) + ";\n", encoding="utf-8")
    print("OK", app["meta"])


if __name__ == "__main__":
    main()
