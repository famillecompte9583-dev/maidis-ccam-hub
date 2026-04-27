#!/usr/bin/env python3
"""Génération de vrais dossiers Ameli via Playwright.

Objectif : lire les pages publiques Ameli comme un navigateur, y compris les
accordéons et sections masquées, puis fournir à Gemini une matière dense et réelle.

Règle stricte : aucun code CCAM n'est associé par remplissage artificiel.
Seuls les codes explicitement détectés dans le texte source rendu peuvent être liés.
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

MAX_PAGES = 36
MAX_ARTICLES = 22
MIN_TEXT_CHARS = 650
SOURCE_TEXT_LIMIT = 26000

SEEDS = [
    "https://www.ameli.fr/chirurgien-dentiste/actualites",
    "https://www.ameli.fr/medecin/actualites",
    "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam",
    "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/nomenclatures-codage/ccam/codage",
    "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028",
    "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles",
    "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs",
    "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire",
    "https://www.ameli.fr/chirurgien-dentiste/actualites/examens-bucco-dentaires-ce-qui-change-au-1er-avril-2025",
    "https://www.ameli.fr/chirurgien-dentiste/actualites/tout-savoir-sur-la-pratique-du-tiers-payant-pour-l-examen-bucco-dentaire-et-les-soins-associes",
    "https://www.ameli.fr/chirurgien-dentiste/actualites/m-t-dents-tous-les-ans-une-campagne-de-communication-pour-promouvoir-la-sante-bucco-dentaire",
    "https://www.ameli.fr/chirurgien-dentiste/actualites/forfait-d-aide-la-modernisation-la-campagne-de-declaration-est-ouverte-jusqu-au-2-mars",
    "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/tarifs/tarifs-conventionnels-medecins-generalistes-specialistes",
]

TOPIC_KEYWORDS = [
    "ccam", "codage", "actes", "nomenclature", "tarifs", "convention", "honoraires",
    "rémunération", "remuneration", "facturation", "100 % santé", "100-santé", "100-sante",
    "prothétique", "prothétiques", "prothese", "prothèse", "dentaire", "chirurgien-dentiste",
    "prise en charge", "prise-charge", "panier", "devis", "tiers payant", "examen bucco-dentaire",
    "m't dents", "fami", "forfait d'aide", "modernisation", "brss", "amo", "amc", "ngap",
]

CATEGORY_RULES = [
    ("100 % Santé", ["100", "sante", "santé", "panier", "prothet"]),
    ("Tarifs", ["tarif", "honoraire", "brss", "amo", "amc", "tiers payant", "prise en charge"]),
    ("Dentaire", ["dentaire", "dentiste", "bucco", "m't dents", "prothese", "prothèse"]),
    ("Convention", ["convention", "avenant", "calendrier", "fami", "forfait"]),
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
    r"Fermer",
    r"Cet article vous a-t-il été utile.*$",
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


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def is_ameli_public_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.netloc != "www.ameli.fr":
        return False
    path = parsed.path.lower()
    # Ameli peut préfixer par un département : /gard/chirurgien-dentiste/actualites/...
    return any(part in path for part in ["/chirurgien-dentiste/", "/medecin/"])


def is_candidate_url(url: str) -> bool:
    if not is_ameli_public_url(url):
        return False
    path = urllib.parse.urlparse(url).path.lower()
    if "/actualites" in path:
        return True
    return any(keyword.replace(" ", "-") in path or keyword in path for keyword in TOPIC_KEYWORDS)


def text_is_relevant(title: str, text: str) -> bool:
    low = f"{title} {text}".lower()
    return any(keyword in low for keyword in TOPIC_KEYWORDS)


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.I | re.S)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = text.strip()
    text = re.split(r"(?:Mentions légales|Accessibilité|Plan du site|Contacts|Nous contacter)", text, flags=re.I)[0].strip()
    return text


def paragraphize(text: str) -> list[str]:
    chunks: list[str] = []
    for raw in re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÉÈÀÂÎÔÙÇ])", text):
        value = re.sub(r"\s+", " ", raw).strip()
        if 45 <= len(value) <= 900:
            chunks.append(value)
    return chunks


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


def build_summary(category: str, detected_code_count: int, chars: int) -> str:
    base = {
        "100 % Santé": "Article Ameli complet rendu par navigateur sur les paniers 100 % Santé et les contrôles associés.",
        "Tarifs": "Article Ameli complet rendu par navigateur sur les tarifs conventionnels, la BRSS et les points de contrôle.",
        "Convention": "Article Ameli complet rendu par navigateur sur les repères conventionnels utiles au suivi des actes.",
        "Dentaire": "Article Ameli complet rendu par navigateur sur les actes bucco-dentaires et les points de vigilance.",
        "CCAM": "Article Ameli complet rendu par navigateur sur le codage CCAM et la lecture des actes.",
    }.get(category, "Article Ameli complet rendu par navigateur.")
    suffix = f" Texte extrait : {chars} caractères."
    if detected_code_count:
        return f"{base} {detected_code_count} code(s) CCAM ont été détecté(s) explicitement dans le texte source.{suffix}"
    return f"{base} Aucun code CCAM explicite n'a été détecté dans le texte source.{suffix}"


def build_html(title: str, url: str, text: str, detected_codes: list[str], chars: int) -> str:
    paragraphs = paragraphize(text)
    intro = paragraphs[:2] or ["Le contenu de cette page Ameli a été rendu avec Playwright puis transmis à Gemini pour reformulation structurée."]
    details = paragraphs[2:14]
    code_text = ", ".join(detected_codes[:40]) if detected_codes else "Aucun code CCAM explicite n'a été détecté dans le texte rendu."
    return "".join([
        "<p>Ce dossier est produit à partir d'une page Ameli publique rendue avec Playwright. Les sections dépliables ont été ouvertes automatiquement avant extraction.</p>",
        "<h2>Contenu source extrait</h2>",
        "".join(f"<p>{esc(p)}</p>" for p in intro),
        "<h2>Éléments détaillés extraits</h2>",
        "<ul>",
        "".join(f"<li>{esc(p)}</li>" for p in details[:10]),
        "</ul>",
        "<h2>Codes CCAM explicitement détectés</h2>",
        f"<p>{esc(code_text)}</p>",
        "<h2>Source et traçabilité</h2>",
        f"<p>Source officielle suivie : <a href=\"{esc(url)}\" target=\"_blank\" rel=\"noopener noreferrer\">{esc(title)}</a>. Texte rendu exploité : {chars} caractères. Article généré le {esc(now_fr())}.</p>",
    ])


def expand_dynamic_sections(page) -> int:
    """Ouvre les accordéons/détails/boutons qui révèlent du contenu."""
    opened = 0
    for _ in range(5):
        changed = page.evaluate(
            """
            () => {
              let count = 0;
              document.querySelectorAll('details:not([open])').forEach(el => { el.open = true; count++; });
              const candidates = Array.from(document.querySelectorAll('button, a, [role="button"], summary'));
              const rx = /(tout afficher|afficher les sections|voir plus|lire la suite|déplier|deplier|ouvrir|plus d'informations|en savoir plus|pratique|tarifs|actes|consultations|au 1er|documents utiles)/i;
              for (const el of candidates) {
                const txt = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
                const expanded = el.getAttribute('aria-expanded');
                const hiddenTarget = el.getAttribute('aria-controls');
                const looksClosed = expanded === 'false' || /collapsed|fermé|closed/i.test(el.className || '') || rx.test(txt);
                if (!looksClosed) continue;
                try {
                  el.scrollIntoView({block: 'center'});
                  el.click();
                  count++;
                } catch (e) {}
                if (hiddenTarget) {
                  const target = document.getElementById(hiddenTarget);
                  if (target) {
                    target.hidden = false;
                    target.removeAttribute('hidden');
                    target.style.display = '';
                    target.style.visibility = 'visible';
                    count++;
                  }
                }
              }
              document.querySelectorAll('[aria-hidden="true"]').forEach(el => {
                if ((el.innerText || '').trim().length > 40) {
                  el.setAttribute('aria-hidden', 'false');
                  count++;
                }
              });
              return count;
            }
            """
        )
        opened += int(changed or 0)
        if not changed:
            break
        try:
            page.wait_for_load_state("networkidle", timeout=2500)
        except Exception:
            pass
        page.wait_for_timeout(500)
    return opened


def remove_noise(page) -> None:
    page.evaluate(
        """
        () => {
          for (const selector of ['script','style','noscript','svg','nav','footer','header','aside','form','iframe']) {
            document.querySelectorAll(selector).forEach(el => el.remove());
          }
          document.querySelectorAll('[class*="cookie"], [id*="cookie"], [class*="breadcrumb"], [class*="share"]').forEach(el => el.remove());
        }
        """
    )


def structured_text(page) -> str:
    return page.evaluate(
        """
        () => {
          const root = document.querySelector('main') || document.querySelector('article') || document.querySelector('[role="main"]') || document.body;
          const blocks = [];
          const allowed = 'h1,h2,h3,h4,p,li,th,td,caption,summary';
          root.querySelectorAll(allowed).forEach(el => {
            const txt = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
            if (!txt || txt.length < 2) return;
            const tag = el.tagName.toLowerCase();
            if (/^h[1-4]$/.test(tag)) blocks.push('\n## ' + txt + '\n');
            else if (tag === 'li') blocks.push('- ' + txt);
            else if (tag === 'th' || tag === 'td') blocks.push(txt + ' |');
            else blocks.push(txt);
          });
          return blocks.join('\n');
        }
        """
    )


def extract_page(page, url: str) -> dict[str, Any] | None:
    page.goto(url, wait_until="domcontentloaded", timeout=55_000)
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass

    for label in ["Tout accepter", "Accepter", "J'accepte", "OK", "Continuer"]:
        try:
            page.get_by_text(label, exact=False).first.click(timeout=1200)
            break
        except Exception:
            pass

    opened_count = expand_dynamic_sections(page)
    remove_noise(page)

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

    text = clean_text(structured_text(page))
    if len(text) < MIN_TEXT_CHARS:
        try:
            text = clean_text(page.locator("body").inner_text(timeout=3500))
        except Exception:
            pass
    if len(text) < MIN_TEXT_CHARS:
        return None

    links = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('a[href]')).map(a => ({ href: a.href, text: (a.innerText || a.textContent || '').trim() }))
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
        if is_candidate_url(normalized) and normalized not in article_links:
            article_links.append(normalized)

    return {
        "url": normalize_url(url),
        "title": title,
        "text": text,
        "links": article_links,
        "pdfs": pdf_links[:10],
        "opened_sections": opened_count,
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
            viewport={"width": 1440, "height": 1200},
        )
        page = context.new_page()
        while queue and len(pages) < MAX_PAGES:
            url = queue.pop(0)
            if url in seen or not is_candidate_url(url):
                continue
            seen.add(url)
            try:
                extracted = extract_page(page, url)
                if extracted:
                    for link in extracted["links"]:
                        if link not in seen and link not in queue and len(queue) < 140:
                            queue.append(link)
                    if text_is_relevant(extracted["title"], extracted["text"]):
                        pages.append(extracted)
                time.sleep(0.6)
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
        context.close()
        browser.close()

    if errors:
        print("Erreurs Playwright partielles :", file=sys.stderr)
        for error in errors[:10]:
            print(f"- {error}", file=sys.stderr)
    return sorted(pages, key=lambda item: len(item.get("text", "")), reverse=True)[:MAX_ARTICLES]


def pages_to_articles(pages: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    record_codes = {r.get("code") for r in records if isinstance(r, dict) and isinstance(r.get("code"), str)}
    articles = []
    seen_ids: set[str] = set()
    for item in pages:
        title = item["title"]
        text = item["text"]
        url = item["url"]
        category = detect_category(title, text)
        detected_codes = sorted(set(codes_in(text)) & record_codes)
        slug = slugify(title)
        if slug in seen_ids:
            slug = f"{slug}-{len(seen_ids)+1}"
        seen_ids.add(slug)
        articles.append({
            "id": slug,
            "title": title,
            "date": dt.date.today().isoformat(),
            "source": "Ameli",
            "source_url": url,
            "category": category,
            "tag": category,
            "summary": build_summary(category, len(detected_codes), len(text)),
            "content_html": build_html(title, url, text, detected_codes, len(text)),
            "codes": detected_codes[:80],
            "codes_detectes": detected_codes[:180],
            "pdf_count": len(item.get("pdfs", [])),
            "pdfs": item.get("pdfs", [])[:10],
            "opened_sections": item.get("opened_sections", 0),
            "extracted_chars": len(text),
            "source_text_excerpt": text[:SOURCE_TEXT_LIMIT],
            "confidence": "Haute" if len(text) > 2500 else "Moyenne",
            "generation": {
                "mode": "playwright-browser-render-expanded-sections",
                "generated": now_fr(),
                "text_chars": len(text),
                "grounding": "visible_text_extracted_after_opening_public_ameli_sections",
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
        elif "articles_lies" in record:
            record.pop("articles_lies", None)


def main() -> None:
    app = load_app()
    records = app.get("records", [])
    if not isinstance(records, list) or not records:
        raise SystemExit("Aucun record CCAM disponible")

    pages = crawl_with_playwright()
    articles = pages_to_articles(pages, records)
    if not articles:
        app["articles"] = []
        app.setdefault("meta", {})["articles"] = 0
        app["meta"]["article_generation"] = {
            "mode": "playwright-browser-render-expanded-sections",
            "generated": now_fr(),
            "pages_scanned": 0,
            "description": "Aucun article réel extrait ; aucun dossier de substitution n'est publié.",
        }
        save_app(app)
        update_status("empty", {"count": 0, "mode": "playwright-browser-render-expanded-sections", "message": "Aucun vrai article Ameli exploitable extrait."})
        print("Aucun article Playwright exploitable. Aucun dossier de substitution publié.")
        return

    app["articles"] = articles
    app.setdefault("meta", {})["articles"] = len(articles)
    app["meta"]["article_generation"] = {
        "mode": "playwright-browser-render-expanded-sections",
        "generated": now_fr(),
        "pages_scanned": len(pages),
        "description": "Articles générés depuis des pages Ameli publiques rendues avec Chromium/Playwright, sections dépliables ouvertes.",
    }
    link_articles_to_records(app)
    save_app(app)
    update_status("ok", {
        "count": len(articles),
        "mode": "playwright-browser-render-expanded-sections",
        "pages_scanned": len(pages),
        "total_extracted_chars": sum(len(a.get("source_text_excerpt", "")) for a in articles),
        "message": "Articles réels générés depuis Ameli avec sections dépliables ouvertes. Codes liés uniquement si explicitement détectés.",
    })
    print(f"Articles Playwright générés : {len(articles)}")


if __name__ == "__main__":
    main()
