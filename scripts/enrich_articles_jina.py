#!/usr/bin/env python3
"""Génération de dossiers Ameli via Jina Reader.

Pourquoi Jina ici ?
- Les pages Ameli publiques sont visibles par les moteurs et contiennent des accordéons.
- Playwright sur GitHub Actions peut recevoir une page pauvre ou filtrée.
- Jina Reader convertit une URL publique en Markdown propre, compatible LLM.
- Gemini reçoit ensuite ce Markdown dense pour reformulation.

Règle stricte : aucune association artificielle de codes CCAM.
Seuls les codes explicitement présents dans le texte source sont liés.
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

SOURCE_TEXT_LIMIT = 36000
MIN_TEXT_CHARS = 700
MAX_ARTICLES = 18

AMELI_SOURCES = [
    {
        "url": "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles",
        "category": "Convention",
    },
    {
        "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/nomenclatures-codage/ccam/codage",
        "category": "CCAM",
    },
    {
        "url": "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam",
        "category": "CCAM",
    },
    {
        "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire",
        "category": "100 % Santé",
    },
    {
        "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/pratique-tiers-payant/tiers-payant-examen-bucco-dentaire-soins",
        "category": "Tarifs",
    },
    {
        "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/pratique-tiers-payant/tiers-payant-faq",
        "category": "Tarifs",
    },
    {
        "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/services-patients/dents",
        "category": "Dentaire",
    },
    {
        "url": "https://www.ameli.fr/chirurgien-dentiste/actualites/tout-savoir-sur-la-pratique-du-tiers-payant-pour-l-examen-bucco-dentaire-et-les-soins-associes",
        "category": "Tarifs",
    },
    {
        "url": "https://www.ameli.fr/chirurgien-dentiste/actualites/m-t-dents-tous-les-ans-une-campagne-de-communication-pour-promouvoir-la-sante-bucco-dentaire",
        "category": "Dentaire",
    },
    {
        "url": "https://www.ameli.fr/medecin/actualites/le-programme-m-t-dents-evolue-et-devient-m-t-dents-tous-les-ans",
        "category": "Dentaire",
    },
    {
        "url": "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028",
        "category": "Convention",
    },
    {
        "url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs",
        "category": "Tarifs",
    },
]

TOPIC_KEYWORDS = [
    "ccam", "codage", "acte", "nomenclature", "tarif", "convention", "honoraire",
    "rémunération", "facturation", "100 % santé", "prothétique", "prothèse",
    "dentaire", "chirurgien-dentiste", "prise en charge", "panier", "devis", "tiers payant",
    "examen bucco-dentaire", "m't dents", "brss", "amo", "amc", "ngap", "complémentaire",
]

CATEGORY_RULES = [
    ("100 % Santé", ["100 % santé", "reste à charge", "panier", "prothétique", "prothèse"]),
    ("Tarifs", ["tarif", "honoraire", "brss", "amo", "amc", "tiers payant", "prise en charge"]),
    ("Dentaire", ["dentaire", "dentiste", "bucco", "m't dents", "examen bucco-dentaire"]),
    ("Convention", ["convention", "avenant", "calendrier", "mesures conventionnelles"]),
    ("CCAM", ["ccam", "codage", "nomenclature"]),
]

NOISE_RE = re.compile(
    r"(Javascript est désactivé|Vous utilisez un navigateur obsolète|Retour en haut de page|Partager cette page|Cet article vous a-t-il été utile.*$)",
    re.I | re.S,
)
CODE_RE = re.compile(r"\b[A-Z]{4}\d{3}\b")


def now_fr() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS).isoformat(timespec="seconds")


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def slugify(text: str) -> str:
    replacements = str.maketrans("éèêëàâäçîïôöùûüÿñ", "eeeeaaaciioouuuyn")
    text = text.lower().translate(replacements)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:90] or "article"


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
            current = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    else:
        current = {}
    current["articles"] = {"status": status, "generated": now_fr(), **details}
    STATUS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_jina(url: str) -> str:
    reader_url = "https://r.jina.ai/" + url
    req = urllib.request.Request(
        reader_url,
        headers={
            "Accept": "text/plain; charset=utf-8",
            "User-Agent": "maidis-ccam-hub/1.0 (+https://github.com/famillecompte9583-dev/maidis-ccam-hub)",
            "x-respond-with": "markdown",
            "x-no-cache": "true",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def clean_markdown(text: str) -> str:
    text = NOISE_RE.sub(" ", text or "")
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def extract_title(markdown: str, fallback_url: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()[:180]
        if line.lower().startswith("title:"):
            return line.split(":", 1)[1].strip()[:180]
    return pathlib.Path(urllib.parse.urlparse(fallback_url).path).name.replace("-", " ").title()


def detect_category(title: str, text: str, fallback: str) -> str:
    low = f"{title} {text}".lower()
    for category, words in CATEGORY_RULES:
        if any(word in low for word in words):
            return category
    return fallback or "Dossier"


def relevant(text: str) -> bool:
    low = text.lower()
    return any(keyword in low for keyword in TOPIC_KEYWORDS)


def paragraphs(text: str) -> list[str]:
    out: list[str] = []
    for block in re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÉÈÀÂÎÔÙÇ])", text):
        value = re.sub(r"\s+", " ", block).strip(" -•\t")
        if 50 <= len(value) <= 1100:
            out.append(value)
    return out


def build_html(title: str, url: str, text: str, codes: list[str]) -> str:
    parts = paragraphs(text)
    intro = parts[:3]
    detail = parts[3:22]
    code_text = ", ".join(codes[:50]) if codes else "Aucun code CCAM explicite détecté dans le texte source."
    return "".join([
        "<p>Ce dossier est produit à partir du contenu Ameli extrait en Markdown via Jina Reader, puis destiné à être reformulé densément par Gemini.</p>",
        "<h2>Contenu extrait de la source</h2>",
        "".join(f"<p>{esc(p)}</p>" for p in intro),
        "<h2>Détails utiles extraits</h2>",
        "<ul>",
        "".join(f"<li>{esc(p)}</li>" for p in detail[:14]),
        "</ul>",
        "<h2>Codes CCAM explicitement détectés</h2>",
        f"<p>{esc(code_text)}</p>",
        "<h2>Source et traçabilité</h2>",
        f"<p>Source officielle : <a href=\"{esc(url)}\" target=\"_blank\" rel=\"noopener noreferrer\">{esc(title)}</a>. Texte extrait : {len(text)} caractères. Généré le {esc(now_fr())}.</p>",
    ])


def make_article(source: dict[str, str], record_codes: set[str]) -> dict[str, Any] | None:
    url = source["url"]
    raw = fetch_jina(url)
    text = clean_markdown(raw)
    if len(text) < MIN_TEXT_CHARS or not relevant(text):
        return None
    title = extract_title(text, url)
    category = detect_category(title, text, source.get("category", "Dossier"))
    detected_codes = sorted(set(CODE_RE.findall(text)) & record_codes)
    return {
        "id": slugify(title),
        "title": title,
        "date": dt.date.today().isoformat(),
        "source": "Ameli",
        "source_url": url,
        "category": category,
        "tag": category,
        "summary": f"Dossier issu du contenu Ameli extrait en Markdown ({len(text)} caractères), destiné à une reformulation dense et fidèle par Gemini.",
        "content_html": build_html(title, url, text, detected_codes),
        "codes": detected_codes[:80],
        "codes_detectes": detected_codes[:180],
        "extracted_chars": len(text),
        "source_text_excerpt": text[:SOURCE_TEXT_LIMIT],
        "confidence": "Haute" if len(text) > 2500 else "Moyenne",
        "generation": {
            "mode": "jina-reader-markdown",
            "generated": now_fr(),
            "text_chars": len(text),
            "grounding": "ameli_public_page_converted_to_markdown_by_jina_reader",
        },
    }


def link_articles_to_records(app: dict[str, Any]) -> None:
    link_map: dict[str, list[str]] = {}
    for article in app.get("articles", []):
        for code in article.get("codes", []):
            link_map.setdefault(code, []).append(article["id"])
    for record in app.get("records", []):
        code = record.get("code")
        if code in link_map:
            record["articles_lies"] = link_map[code][:8]
        elif "articles_lies" in record:
            record.pop("articles_lies", None)


def main() -> None:
    app = load_app()
    records = app.get("records", [])
    record_codes = {r.get("code") for r in records if isinstance(r, dict) and isinstance(r.get("code"), str)}
    articles: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()

    for source in AMELI_SOURCES[:MAX_ARTICLES]:
        try:
            article = make_article(source, record_codes)
            if article and article["id"] not in seen:
                articles.append(article)
                seen.add(article["id"])
            time.sleep(0.8)
        except Exception as exc:
            errors.append({"url": source["url"], "error": f"{type(exc).__name__}: {exc}"})

    app["articles"] = articles
    app.setdefault("meta", {})["articles"] = len(articles)
    app["meta"]["article_generation"] = {
        "mode": "jina-reader-markdown",
        "generated": now_fr(),
        "pages_scanned": len(AMELI_SOURCES[:MAX_ARTICLES]),
        "articles_generated": len(articles),
        "errors": errors[:8],
        "description": "Articles générés depuis des pages Ameli publiques converties en Markdown par Jina Reader, puis relus par Gemini.",
    }
    link_articles_to_records(app)
    save_app(app)
    update_status("ok" if articles else "empty", {
        "count": len(articles),
        "mode": "jina-reader-markdown",
        "pages_scanned": len(AMELI_SOURCES[:MAX_ARTICLES]),
        "total_extracted_chars": sum(int(a.get("extracted_chars", 0)) for a in articles),
        "errors": errors[:8],
        "message": "Articles Ameli extraits via Jina Reader. Codes liés uniquement si explicitement détectés.",
    })
    print(f"Articles Jina générés : {len(articles)} ; erreurs : {len(errors)}")


if __name__ == "__main__":
    main()
