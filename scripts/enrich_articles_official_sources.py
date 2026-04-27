#!/usr/bin/env python3
"""Veille médicale multi-sources officielles, sans dépendre d'Ameli.fr pro.

Règles publiques :
- uniquement des contenus récents ; par défaut depuis le 1er janvier de N-2 ;
- tri automatique par date décroissante ;
- aucune page anti-bot ;
- aucune fiche technique API dans les dossiers d'actualité.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APP_PATH = DATA_DIR / "app-data.json"
STATUS_PATH = DATA_DIR / "sync-status.json"
PARIS = ZoneInfo("Europe/Paris")

MAX_ARTICLES = 24
MAX_PER_SOURCE = 10
SOURCE_TEXT_LIMIT = 36000
MIN_TEXT_CHARS = 350
MIN_ARTICLE_YEAR = int(os.environ.get("MIN_ARTICLE_YEAR", str(dt.date.today().year - 2)))
MIN_ARTICLE_DATE = dt.date(MIN_ARTICLE_YEAR, 1, 1)

RSS_SOURCES = [
    {"name": "HAS - Recommandations et guides", "url": "https://www.has-sante.fr/jcms/c_1771214/fr/feed/Rss2.jsp?id=p_3081452", "category": "HAS", "priority": 1},
    {"name": "HAS - Actualités", "url": "https://www.has-sante.fr/jcms/c_1771214/fr/feed/Rss2.jsp?id=p_3081656", "category": "HAS", "priority": 2},
    {"name": "HAS - Bulletin officiel", "url": "https://www.has-sante.fr/jcms/c_1771214/fr/feed/Rss2.jsp?id=p_3113093", "category": "HAS", "priority": 3},
    {"name": "Santé publique France - Actualités", "url": "https://www.santepubliquefrance.fr/rss/news/1008", "category": "Santé publique", "priority": 4},
    {"name": "Santé publique France - Communiqués", "url": "https://www.santepubliquefrance.fr/rss/press-releases", "category": "Santé publique", "priority": 5},
    {"name": "Santé publique France - Avis et recommandations", "url": "https://www.santepubliquefrance.fr/rss/1088", "category": "Santé publique", "priority": 6},
]

HTML_INDEX_SOURCES = [
    {"name": "Vie-publique - Assurance maladie", "url": "https://www.vie-publique.fr/assurance-maladie", "category": "Assurance maladie", "priority": 7},
    {"name": "Vie-publique - Santé publique", "url": "https://www.vie-publique.fr/ressources/mots-cles/sante-publique", "category": "Santé publique", "priority": 8},
    {"name": "Assurance Maladie institutionnelle - Actualités", "url": "https://www.assurance-maladie.ameli.fr/actualites", "category": "Assurance maladie", "priority": 9},
    {"name": "DGS-Urgent", "url": "https://www.media-emploi.travail.gouv.fr/professionnels/article/dgs-urgent", "category": "Alerte sanitaire", "priority": 10},
]

TOPIC_KEYWORDS = [
    "ccam", "acte", "actes", "codage", "nomenclature", "remboursement", "assurance maladie",
    "prise en charge", "tiers payant", "tarif", "honoraire", "brss", "amo", "amc", "ngap",
    "dentaire", "chirurgien-dentiste", "bucco-dentaire", "m't dents", "prothèse", "100 % santé",
    "has", "recommandation", "guide", "avis", "accès précoce", "dispositif médical", "médicament",
    "vaccination", "infection", "épidémie", "alerte", "dgs-urgent", "prévention", "santé publique",
    "qualité des soins", "parcours de santé", "numérique en santé", "sécurité du patient",
]

CATEGORY_RULES = [
    ("CCAM", ["ccam", "codage", "nomenclature", "acte médical", "actes médicaux"]),
    ("Dentaire", ["dentaire", "chirurgien-dentiste", "bucco-dentaire", "m't dents", "prothèse", "100 % santé"]),
    ("Assurance maladie", ["assurance maladie", "remboursement", "tiers payant", "prise en charge", "brss", "amo", "amc"]),
    ("HAS", ["haute autorité de santé", "has", "recommandation", "avis", "guide", "dispositif médical"]),
    ("Alerte sanitaire", ["dgs-urgent", "alerte", "vigilance", "urgent", "vaccination"]),
    ("Santé publique", ["santé publique", "épidémie", "prévention", "infection", "vaccination"]),
]

FRENCH_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}

ANTIBOT_RE = re.compile(r"(cloudflare|just a moment|vérification de sécurité|verification de securite|ray id|not a bot|n'est pas un bot|robots malveillants)", re.I)
CODE_RE = re.compile(r"\b[A-Z]{4}\d{3}\b")


class TextExtractor(HTMLParser):
    skip_tags = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe"}
    block_tags = {"h1", "h2", "h3", "h4", "p", "li", "td", "th", "caption", "summary", "div", "article", "section", "br", "time"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.skip_depth = 0
        self.current_href: str | None = None
        self.current_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {k.lower(): v or "" for k, v in attrs}
        if tag in self.skip_tags:
            self.skip_depth += 1
        if tag == "a":
            self.current_href = attrs_dict.get("href")
            self.current_text = []
        if tag == "time" and attrs_dict.get("datetime"):
            self.parts.append("\n" + attrs_dict["datetime"] + "\n")
        if tag in {"h1", "h2", "h3", "h4"}:
            self.parts.append("\n## ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.skip_tags and self.skip_depth:
            self.skip_depth -= 1
        if tag == "a" and self.current_href:
            label = re.sub(r"\s+", " ", " ".join(self.current_text)).strip()
            self.links.append((label, self.current_href))
            self.current_href = None
            self.current_text = []
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        value = html.unescape(data or "")
        value = re.sub(r"\s+", " ", value).strip()
        if not value:
            return
        self.parts.append(value + " ")
        if self.current_href:
            self.current_text.append(value)

    def text(self) -> str:
        value = "".join(self.parts)
        value = re.sub(r"\n{3,}", "\n\n", value)
        value = re.sub(r"[ \t]{2,}", " ", value)
        return value.strip()


def now_fr() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS).isoformat(timespec="seconds")


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def slugify(text: str) -> str:
    replacements = str.maketrans("éèêëàâäçîïôöùûüÿñ", "eeeeaaaciioouuuyn")
    text = text.lower().translate(replacements)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:90] or "article"


def date_obj(value: str | None) -> dt.date | None:
    if not value:
        return None
    value = str(value).strip()
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(PARIS).date()
    except Exception:
        pass
    for pattern in [r"(\d{4})-(\d{1,2})-(\d{1,2})", r"(\d{1,2})/(\d{1,2})/(\d{4})"]:
        m = re.search(pattern, value)
        if m:
            try:
                if pattern.startswith("(\\d{4})"):
                    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass
    m = re.search(r"(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+(\d{4})", value, re.I)
    if m:
        try:
            return dt.date(int(m.group(3)), FRENCH_MONTHS[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            pass
    return None


def extract_date(text: str) -> dt.date | None:
    candidates: list[dt.date] = []
    for m in re.finditer(r"\b\d{4}-\d{1,2}-\d{1,2}\b|\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+\d{4}\b", text or "", re.I):
        parsed = date_obj(m.group(0))
        if parsed:
            candidates.append(parsed)
    # On prend la date récente la plus plausible. Cela évite de publier un vieux dossier qui mentionne une date récente accessoire.
    valid = [d for d in candidates if dt.date(2000, 1, 1) <= d <= dt.date.today() + dt.timedelta(days=30)]
    return max(valid) if valid else None


def is_recent(value: dt.date | None) -> bool:
    return bool(value and value >= MIN_ARTICLE_DATE)


def fetch(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; maidis-ccam-hub/1.0; +https://github.com/famillecompte9583-dev/maidis-ccam-hub)",
            "Accept": "application/rss+xml, application/xml, text/xml, text/html, text/plain;q=0.9, */*;q=0.5",
            "Accept-Language": "fr-FR,fr;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"(Partager cette page|Retour en haut de page|Mentions légales|Plan du site).*", "", text, flags=re.I | re.S)
    return text.strip()


def html_to_text_and_links(raw: str, base_url: str) -> tuple[str, list[tuple[str, str]]]:
    parser = TextExtractor()
    parser.feed(raw)
    links = []
    for label, href in parser.links:
        absolute = urllib.parse.urljoin(base_url, href)
        if absolute.startswith("http"):
            links.append((clean_text(label), absolute))
    return clean_text(parser.text()), links


def reject_bad_content(text: str, label: str) -> None:
    if ANTIBOT_RE.search(text or ""):
        raise ValueError(f"contenu anti-bot rejeté : {label}")
    if len(clean_text(text)) < MIN_TEXT_CHARS:
        raise ValueError(f"contenu trop court : {label}")


def rss_items(source: dict[str, Any]) -> list[dict[str, Any]]:
    raw = fetch(source["url"])
    reject_bad_content(raw, source["name"])
    root = ET.fromstring(raw.encode("utf-8"))
    items = []
    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title") or "")
        link = clean_text(item.findtext("link") or "")
        desc = clean_text(item.findtext("description") or item.findtext("summary") or "")
        pub_date = date_obj(item.findtext("pubDate") or item.findtext("date")) or extract_date(f"{title} {desc}")
        if title and link and is_recent(pub_date):
            items.append({"title": title, "url": link, "description": desc, "date": pub_date.isoformat(), "source": source})
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title = clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        link_el = entry.find("atom:link", ns)
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        desc = clean_text(entry.findtext("atom:summary", default="", namespaces=ns) or entry.findtext("atom:content", default="", namespaces=ns))
        pub_date = date_obj(entry.findtext("atom:updated", default="", namespaces=ns)) or extract_date(f"{title} {desc}")
        if title and link and is_recent(pub_date):
            items.append({"title": title, "url": link, "description": desc, "date": pub_date.isoformat(), "source": source})
    items.sort(key=lambda item: item.get("date", ""), reverse=True)
    return items[:MAX_PER_SOURCE]


def index_items(source: dict[str, Any]) -> list[dict[str, Any]]:
    raw = fetch(source["url"])
    text, links = html_to_text_and_links(raw, source["url"])
    reject_bad_content(text, source["name"])
    out = []
    seen = set()
    for label, href in links:
        low = f"{label} {href}".lower()
        if href in seen or not label or len(label) < 20:
            continue
        if not any(k in low for k in TOPIC_KEYWORDS) and source["category"] not in {"Assurance maladie", "Alerte sanitaire"}:
            continue
        if any(skip in href for skip in ["#", "mailto:", "facebook", "twitter", "linkedin"]):
            continue
        seen.add(href)
        out.append({"title": label[:180], "url": href, "description": "", "date": None, "source": source})
        if len(out) >= MAX_PER_SOURCE:
            break
    return out


def fetch_detail(url: str, fallback: str) -> str:
    try:
        raw = fetch(url)
        text, _ = html_to_text_and_links(raw, url)
        reject_bad_content(text, url)
        return text
    except Exception:
        if len(fallback) >= 120:
            return fallback
        raise


def category_for(title: str, text: str, fallback: str) -> str:
    low = f"{title} {text}".lower()
    for category, words in CATEGORY_RULES:
        if any(word in low for word in words):
            return category
    return fallback or "Dossier"


def relevant(title: str, text: str, source_category: str) -> bool:
    low = f"{title} {text}".lower()
    if source_category in {"HAS", "Santé publique", "Assurance maladie", "Alerte sanitaire"}:
        return any(k in low for k in TOPIC_KEYWORDS) or len(text) > 900
    return any(k in low for k in TOPIC_KEYWORDS)


def paragraphs(text: str) -> list[str]:
    out = []
    for block in re.split(r"\n+|(?<=[.!?])\s+(?=[A-ZÉÈÀÂÎÔÙÇ])", text):
        value = re.sub(r"\s+", " ", block).strip(" -•\t")
        if 50 <= len(value) <= 1200:
            out.append(value)
    return out


def build_html(title: str, url: str, text: str, codes: list[str], source_name: str, article_date: str) -> str:
    parts = paragraphs(text)
    intro = parts[:3]
    detail = parts[3:22]
    code_text = ", ".join(codes[:40]) if codes else "Aucun code CCAM explicite détecté dans le texte source."
    return "".join([
        f"<p>Ce dossier provient d'une source officielle récente : {esc(source_name)}. Date retenue : {esc(article_date)}.</p>",
        "<h2>Contenu extrait</h2>",
        "".join(f"<p>{esc(p)}</p>" for p in intro),
        "<h2>Détails utiles</h2>",
        "<ul>",
        "".join(f"<li>{esc(p)}</li>" for p in detail[:14]),
        "</ul>",
        "<h2>Codes CCAM explicitement détectés</h2>",
        f"<p>{esc(code_text)}</p>",
        "<h2>Source et traçabilité</h2>",
        f"<p>Source : <a href=\"{esc(url)}\" target=\"_blank\" rel=\"noopener noreferrer\">{esc(title)}</a>. Texte extrait : {len(text)} caractères. Généré le {esc(now_fr())}. Les contenus antérieurs au {esc(MIN_ARTICLE_DATE.isoformat())} sont ignorés automatiquement.</p>",
    ])


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
    raw_items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    skipped_old = 0
    skipped_no_date = 0

    for source in RSS_SOURCES:
        try:
            raw_items.extend(rss_items(source))
            time.sleep(0.3)
        except Exception as exc:
            errors.append({"source": source["name"], "error": f"{type(exc).__name__}: {exc}"})
    for source in HTML_INDEX_SOURCES:
        try:
            raw_items.extend(index_items(source))
            time.sleep(0.3)
        except Exception as exc:
            errors.append({"source": source["name"], "error": f"{type(exc).__name__}: {exc}"})

    articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    # Les items RSS récents passent d'abord, puis les pages HTML dont la date sera vérifiée après extraction.
    raw_items.sort(key=lambda x: (x.get("date") or "0000-00-00"), reverse=True)
    for item in raw_items:
        if len(articles) >= MAX_ARTICLES:
            break
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        try:
            source = item["source"]
            text = clean_text(fetch_detail(item["url"], item.get("description", "")))
            article_date_obj = date_obj(item.get("date")) or extract_date(f"{item['title']} {text}")
            if not article_date_obj:
                skipped_no_date += 1
                continue
            if not is_recent(article_date_obj):
                skipped_old += 1
                continue
            if not relevant(item["title"], text, source["category"]):
                continue
            reject_bad_content(text, item["url"])
            category = category_for(item["title"], text, source["category"])
            codes = sorted(set(CODE_RE.findall(text)) & record_codes)
            slug = slugify(item["title"])
            if any(a["id"] == slug for a in articles):
                slug = f"{slug}-{len(articles)+1}"
            article_date = article_date_obj.isoformat()
            articles.append({
                "id": slug,
                "title": item["title"],
                "date": article_date,
                "source": source["name"],
                "source_url": item["url"],
                "category": category,
                "tag": category,
                "summary": f"Dossier récent extrait depuis {source['name']} ({len(text)} caractères), destiné à une reformulation dense par Gemini.",
                "content_html": build_html(item["title"], item["url"], text, codes, source["name"], article_date),
                "codes": codes[:80],
                "codes_detectes": codes[:180],
                "extracted_chars": len(text),
                "source_text_excerpt": text[:SOURCE_TEXT_LIMIT],
                "confidence": "Haute" if len(text) > 1800 else "Moyenne",
                "generation": {
                    "mode": "official-rss-and-public-html-recent-only",
                    "generated": now_fr(),
                    "text_chars": len(text),
                    "minimum_date": MIN_ARTICLE_DATE.isoformat(),
                    "grounding": "recent_official_sources_rss_or_public_html_no_antibot",
                },
            })
            time.sleep(0.3)
        except Exception as exc:
            errors.append({"source": item.get("url", ""), "error": f"{type(exc).__name__}: {exc}"})

    articles.sort(key=lambda item: item.get("date", "0000-00-00"), reverse=True)
    app["articles"] = articles
    app.setdefault("meta", {})["articles"] = len(articles)
    app["meta"]["article_generation"] = {
        "mode": "official-rss-and-public-html-recent-only",
        "generated": now_fr(),
        "minimum_date": MIN_ARTICLE_DATE.isoformat(),
        "sources_attempted": len(RSS_SOURCES) + len(HTML_INDEX_SOURCES),
        "raw_items": len(raw_items),
        "articles_generated": len(articles),
        "skipped_old": skipped_old,
        "skipped_no_date": skipped_no_date,
        "errors": errors[:12],
        "description": "Dossiers récents uniquement, triés par date décroissante, depuis des sources officielles stables.",
    }
    link_articles_to_records(app)
    save_app(app)
    update_status("ok" if articles else "empty", {
        "count": len(articles),
        "mode": "official-rss-and-public-html-recent-only",
        "minimum_date": MIN_ARTICLE_DATE.isoformat(),
        "sources_attempted": len(RSS_SOURCES) + len(HTML_INDEX_SOURCES),
        "raw_items": len(raw_items),
        "skipped_old": skipped_old,
        "skipped_no_date": skipped_no_date,
        "total_extracted_chars": sum(int(a.get("extracted_chars", 0)) for a in articles),
        "errors": errors[:12],
        "message": "Dossiers récents triés automatiquement par date décroissante.",
    })
    print(f"Articles récents générés : {len(articles)} ; ignorés anciens : {skipped_old} ; sans date : {skipped_no_date} ; erreurs : {len(errors)}")


if __name__ == "__main__":
    main()
