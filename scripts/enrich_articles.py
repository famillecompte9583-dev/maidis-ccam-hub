#!/usr/bin/env python3
"""Enrichissement éditorial autonome pour Annuaire CCAM Santé.

Ce script complète la génération CCAM :
- il lit data/app-data.json déjà produit par update_all.py ;
- il explore un périmètre Ameli ciblé autour de la CCAM, du dentaire, des tarifs et du 100 % Santé ;
- il extrait le contenu utile des pages et documents PDF accessibles ;
- il reformule ce contenu en dossiers courts de type blog, sans recopier intégralement les pages sources ;
- il relie les dossiers aux codes CCAM détectés ou pertinents ;
- il réécrit data/app-data.json et data/app-data.js.
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
from typing import Any
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache" / "pdf"
PARIS = ZoneInfo("Europe/Paris")

MAX_PAGES = 28
MAX_PDFS_PER_PAGE = 4
MAX_ARTICLES = 18

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36",
]

SEEDS = [
    "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam",
    "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028",
    "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles",
    "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs",
    "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire",
]

TOPIC_KEYWORDS = [
    "ccam", "codage", "actes", "nomenclature", "tarifs", "convention", "honoraires",
    "remuneration", "facturation", "100-sante", "100-santé", "prothetiques", "prothétiques",
    "dentaire", "chirurgien-dentiste", "prise-charge", "panier", "devis",
]

CATEGORY_RULES = [
    ("100 % Santé", ["100", "sante", "santé", "panier", "prothet"]),
    ("Tarifs", ["tarif", "honoraire", "remuneration", "rémunération"]),
    ("Dentaire", ["dentaire", "dentiste", "prothese", "prothèse"]),
    ("Convention", ["convention", "avenant", "calendrier"]),
    ("CCAM", ["ccam", "codage", "nomenclature"]),
]

STOP_SNIPPETS = [
    "Javascript est désactivé",
    "Vous utilisez un navigateur obsolète",
    "accepter les cookies",
    "Accueil",
]


def now_fr() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS).isoformat(timespec="seconds")


def fetch(url: str, timeout: int = 35, retries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/pdf,*/*",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.4",
                "Cache-Control": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in {403, 408, 409, 425, 429, 500, 502, 503, 504}:
                raise
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(min(2**attempt, 8) + random.random())
    raise last or RuntimeError(url)


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def slugify(text: str) -> str:
    text = text.lower()
    text = text.replace("é", "e").replace("è", "e").replace("ê", "e").replace("à", "a").replace("ç", "c")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:90] or "article"


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def is_relevant_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc != "www.ameli.fr":
        return False
    path = parsed.path.lower()
    if not (path.startswith("/medecin/") or path.startswith("/chirurgien-dentiste/")):
        return False
    return any(k in path for k in TOPIC_KEYWORDS)


def extract_links(page_url: str, source: str) -> list[str]:
    links = []
    for match in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"']", source, flags=re.I):
        href = html.unescape(match.group(1).strip())
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        url = normalize_url(urllib.parse.urljoin(page_url, href))
        if is_relevant_url(url):
            links.append(url)
    return list(dict.fromkeys(links))


def extract_pdf_links(page_url: str, source: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    pattern = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+\.pdf(?:\?[^\"']*)?)[\"'][^>]*>(?P<title>.*?)</a>", re.I | re.S)
    for match in pattern.finditer(source):
        url = urllib.parse.urljoin(page_url, html.unescape(match.group("href").strip()))
        title = re.sub(r"<[^>]+>", " ", match.group("title"))
        title = re.sub(r"\s+", " ", html.unescape(title)).strip() or pathlib.Path(urllib.parse.urlparse(url).path).name
        if url not in seen:
            out.append((title, url))
            seen.add(url)
    return out


def clean_html(source: str) -> str:
    source = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<(nav|footer|header|aside|form)\b.*?</\1>", " ", source, flags=re.I | re.S)
    source = re.sub(r"<(h[1-4]|p|li|td|th|article|section|div)\b[^>]*>", "\n", source, flags=re.I)
    source = re.sub(r"<[^>]+>", " ", source)
    source = html.unescape(source)
    for junk in STOP_SNIPPETS:
        source = source.replace(junk, " ")
    source = re.sub(r"\s+", " ", source).strip()
    return source


def extract_title(source: str, fallback_url: str) -> str:
    for pattern in [r"<h1[^>]*>(.*?)</h1>", r"<title[^>]*>(.*?)</title>"]:
        match = re.search(pattern, source, flags=re.I | re.S)
        if match:
            title = re.sub(r"<[^>]+>", " ", match.group(1))
            title = re.sub(r"\s+", " ", html.unescape(title)).strip()
            title = re.sub(r"\s*\|\s*ameli.*$", "", title, flags=re.I)
            if title:
                return title
    return pathlib.Path(urllib.parse.urlparse(fallback_url).path).name.replace("-", " ").title()


def sentence_candidates(text: str) -> list[str]:
    sentences: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = re.sub(r"\s+", " ", sentence).strip()
        low = s.lower()
        if 70 <= len(s) <= 340 and any(k.replace("-", " ") in low for k in TOPIC_KEYWORDS):
            sentences.append(s)
    return sentences


def codes_in(text: str) -> list[str]:
    return sorted(set(re.findall(r"\b[A-Z]{4}\d{3}\b", text or "")))


def detect_category(title: str, text: str) -> str:
    low = f"{title} {text}".lower()
    for category, words in CATEGORY_RULES:
        if any(word in low for word in words):
            return category
    return "Dossier"


def rewrite_summary(title: str, category: str, sentences: list[str], codes: list[str]) -> str:
    if category == "100 % Santé":
        return "Ce dossier explique les points utiles autour du 100 % Santé dentaire, des paniers de soins, des actes concernés et des vérifications à effectuer avant facturation."
    if category == "Tarifs":
        return "Ce dossier synthétise les informations utiles sur les tarifs conventionnels, la BRSS, les honoraires limites et les contrôles à réaliser dans un outil métier."
    if category == "Convention":
        return "Ce dossier reprend les éléments pratiques liés à la convention et les transforme en repères opérationnels pour le suivi des actes et du paramétrage."
    if category == "Dentaire":
        return "Ce dossier rassemble les informations utiles aux actes bucco-dentaires, aux prothèses, aux paniers et aux points de vigilance de prise en charge."
    if codes:
        return f"Ce dossier met en relation la source Ameli avec {len(codes)} code(s) CCAM détecté(s) afin de faciliter le contrôle et la recherche dans l’annuaire."
    return f"Ce dossier reformule les informations utiles de la source suivie afin de les rendre plus lisibles dans l’annuaire."


def build_blog_html(title: str, url: str, category: str, text: str, sentences: list[str], codes: list[str], pdfs: list[dict[str, Any]]) -> str:
    points = sentences[:5]
    if not points:
        points = [
            "La source a été suivie automatiquement et intégrée dans la veille de l’annuaire.",
            "Les informations doivent être rapprochées de la base CCAM, du contexte patient et des règles de facturation applicables.",
            "Les liens officiels restent prioritaires pour toute validation réglementaire.",
        ]
    paragraphs = []
    paragraphs.append(f"<p>Ce dossier transforme une source Ameli en article pratique. L’objectif n’est pas de recopier la page officielle, mais d’en extraire les points utiles pour la recherche d’actes, la facturation et le paramétrage.</p>")
    paragraphs.append("<h2>Ce qu’il faut comprendre</h2><ul>" + "".join(f"<li>{esc(p)}</li>" for p in points) + "</ul>")
    paragraphs.append("<h2>Lecture métier</h2>")
    if category == "100 % Santé":
        paragraphs.append("<p>La lecture doit se faire en croisant l’acte, le matériau, la localisation, le panier de soins et le contexte du patient. Les codes liés sont proposés comme aide de recherche, pas comme décision automatique.</p>")
    elif category == "Tarifs":
        paragraphs.append("<p>Les tarifs et bases de remboursement servent au contrôle. Ils doivent être vérifiés avec la situation réelle du patient, les majorations, exonérations et règles conventionnelles applicables.</p>")
    elif category == "Convention":
        paragraphs.append("<p>Les mesures conventionnelles doivent être traduites en points de contrôle : actes concernés, dates d’application, panier éventuel, devis et cohérence du paramétrage.</p>")
    else:
        paragraphs.append("<p>Le contenu est classé pour aider à retrouver les informations utiles sans mélanger les données officielles, les déductions automatiques et les points à contrôler manuellement.</p>")
    paragraphs.append("<h2>Codes CCAM repérés ou associés</h2>")
    paragraphs.append(f"<p>{esc(', '.join(codes[:120])) if codes else 'Aucun code CCAM explicite n’a été détecté dans cette source. Le dossier reste utile comme repère de veille.'}</p>")
    if pdfs:
        paragraphs.append("<h2>Documents associés détectés</h2><ul>" + "".join(f"<li>{esc(p['title'])} — {len(p.get('codes', []))} code(s) repéré(s)</li>" for p in pdfs[:6]) + "</ul>")
    paragraphs.append("<h2>Source et traçabilité</h2>")
    paragraphs.append(f"<p>Source officielle suivie : <a href=\"{esc(url)}\" target=\"_blank\" rel=\"noopener\">{esc(title)}</a>. Texte exploité : {len(text)} caractères. Article généré automatiquement le {now_fr()}.</p>")
    return "".join(paragraphs)


def pdf_filename(url: str) -> str:
    name = pathlib.Path(urllib.parse.urlparse(url).path).name or "document.pdf"
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def pdf_text(url: str) -> tuple[str, list[str]]:
    try:
        content = fetch(url, timeout=30, retries=2)
        if not content.startswith(b"%PDF"):
            return "", []
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = CACHE_DIR / pdf_filename(url)
        path.write_bytes(content)
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                text = " ".join((page.extract_text() or "") for page in pdf.pages[:8])
            text = re.sub(r"\s+", " ", text).strip()
            return text, codes_in(text)
        except Exception:
            return "", []
    except Exception:
        return "", []


def crawl_ameli() -> list[dict[str, Any]]:
    queue = [normalize_url(url) for url in SEEDS]
    seen: set[str] = set()
    pages: list[dict[str, Any]] = []
    while queue and len(pages) < MAX_PAGES:
        url = queue.pop(0)
        if url in seen or not is_relevant_url(url):
            continue
        seen.add(url)
        try:
            raw = fetch(url).decode("utf-8", errors="ignore")
            title = extract_title(raw, url)
            text = clean_html(raw)
            if len(text) < 250:
                continue
            pdf_items = []
            merged_text = text
            code_set = set(codes_in(text))
            for pdf_title, pdf_url in extract_pdf_links(url, raw)[:MAX_PDFS_PER_PAGE]:
                ptext, pcodes = pdf_text(pdf_url)
                if ptext:
                    merged_text += " " + ptext[:4000]
                code_set.update(pcodes)
                pdf_items.append({"title": pdf_title, "url": pdf_url, "codes": pcodes[:80]})
            category = detect_category(title, merged_text)
            sentences = sentence_candidates(merged_text)
            codes = sorted(code_set)
            pages.append({
                "id": slugify(title),
                "title": title,
                "date": dt.date.today().isoformat(),
                "source": "Ameli",
                "source_url": url,
                "category": category,
                "tag": category,
                "summary": rewrite_summary(title, category, sentences, codes),
                "content_html": build_blog_html(title, url, category, merged_text, sentences, codes, pdf_items),
                "codes": codes[:120],
                "codes_detectes": codes[:180],
                "pdf_count": len(pdf_items),
                "extracted_chars": len(merged_text),
                "confidence": "Haute" if len(merged_text) > 1200 else "Moyenne",
            })
            for link in extract_links(url, raw):
                if link not in seen and link not in queue and len(queue) < 80:
                    queue.append(link)
        except Exception as exc:  # noqa: BLE001
            print(f"Page Ameli ignorée {url}: {exc}")
    return pages[:MAX_ARTICLES]


def enrich_article_codes(articles: list[dict[str, Any]], records: list[dict[str, Any]]) -> None:
    existing = {r.get("code") for r in records if r.get("code")}
    dental_codes = [r["code"] for r in records if r.get("domaine") != "Médical CCAM"][:90]
    medical_codes = [r["code"] for r in records if r.get("domaine") == "Médical CCAM"][:90]
    rac_codes = [r["code"] for r in records if str(r.get("panier_100_sante", "")).startswith(("RAC 0", "RAC mod"))][:120]
    for article in articles:
        codes = [c for c in article.get("codes", []) if c in existing]
        cat = article.get("category", "")
        if len(codes) < 5:
            if cat == "100 % Santé":
                codes.extend(rac_codes)
            elif cat in {"Dentaire", "Tarifs", "Convention"}:
                codes.extend(dental_codes)
            elif cat == "CCAM":
                codes.extend(medical_codes)
        article["codes"] = sorted(dict.fromkeys(codes))[:120]


def link_articles_to_records(app: dict[str, Any]) -> None:
    link_map: dict[str, list[str]] = {}
    for article in app.get("articles", []):
        for code in article.get("codes", []):
            link_map.setdefault(code, []).append(article["id"])
    for record in app.get("records", []):
        code = record.get("code")
        if code in link_map:
            record["articles_lies"] = link_map[code][:8]


def main() -> None:
    data_path = DATA_DIR / "app-data.json"
    if not data_path.exists() or data_path.stat().st_size == 0:
        raise SystemExit("data/app-data.json absent ou vide : lancez d’abord scripts/update_all.py")
    app = json.loads(data_path.read_text(encoding="utf-8"))
    records = app.get("records", [])
    articles = crawl_ameli()
    enrich_article_codes(articles, records)
    app["articles"] = articles
    app.setdefault("meta", {})["articles"] = len(articles)
    app["meta"]["article_generation"] = {
        "mode": "ameli-crawl-blog",
        "generated": now_fr(),
        "pages_scanned": len(articles),
        "max_pages": MAX_PAGES,
        "description": "Articles reformulés automatiquement depuis les pages Ameli suivies et leurs PDF liés.",
    }
    link_articles_to_records(app)
    DATA_DIR.mkdir(exist_ok=True)
    data_path.write_text(json.dumps(app, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "app-data.js").write_text("window.CCAM_APP_DATA = " + json.dumps(app, ensure_ascii=False) + ";\n", encoding="utf-8")
    status_path = DATA_DIR / "sync-status.json"
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            status = {}
    else:
        status = {}
    status["articles"] = {"status": "ok", "generated": now_fr(), "count": len(articles), "mode": "ameli-crawl-blog"}
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Articles générés depuis Ameli : {len(articles)}")


if __name__ == "__main__":
    main()
