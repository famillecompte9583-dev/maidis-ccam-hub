#!/usr/bin/env python3
"""Génération de vrais dossiers Ameli via Playwright.

Pourquoi ce script existe :
- urllib peut recevoir une page incomplète, filtrée ou trop dépendante du JS ;
- Playwright rend la page comme un navigateur Chromium headless ;
- on extrait ensuite le texte visible et les liens utiles ;
- Gemini peut relire de vrais contenus au lieu d'un dossier de secours.

Le script reste prudent : il ne contourne pas d'authentification, ne force pas de zone
privée et se limite aux pages publiques Ameli ciblées.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
import sys
import time
import urllib.parse
from typing import Any
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APP_PATH = DATA_DIR / "app-data.json"
STATUS_PATH = DATA_DIR / "sync-status.json"
PARIS = ZoneInfo("Europe/Paris")

MAX_PAGES = 20
MAX_ARTICLES = 14
MIN_TEXT_CHARS = 450

SEEDS = [
    "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam",
    "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028",
    "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles",
    "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs",
    "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire",
]

TOPIC_KEYWORDS = [
    "ccam", "codage", "actes", "nomenclature", "tarifs", "convention", "honoraires",
    "remuneration", "rémunération", "facturation", "100-sante", "100-santé", "prothetiques",
    "prothétiques", "dentaire", "chirurgien-dentiste", "prise-charge", "panier", "devis",
]

CATEGORY_RULES = [
    ("100 % Santé", ["100", "sante", "santé", "panier", "prothet"]),
    ("Tarifs", ["tarif", "honoraire", "remuneration", "rémunération"]),
    ("Dentaire", ["dentaire", "dentiste", "prothese", "prothèse"]),
    ("Convention", ["convention", "avenant", "calendrier"]),
    ("CCAM", ["ccam", "codage", "nomenclature"]),
]

NOISE_PATTERNS = [
    r"Javascript est désactivé",
    r"Vous utilisez un navigateur obsolète",
    r"Accepter les cookies",
    r"Gestion des cookies",
    r"Menu principal",
    r"Fil d'Ariane",
    r"Partager cette page",
    r"Retour en haut de page",
]


def now_fr() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS).isoformat(timespec="seconds")


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def load_app() -> dict[str, Any]:
    if not APP_PATH.exists() or APP_PATH.stat().st_size == 0:
        raise SystemExit("data/app-data.json absent ou vide : lancez d'abord scripts/update_all.py")
    return json.loads(APP_PATH.read_text(encoding="utf-8"))


def save_app(app: dict[str, Any]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    APP_PATH.write_text(json.dumps(app, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "app-data.js").write_text(
        "window.CCAM_APP_DATA = " + json.dumps(app, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )


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
    return any(keyword in path for keyword in TOPIC_KEYWORDS)


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    # Certaines pages répètent beaucoup de menus. On coupe avant des blocs de pied de page typiques.
    text = re.split(r"(?:Mentions légales|Accessibilité|Plan du site|Contacts|Nous contacter)", text, flags=re.I)[0].strip()
    return text


def sentence_candidates(text: str, limit: int = 7) -> list[str]:
    sentences: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        s = re.sub(r"\s+", " ", sentence).strip()
        low = s.lower()
        if 70 <= len(s) <= 380 and any(keyword.replace("-", " ") in low for keyword in TOPIC_KEYWORDS):
            sentences.append(s)
        if len(sentences) >= limit:
            break
    return sentences


def codes_in(text: str) -> list[str]:
    return sorted(set(re.findall(r"\b[A-Z]{4}\d{3}\b", text or "")))


def detect_category(title: str, text: str) -> str:
    low = f"{title} {text}".lower()
    for category, words in CATEGORY_RULES:
        if any(word in low for word in words):
            return category
    return "Dossier"


def slugify(text: str) -> str:
    replacements = str.maketrans("éèêëàâäçîïôöùûüÿñ", "eeeeaaaciioouuuyn")
    text = text.lower().translate(replacements)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:90] or "article"


def select_fallback_codes(records: list[dict[str, Any]], category: str, existing: set[str], limit: int = 80) -> list[str]:
    if existing:
        return sorted(existing)[:limit]
    out: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        code = record.get("code")
        if not isinstance(code, str) or code in out:
            continue
        domaine = str(record.get("domaine", ""))
        panier = str(record.get("panier_100_sante", ""))
        if category == "100 % Santé" and panier.startswith(("RAC 0", "RAC mod")):
            out.append(code)
        elif category in {"Tarifs", "Dentaire", "Convention"} and domaine != "Médical CCAM":
            out.append(code)
        elif category == "CCAM" and domaine == "Médical CCAM":
            out.append(code)
        if len(out) >= limit:
            break
    return out


def build_summary(category: str, codes: list[str]) -> str:
    if category == "100 % Santé":
        return "Synthèse issue d'une page Ameli rendue par navigateur sur les paniers 100 % Santé, les actes associés et les contrôles à effectuer."
    if category == "Tarifs":
        return "Synthèse issue d'une page Ameli rendue par navigateur sur les tarifs conventionnels, la BRSS et les points de contrôle avant facturation."
    if category == "Convention":
        return "Synthèse issue d'une page Ameli rendue par navigateur sur les repères conventionnels utiles au suivi des actes."
    if category == "Dentaire":
        return "Synthèse issue d'une page Ameli rendue par navigateur sur les actes bucco-dentaires et les points de vigilance de prise en charge."
    if codes:
        return f"Synthèse issue d'une page Ameli rendue par navigateur, reliée à {len(codes)} code(s) CCAM détecté(s) ou associés."
    return "Synthèse issue d'une page Ameli rendue par navigateur pour faciliter la lecture publique des informations suivies."


def build_html(title: str, url: str, category: str, text: str, sentences: list[str], codes: list[str], chars: int) -> str:
    if not sentences:
        sentences = [
            "La page officielle a été rendue par navigateur puis synthétisée pour faciliter la lecture dans l'annuaire.",
            "Les informations doivent être contrôlées avec la source officielle, la base CCAM et le contexte patient réel.",
            "L'annuaire sert d'aide à la recherche et au paramétrage, sans remplacer les textes opposables.",
        ]
    code_text = ", ".join(codes[:80]) if codes else "Aucun code CCAM explicite n'a été détecté dans le texte rendu."
    return "".join([
        "<p>Ce dossier est produit à partir d'une page Ameli publique rendue avec Playwright, puis nettoyée et structurée pour une lecture pratique.</p>",
        "<h2>Ce qu'il faut retenir</h2>",
        "<ul>",
        "".join(f"<li>{esc(sentence)}</li>" for sentence in sentences[:6]),
        "</ul>",
        "<h2>Lecture métier</h2>",
        "<p>Ces éléments aident à contrôler un acte, un tarif, un panier ou une mesure conventionnelle. Ils ne remplacent pas la source officielle, la situation réelle du patient ni le paramétrage du logiciel métier.</p>",
        "<h2>Codes CCAM repérés ou associés</h2>",
        f"<p>{esc(code_text)}</p>",
        "<h2>Source et traçabilité</h2>",
        f"<p>Source officielle suivie : <a href=\"{esc(url)}\" target=\"_blank\" rel=\"noopener noreferrer\">{esc(title)}</a>. Texte rendu exploité : {chars} caractères. Article généré le {esc(now_fr())}.</p>",
    ])


def extract_page(page, url: str) -> dict[str, Any] | None:
    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:
        pass

    for label in ["Tout accepter", "Accepter", "J'accepte", "OK", "Continuer"]:
        try:
            page.get_by_text(label, exact=False).first.click(timeout=1200)
            break
        except Exception:
            pass

    page.evaluate(
        """
        () => {
          for (const selector of ['script','style','noscript','svg','nav','footer','header','aside','form','iframe']) {
            document.querySelectorAll(selector).forEach(el => el.remove());
          }
        }
        """
    )

    title = ""
    for selector in ["h1", "title"]:
        try:
            value = page.locator(selector).first.inner_text(timeout=2500).strip()
            if value:
                title = re.sub(r"\s*\|\s*ameli.*$", "", value, flags=re.I).strip()
                break
        except Exception:
            pass
    if not title:
        title = pathlib.Path(urllib.parse.urlparse(url).path).name.replace("-", " ").title()

    text = ""
    for selector in ["main", "article", "[role=main]", ".main", ".content", "body"]:
        try:
            value = page.locator(selector).first.inner_text(timeout=3500)
            value = clean_text(value)
            if len(value) > len(text):
                text = value
        except Exception:
            pass
    if len(text) < MIN_TEXT_CHARS:
        return None

    links = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
          href: a.href,
          text: (a.innerText || a.textContent || '').trim()
        }))
        """
    )

    article_links: list[str] = []
    pdf_links: list[dict[str, str]] = []
    for link in links:
        href = str(link.get("href") or "")
        text_label = str(link.get("text") or pathlib.Path(urllib.parse.urlparse(href).path).name)
        if href.lower().split("?")[0].endswith(".pdf"):
            pdf_links.append({"title": text_label[:160] or "PDF Ameli", "url": href})
        normalized = normalize_url(href)
        if is_relevant_url(normalized) and normalized not in article_links:
            article_links.append(normalized)

    return {
        "url": normalize_url(url),
        "title": title,
        "text": text,
        "links": article_links,
        "pdfs": pdf_links[:8],
    }


def crawl_with_playwright() -> list[dict[str, Any]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise SystemExit(f"Playwright indisponible : {exc}")

    pages: list[dict[str, Any]] = []
    queue = [normalize_url(url) for url in SEEDS]
    seen: set[str] = set()
    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="fr-FR",
            timezone_id="Europe/Paris",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
            viewport={"width": 1365, "height": 900},
        )
        page = context.new_page()
        while queue and len(pages) < MAX_PAGES:
            url = queue.pop(0)
            if url in seen or not is_relevant_url(url):
                continue
            seen.add(url)
            try:
                extracted = extract_page(page, url)
                if extracted:
                    pages.append(extracted)
                    for link in extracted["links"]:
                        if link not in seen and link not in queue and len(queue) < 80:
                            queue.append(link)
                time.sleep(0.8)
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
        context.close()
        browser.close()

    if errors:
        print("Erreurs Playwright partielles :", file=sys.stderr)
        for error in errors[:8]:
            print(f"- {error}", file=sys.stderr)
    return pages[:MAX_ARTICLES]


def pages_to_articles(pages: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    record_codes = {r.get("code") for r in records if isinstance(r, dict) and isinstance(r.get("code"), str)}
    articles = []
    seen_ids: set[str] = set()
    for item in pages:
        title = item["title"]
        text = item["text"]
        url = item["url"]
        category = detect_category(title, text)
        detected_codes = set(codes_in(text)) & record_codes
        codes = select_fallback_codes(records, category, detected_codes)
        slug = slugify(title)
        if slug in seen_ids:
            slug = f"{slug}-{len(seen_ids)+1}"
        seen_ids.add(slug)
        sentences = sentence_candidates(text)
        articles.append({
            "id": slug,
            "title": title,
            "date": dt.date.today().isoformat(),
            "source": "Ameli",
            "source_url": url,
            "category": category,
            "tag": category,
            "summary": build_summary(category, codes),
            "content_html": build_html(title, url, category, text, sentences, codes, len(text)),
            "codes": codes[:120],
            "codes_detectes": sorted(detected_codes)[:180],
            "pdf_count": len(item.get("pdfs", [])),
            "pdfs": item.get("pdfs", [])[:8],
            "extracted_chars": len(text),
            "confidence": "Haute" if len(text) > 1600 else "Moyenne",
            "generation": {
                "mode": "playwright-browser-render",
                "generated": now_fr(),
                "text_chars": len(text),
            },
        })
    return articles


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
    app = load_app()
    records = app.get("records", [])
    if not isinstance(records, list) or not records:
        raise SystemExit("Aucun record CCAM disponible")

    pages = crawl_with_playwright()
    articles = pages_to_articles(pages, records)
    if not articles:
        update_status("empty", {
            "count": 0,
            "mode": "playwright-browser-render",
            "message": "Playwright n'a produit aucun article exploitable ; ensure_articles.py prendra le relais.",
        })
        print("Aucun article Playwright exploitable.")
        return

    app["articles"] = articles
    app.setdefault("meta", {})["articles"] = len(articles)
    app["meta"]["article_generation"] = {
        "mode": "playwright-browser-render",
        "generated": now_fr(),
        "pages_scanned": len(pages),
        "description": "Articles générés depuis des pages Ameli publiques rendues avec Chromium/Playwright.",
    }
    link_articles_to_records(app)
    save_app(app)
    update_status("ok", {
        "count": len(articles),
        "mode": "playwright-browser-render",
        "pages_scanned": len(pages),
        "message": "Articles réels générés depuis les pages Ameli rendues avec Playwright.",
    })
    print(f"Articles Playwright générés : {len(articles)}")


if __name__ == "__main__":
    main()
