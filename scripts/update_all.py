#!/usr/bin/env python3
"""Synchronisation robuste de l'Annuaire CCAM Santé.

Objectif :
- récupérer les actes CCAM depuis plusieurs exports OpenDataSoft/Healthref ;
- ne jamais écraser une base valide par une base vide ;
- continuer même si Ameli bloque certaines pages ;
- écrire des données JSON/JS valides avec horodatage Europe/Paris ;
- produire un fichier de statut lisible pour diagnostiquer la synchro.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import html
import io
import json
import pathlib
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = ROOT / "cache" / "pdf"
PARIS = ZoneInfo("Europe/Paris")

MIN_MAIN_RECORDS = 3000
MIN_PREVIOUS_RECORDS = 1000

CCAM_SOURCES = [
    {
        "name": "OpenDataSoft public Healthref CCAM export JSON v2",
        "url": "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/healthref-france-ccam/exports/json?lang=fr&timezone=Europe%2FParis",
        "kind": "json",
    },
    {
        "name": "OpenDataSoft public Healthref CCAM export CSV v2",
        "url": "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets/healthref-france-ccam/exports/csv?lang=fr&timezone=Europe%2FParis&use_labels=false&delimiter=%3B",
        "kind": "csv",
    },
    {
        "name": "OpenDataSoft legacy Healthref CCAM download",
        "url": "https://data.opendatasoft.com/api/records/1.0/download/?dataset=healthref-france-ccam@public&format=json",
        "kind": "json",
    },
    {
        "name": "SmartIDF Healthref CCAM export JSON v2",
        "url": "https://data.smartidf.services/api/explore/v2.1/catalog/datasets/healthref-france-ccam/exports/json?lang=fr&timezone=Europe%2FParis",
        "kind": "json",
    },
    {
        "name": "SmartIDF Healthref CCAM legacy download",
        "url": "https://data.smartidf.services/api/records/1.0/download/?dataset=healthref-france-ccam&format=json",
        "kind": "json",
    },
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36",
]

RSS_FEEDS: list[tuple[str, str]] = []

AMELI_DOC_PAGES = [
    ("convention_dentistes", "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028"),
    ("calendrier_convention", "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles"),
    ("ccam_medecins", "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam"),
]

ARTICLE_SOURCES = [
    {"id": "convention-dentaire-2023-2028", "category": "Dentaire", "tag": "Convention", "title": "Convention dentaire 2023-2028 : ce qu'il faut retenir", "url": "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028"},
    {"id": "calendrier-mesures-conventionnelles", "category": "Dentaire", "tag": "Calendrier", "title": "Calendrier des mesures conventionnelles : points de vigilance", "url": "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles"},
    {"id": "tarifs-dentaires", "category": "Tarifs", "tag": "Tarifs", "title": "Tarifs conventionnels dentaires : repères pratiques", "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs"},
    {"id": "cent-pour-cent-sante-dentaire", "category": "100 % Santé", "tag": "100 % Santé", "title": "100 % Santé dentaire : actes, matériaux et paniers de soins", "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire"},
    {"id": "codage-ccam-medecins", "category": "CCAM", "tag": "CCAM", "title": "Codage CCAM : retrouver et contrôler les actes médicaux", "url": "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam"},
]

RAC0 = set("HBKD140 HBKD212 HBKD213 HBKD244 HBKD300 HBKD396 HBKD431 HBKD462 HBLD031 HBLD032 HBLD033 HBLD035 HBLD038 HBLD083 HBLD090 HBLD101 HBLD123 HBLD138 HBLD148 HBLD203 HBLD215 HBLD224 HBLD231 HBLD232 HBLD259 HBLD262 HBLD349 HBLD350 HBLD364 HBLD370 HBLD474 HBLD490 HBLD634 HBLD680 HBLD734 HBLD785".split())
MOD = set("HBLD040 HBLD043 HBLD073 HBLD131 HBLD158 HBLD227 HBLD332 HBLD486 HBLD491 HBLD724 HBLD745".split())

PROTH_TERMS = [
    "couronne dentaire", "prothese dentaire", "prothèse dentaire", "prothese amovible",
    "prothèse amovible", "bridge", "inlay core", "infrastructure coronoradiculaire",
]
DENTAL_TERMS = "dentaire dent bucco bouche mandibul maxill gingiv parodont pulpe carie racine couronne prothese prothèse bridge incisive canine molaire premolaire prémolaire edent édent occlus arcade alveol alvéol orthodont endodont detartrage détartrage inlay onlay résine sillons".split()

STATIC_NEWS = [
    {"date": dt.date.today().isoformat(), "source": "Ameli", "title": "Tarifs conventionnels et honoraires limites dentaires", "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs", "tag": "Tarifs"},
    {"date": dt.date.today().isoformat(), "source": "Ameli", "title": "Matériaux et actes prothétiques inclus dans l'offre 100 % Santé dentaire", "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire", "tag": "100 % Santé"},
    {"date": dt.date.today().isoformat(), "source": "Ameli", "title": "CCAM : codage des actes médicaux et téléchargement des versions PDF/Excel", "url": "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam", "tag": "CCAM"},
]


def now_fr() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS)


def fetch(url: str, timeout: int = 45, retries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/json,text/csv,application/pdf,*/*",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.4",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in {403, 408, 409, 425, 429, 500, 502, 503, 504}:
                raise
        except Exception as exc:
            last = exc
        time.sleep(min(2 ** attempt, 8) + random.random())
    raise last or RuntimeError(f"Impossible de récupérer {url}")


def norm_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    return value


def get_any(row: dict[str, Any], names: list[str]) -> Any:
    normalized = {norm_key(k): v for k, v in row.items()}
    for name in names:
        key = norm_key(name)
        if key in normalized and normalized[key] not in (None, ""):
            return normalized[key]
    return None


def fnum(value: Any) -> float | None:
    if value in (None, ""):
        return None
    raw = str(value).strip().replace("\xa0", "").replace("€", "").replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        raw = raw.replace(",", ".")
    try:
        return round(float(raw), 2)
    except Exception:
        return None


def code_from(value: Any) -> str:
    raw = str(value or "").upper().strip()
    match = re.search(r"\b[A-Z]{4}\d{3}\b", raw)
    return match.group(0) if match else raw


def dental(libelle: str) -> bool:
    text = (libelle or "").lower()
    return any(term in text for term in DENTAL_TERMS)


def panier_scope(code: str, libelle: str) -> bool:
    text = (libelle or "").lower()
    return code in RAC0 or code in MOD or any(term in text for term in PROTH_TERMS)


def classify(code: str, libelle: str) -> tuple[str, str, str]:
    if code in RAC0:
        return "RAC 0 / 100 % Santé", "Haute", "Code prothétique reconnu dans le panier sans reste à charge."
    if code in MOD:
        return "RAC modéré / tarif maîtrisé", "Haute", "Code prothétique reconnu dans le panier à honoraires maîtrisés."
    if panier_scope(code, libelle):
        return "Tarif libre ou à vérifier", "Moyenne", "Acte prothétique ou bucco-dentaire détecté, à vérifier selon le contexte patient."
    return "Hors périmètre panier 100 % Santé", "Haute", "Cet acte n'entre pas dans le périmètre des paniers 100 % Santé dentaires."


def normalize_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    row = raw.get("fields", raw) if isinstance(raw, dict) else {}
    if not isinstance(row, dict):
        return None

    code = code_from(get_any(row, ["code", "code_ccam", "code_acte", "acte", "codage", "id"]))
    libelle = str(get_any(row, ["libelle", "libellé", "libelle_acte", "description", "texte", "nom"]) or "").strip()
    brss = fnum(get_any(row, ["tarif_1", "tarif1", "tarif_base", "brss", "base_remboursement", "montant", "tarif"]))
    activite = str(get_any(row, ["activite", "activité", "activity"]) or "").strip()
    phase = str(get_any(row, ["phase"]) or "").strip()
    accord = str(get_any(row, ["accord_prealable", "accord préalable", "accord", "ap"]) or "").strip()

    if not re.fullmatch(r"[A-Z]{4}\d{3}", code or ""):
        return None
    if not libelle or brss is None:
        return None

    is_dental = dental(libelle)
    in_scope = panier_scope(code, libelle)
    panier, certitude, justification = classify(code, libelle)
    taux = 60 if is_dental or in_scope else 70
    amo = round(brss * taux / 100, 2)

    return {
        "code": code,
        "activite": activite,
        "phase": phase,
        "libelle": libelle,
        "brss": brss,
        "tarif_secteur_1_optam": brss,
        "taux_amo_standard": taux,
        "montant_amo_standard": amo,
        "panier_100_sante": panier,
        "certitude_panier": certitude,
        "justification_panier": justification,
        "perimetre_panier_100_sante": in_scope,
        "hors_perimetre_panier": not in_scope,
        "domaine": "Bucco-dentaire / stomatologie" if is_dental or in_scope else "Médical CCAM",
        "accord_prealable": accord,
        "code_maidis_suggere": f"{code}-{activite}-{phase}",
        "notes_parametrage": "Taux et montant AMO indicatifs : à contrôler selon le contexte patient, les majorations, l'exonération, le régime et les règles applicables.",
    }


def extract_json_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("records", "results", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def read_source(source: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.time()
    content = fetch(source["url"])
    raw_items: list[dict[str, Any]]
    if source["kind"] == "csv":
        text = content.decode("utf-8-sig", errors="replace")
        raw_items = list(csv.DictReader(io.StringIO(text), delimiter=";"))
    else:
        payload = json.loads(content.decode("utf-8", errors="replace"))
        raw_items = extract_json_items(payload)

    dedup: dict[str, dict[str, Any]] = {}
    rejected = 0
    for item in raw_items:
        record = normalize_record(item)
        if record:
            dedup[f"{record['code']}|{record['activite']}|{record['phase']}"] = record
        else:
            rejected += 1

    records = sorted(dedup.values(), key=lambda r: (r["code"], r["activite"], r["phase"]))
    info = {
        "name": source["name"],
        "url": source["url"],
        "kind": source["kind"],
        "raw_items": len(raw_items),
        "valid_records": len(records),
        "rejected_items": rejected,
        "duration_seconds": round(time.time() - started, 2),
    }
    return records, info


def local_app() -> dict[str, Any]:
    path = DATA / "app-data.json"
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Lecture locale impossible: {exc}")
        return {}


def valid_previous_records(app: dict[str, Any]) -> list[dict[str, Any]]:
    records = app.get("records", [])
    if isinstance(records, list) and len(records) >= MIN_PREVIOUS_RECORDS:
        return [r for r in records if isinstance(r, dict)]
    return []


def load_records(previous_records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for source in CCAM_SOURCES:
        try:
            records, info = read_source(source)
            attempts.append({**info, "status": "ok"})
            if len(records) >= MIN_MAIN_RECORDS:
                return records, {
                    "mode": "fresh",
                    "selected_source": info,
                    "attempts": attempts,
                    "message": "Données CCAM fraîches récupérées avec succès.",
                }
        except Exception as exc:
            attempts.append({
                "name": source["name"],
                "url": source["url"],
                "kind": source["kind"],
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })

    if previous_records:
        return previous_records, {
            "mode": "stale",
            "selected_source": "previous-valid-data",
            "attempts": attempts,
            "message": "Toutes les sources fraîches ont échoué : conservation de la dernière base valide.",
        }

    return [], {
        "mode": "empty",
        "selected_source": None,
        "attempts": attempts,
        "message": "Aucune source CCAM fraîche et aucune base précédente exploitable.",
    }


def clean_text(src: str) -> str:
    src = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", src, flags=re.I | re.S)
    src = re.sub(r"<(nav|footer|header|aside)\b.*?</\1>", " ", src, flags=re.I | re.S)
    src = re.sub(r"<(h[1-4]|p|li|td|th|div|section|article)\b[^>]*>", "\n", src, flags=re.I)
    src = re.sub(r"<[^>]+>", " ", src)
    src = html.unescape(src)
    src = re.sub(r"\s+", " ", src).strip()
    for junk in ["Javascript est désactivé", "Vous utilisez un navigateur obsolète", "accepter les cookies"]:
        src = src.replace(junk, "")
    return src.strip()


def codes(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Z]{4}\d{3}\b", text or ""))


def relevant_sentences(text: str, limit: int = 8) -> list[str]:
    keys = "ccam tarif honoraires convention dentaire santé prise en charge acte remboursement prothèse panier devis patient chirurgien-dentiste".split()
    out: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        sentence = re.sub(r"\s+", " ", sentence).strip()
        low = sentence.lower()
        if 80 <= len(sentence) <= 360 and any(key in low for key in keys):
            out.append(sentence)
        if len(out) >= limit:
            break
    return out


def pdf_links(page_url: str, page_html: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+\.pdf(?:\?[^\"']*)?)[\"'][^>]*>(?P<title>.*?)</a>", re.I | re.S)
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for match in pattern.finditer(page_html):
        url = urllib.parse.urljoin(page_url, html.unescape(match.group("href").strip()))
        title = re.sub(r"<[^>]+>", " ", match.group("title"))
        title = re.sub(r"\s+", " ", html.unescape(title)).strip() or pathlib.Path(url).name
        if url not in seen:
            seen.add(url)
            out.append((title, url))
    return out


def pdf_name(url: str) -> str:
    parsed = pathlib.Path(urllib.parse.urlparse(url).path).name or "document.pdf"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", parsed)


def download_pdf(url: str) -> pathlib.Path | None:
    try:
        content = fetch(url, timeout=30, retries=2)
        if not content.startswith(b"%PDF"):
            return None
        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / pdf_name(url)
        path.write_bytes(content)
        return path
    except Exception as exc:
        print(f"PDF ignoré {url}: {exc}")
        return None


def pdf_text(path: pathlib.Path | None, pages: int = 8) -> str:
    if not path:
        return ""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            text = " ".join((page.extract_text() or "") for page in pdf.pages[:pages])
        return re.sub(r"\s+", " ", text).strip()
    except Exception as exc:
        print(f"Analyse PDF impossible {path}: {exc}")
        return ""


def docs_from_ameli(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    found: set[str] = set()

    for _, url in AMELI_DOC_PAGES:
        try:
            page = fetch(url, timeout=25, retries=2).decode("utf-8", errors="ignore")
            for title, pdf_url in pdf_links(url, page)[:8]:
                text = pdf_text(download_pdf(pdf_url), 10)
                detected = codes(text)
                found |= detected
                docs.append({
                    "date": dt.date.today().isoformat(),
                    "source": "Ameli",
                    "title": title,
                    "url": pdf_url,
                    "tag": "Document",
                    "summary": text[:300] + ("…" if len(text) > 300 else ""),
                    "codes": sorted(detected),
                })
        except Exception as exc:
            print(f"Page Ameli ignorée {url}: {exc}")

    known = {r["code"] for r in records if r.get("code")}
    for code in sorted(found - known):
        records.append({
            "code": code,
            "activite": "",
            "phase": "",
            "libelle": "Code détecté dans un document institutionnel Ameli (à vérifier)",
            "brss": None,
            "tarif_secteur_1_optam": None,
            "taux_amo_standard": None,
            "montant_amo_standard": None,
            "panier_100_sante": "À vérifier",
            "certitude_panier": "Basse",
            "justification_panier": "Code détecté dans un document institutionnel, absent de la base tarifaire principale récupérée.",
            "perimetre_panier_100_sante": False,
            "hors_perimetre_panier": True,
            "domaine": "Médical CCAM",
            "accord_prealable": "",
            "code_maidis_suggere": f"{code}--",
            "notes_parametrage": "Information détectée automatiquement dans un document : contrôle manuel obligatoire avant utilisation.",
        })
    return docs


def rss_news() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source, url in RSS_FEEDS:
        try:
            root = ET.fromstring(fetch(url, timeout=20, retries=2))
            for item in root.findall(".//item")[:5]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                date = (item.findtext("pubDate") or dt.date.today().isoformat()).strip()
                if title and link:
                    items.append({"date": date, "source": source, "title": title, "url": link, "tag": "RSS"})
        except Exception as exc:
            print(f"RSS ignoré {source}: {exc}")
    return (items + STATIC_NEWS)[:20]


def sample_codes(records: list[dict[str, Any]], predicate, limit: int = 80) -> list[str]:
    return sorted({r["code"] for r in records if r.get("code") and predicate(r)})[:limit]


def stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    dental_records = [r for r in records if r.get("domaine") != "Médical CCAM"]
    medical_records = [r for r in records if r.get("domaine") == "Médical CCAM"]
    rac0 = [r for r in records if str(r.get("panier_100_sante", "")).startswith("RAC 0")]
    mod = [r for r in records if str(r.get("panier_100_sante", "")).startswith("RAC modéré")]
    brss_values = [r["brss"] for r in records if isinstance(r.get("brss"), (int, float))]
    return {
        "total": len(records),
        "dental": len(dental_records),
        "medical": len(medical_records),
        "rac0": len(rac0),
        "mod": len(mod),
        "brss_min": min(brss_values) if brss_values else None,
        "brss_max": max(brss_values) if brss_values else None,
    }


def article_codes(source: dict[str, str], records: list[dict[str, Any]], extracted: set[str]) -> list[str]:
    sid = source["id"]
    linked = set(extracted)
    if "cent-pour-cent" in sid:
        linked |= RAC0 | MOD
    elif "tarifs" in sid:
        linked |= set(sample_codes(records, lambda r: r.get("domaine") != "Médical CCAM" and r.get("brss") is not None, 70))
    elif "convention" in sid or "calendrier" in sid:
        linked |= set(sample_codes(records, lambda r: r.get("domaine") != "Médical CCAM", 70))
    elif "codage" in sid:
        linked |= set(sample_codes(records, lambda r: r.get("domaine") == "Médical CCAM", 70))
    existing = {r["code"] for r in records if r.get("code")}
    return sorted(code for code in linked if code in existing)[:120]


def build_body(source: dict[str, str], records: list[dict[str, Any]], extracted_text: str, extracted_bits: list[str], linked_codes: list[str], pdf_count: int) -> tuple[str, str]:
    st = stats(records)
    source_link = f"<a href=\"{html.escape(source['url'])}\" target=\"_blank\" rel=\"noopener\">page officielle Ameli</a>"
    intro = (
        f"Ce dossier est généré automatiquement à partir de sources institutionnelles suivies et de la base CCAM synchronisée. "
        f"La génération actuelle contient {st['total']:,} actes, dont {st['dental']:,} actes bucco-dentaires et {st['medical']:,} actes médicaux."
    ).replace(",", " ")

    facts: list[str] = []
    facts.extend(extracted_bits[:4])
    if "cent-pour-cent" in source["id"]:
        facts.extend([
            f"L’annuaire identifie {st['rac0']} codes classés RAC 0 / 100 % Santé et {st['mod']} codes classés RAC modéré ou tarif maîtrisé.",
            "La détermination du panier doit être rapprochée du matériau, de la localisation, du devis et du contexte patient.",
        ])
    elif "tarifs" in source["id"]:
        facts.extend([
            "La BRSS sert de base de lecture pour estimer le remboursement AMO, mais elle ne remplace pas les règles applicables au patient.",
            f"Dans la génération actuelle, les tarifs de base disponibles s’étendent de {st['brss_min']} € à {st['brss_max']} € selon les actes référencés." if st["brss_min"] is not None else "Les tarifs sont repris lorsqu’ils sont présents dans la source CCAM synchronisée.",
        ])
    elif "codage" in source["id"]:
        facts.extend([
            "La lecture fiable d’un acte repose sur le code, l’activité, la phase, le libellé et la base tarifaire.",
            "Le moteur de recherche permet de contrôler rapidement un code, un libellé, un domaine ou un panier de soins.",
        ])
    else:
        facts.extend([
            "Les mesures conventionnelles doivent être rapprochées des actes CCAM réellement utilisés et de leur paramétrage métier.",
            "Les actes prothétiques demandent une attention particulière sur le panier de soins, le tarif et la justification affichée.",
        ])

    facts = [fact for index, fact in enumerate(facts) if fact and fact not in facts[:index]][:7]
    summary = facts[0] if facts else f"Dossier pratique généré pour {source['title']}."

    body = "".join([
        f"<p>{html.escape(intro)}</p>",
        "<h2>À retenir</h2><ul>",
        "".join(f"<li>{html.escape(fact)}</li>" for fact in facts[:5]),
        "</ul>",
        "<h2>Impact pratique</h2>",
        "<p>Ce dossier aide à contrôler les actes, les paniers, les tarifs de base et les points de vigilance avant export ou paramétrage. Les valeurs affichées restent une aide de lecture et doivent être validées avec les règles officielles et le contexte patient.</p>",
        "<h2>Codes liés</h2>",
        f"<p>{html.escape(', '.join(linked_codes[:80])) if linked_codes else 'Aucun code lié n’a pu être déterminé pour cette génération.'}</p>",
        "<h2>Traçabilité</h2>",
        f"<p>Source suivie : {source_link}. {pdf_count} document(s) PDF lié(s) détecté(s). Texte institutionnel exploitable : {len(extracted_text)} caractères.</p>",
    ])
    return summary, body


def make_article(source: dict[str, str], records: list[dict[str, Any]]) -> dict[str, Any]:
    page_text = ""
    pdf_texts: list[str] = []
    pdf_count = 0
    extracted_codes: set[str] = set()

    try:
        page = fetch(source["url"], timeout=25, retries=2).decode("utf-8", errors="ignore")
        page_text = clean_text(page)
        extracted_codes |= codes(page_text)
        for _, url in pdf_links(source["url"], page)[:5]:
            text = pdf_text(download_pdf(url), 8)
            if text:
                pdf_count += 1
                pdf_texts.append(text)
                extracted_codes |= codes(text)
    except Exception as exc:
        print(f"Article Ameli ignoré {source['url']}: {exc}")

    extracted_text = (page_text + " " + " ".join(pdf_texts)).strip()
    bits = relevant_sentences(extracted_text, 8)
    linked = article_codes(source, records, extracted_codes)
    summary, body = build_body(source, records, extracted_text, bits, linked, pdf_count)

    return {
        "id": source["id"],
        "title": source["title"],
        "date": dt.date.today().isoformat(),
        "source": "Ameli",
        "source_url": source["url"],
        "category": source["category"],
        "tag": source["tag"],
        "summary": summary,
        "content_html": body,
        "codes": linked,
        "codes_detectes": sorted(extracted_codes),
        "pdf_count": pdf_count,
        "extracted_chars": len(extracted_text),
        "confidence": "Haute" if len(extracted_text) > 500 else "Moyenne",
    }


def build_articles(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    articles = [make_article(source, records) for source in ARTICLE_SOURCES]
    links: dict[str, list[str]] = {}
    for article in articles:
        for code in article.get("codes", []):
            links.setdefault(code, []).append(article["id"])
    for record in records:
        if record.get("code") in links:
            record["articles_lies"] = links[record["code"]][:8]
    return articles


def record_key(record: dict[str, Any]) -> str:
    return f"{record.get('code', '')}|{record.get('activite', '')}|{record.get('phase', '')}"


def changes(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> dict[str, Any]:
    old = {record_key(r): r for r in previous if r.get("code")}
    new = {record_key(r): r for r in current if r.get("code")}
    modified: list[dict[str, Any]] = []
    for key in sorted(set(old) & set(new)):
        before, after = old[key], new[key]
        fields = [field for field in ["libelle", "brss", "panier_100_sante", "domaine", "accord_prealable"] if before.get(field) != after.get(field)]
        if fields:
            modified.append({
                "code": after.get("code"),
                "activite": after.get("activite"),
                "phase": after.get("phase"),
                "libelle": after.get("libelle"),
                "fields": fields,
                "before": {field: before.get(field) for field in fields},
                "after": {field: after.get(field) for field in fields},
            })
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    return {
        "date": now_fr().isoformat(timespec="seconds"),
        "added_count": len(added),
        "removed_count": len(removed),
        "modified_count": len(modified),
        "added": [new[key] for key in added[:80]],
        "removed": [old[key] for key in removed[:80]],
        "modified": modified[:120],
    }


def meta(records: list[dict[str, Any]], articles: list[dict[str, Any]], report: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated": now_fr().isoformat(timespec="seconds"),
        "timezone": "Europe/Paris",
        "total": len(records),
        "medical": sum(1 for r in records if r.get("domaine") == "Médical CCAM"),
        "bucco_dentaire": sum(1 for r in records if r.get("domaine") != "Médical CCAM"),
        "hors_perimetre_panier": sum(1 for r in records if r.get("hors_perimetre_panier")),
        "rac0": sum(1 for r in records if str(r.get("panier_100_sante", "")).startswith("RAC 0")),
        "modere": sum(1 for r in records if str(r.get("panier_100_sante", "")).startswith("RAC modéré")),
        "articles": len(articles),
        "source": "Healthref CCAM OpenDataSoft + veille institutionnelle Ameli",
        "selected_source": report.get("selected_source"),
        "sync_mode": report.get("mode"),
        "status": "ok" if report.get("mode") == "fresh" else report.get("mode", "unknown"),
        "message": report.get("message"),
        "version": "v7-synchronisation-robuste",
    }


def fingerprint(app: dict[str, Any]) -> str:
    lite = {
        "meta": {key: value for key, value in app.get("meta", {}).items() if key != "generated"},
        "records": app.get("records", []),
        "articles": app.get("articles", []),
        "news": app.get("news", []),
    }
    return hashlib.sha256(json.dumps(lite, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def safe_empty_app(report: dict[str, Any]) -> dict[str, Any]:
    generated = now_fr().isoformat(timespec="seconds")
    return {
        "meta": {
            "generated": generated,
            "timezone": "Europe/Paris",
            "total": 0,
            "medical": 0,
            "bucco_dentaire": 0,
            "hors_perimetre_panier": 0,
            "rac0": 0,
            "modere": 0,
            "articles": 0,
            "source": "Synchronisation CCAM en attente",
            "selected_source": None,
            "sync_mode": "empty",
            "status": "pending",
            "message": report.get("message", "Aucune donnée CCAM disponible pour le moment."),
            "version": "v7-synchronisation-robuste",
        },
        "records": [],
        "news": STATIC_NEWS,
        "articles": [],
        "changes": {
            "date": generated,
            "added_count": 0,
            "removed_count": 0,
            "modified_count": 0,
            "added": [],
            "removed": [],
            "modified": [],
        },
        "profiles": {"medical_standard": 70, "dental_standard": 60, "user_example": 70},
    }


def write_outputs(app: dict[str, Any], report: dict[str, Any]) -> None:
    DATA.mkdir(exist_ok=True)
    app["meta"]["fingerprint"] = fingerprint(app)
    status = {
        "generated": now_fr().isoformat(timespec="seconds"),
        "timezone": "Europe/Paris",
        "status": app.get("meta", {}).get("status"),
        "sync_mode": app.get("meta", {}).get("sync_mode"),
        "total_records": len(app.get("records", [])),
        "message": app.get("meta", {}).get("message"),
        "report": report,
    }

    json_text = json.dumps(app, ensure_ascii=False, indent=2)
    js_text = "window.CCAM_APP_DATA = " + json.dumps(app, ensure_ascii=False) + ";\n"
    status_text = json.dumps(status, ensure_ascii=False, indent=2)

    (DATA / "app-data.json.tmp").write_text(json_text, encoding="utf-8")
    (DATA / "app-data.js.tmp").write_text(js_text, encoding="utf-8")
    (DATA / "sync-status.json.tmp").write_text(status_text, encoding="utf-8")

    (DATA / "app-data.json.tmp").replace(DATA / "app-data.json")
    (DATA / "app-data.js.tmp").replace(DATA / "app-data.js")
    (DATA / "sync-status.json.tmp").replace(DATA / "sync-status.json")


def main() -> int:
    started = now_fr()
    previous = local_app()
    previous_records = valid_previous_records(previous)

    records, report = load_records(previous_records)

    if not records:
        app = safe_empty_app(report)
        write_outputs(app, report)
        print("SYNC EMPTY", json.dumps(report, ensure_ascii=False))
        return 0

    if report.get("mode") == "fresh":
        news = (rss_news() + docs_from_ameli(records))[:40]
        articles = build_articles(records)
    else:
        news = previous.get("news") if isinstance(previous.get("news"), list) else STATIC_NEWS
        articles = previous.get("articles") if isinstance(previous.get("articles"), list) else []

    app = {
        "meta": meta(records, articles, report),
        "records": records,
        "news": news,
        "articles": articles,
        "changes": changes(previous_records, records),
        "profiles": {"medical_standard": 70, "dental_standard": 60, "user_example": 70},
    }

    report["started_at"] = started.isoformat(timespec="seconds")
    report["finished_at"] = now_fr().isoformat(timespec="seconds")
    report["duration_seconds"] = round((now_fr() - started).total_seconds(), 2)

    write_outputs(app, report)
    print("SYNC OK", json.dumps(app["meta"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
