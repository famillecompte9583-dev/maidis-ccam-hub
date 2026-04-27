#!/usr/bin/env python3
"""Contrôles qualité avant publication publique."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys
from typing import Any
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "app-data.json"
STATUS = ROOT / "data" / "sync-status.json"
MIN_RECORDS = 3_000
MIN_MAIN_RECORDS = 10_000
MIN_ARTICLE_YEAR = int(os.environ.get("MIN_ARTICLE_YEAR", str(dt.date.today().year - 2)))
MIN_ARTICLE_DATE = dt.date(MIN_ARTICLE_YEAR, 1, 1)
CODE_RE = re.compile(r"^[A-Z]{4}\d{3}$")
UNSAFE_HTML_RE = re.compile(r"<\s*(script|iframe|object|embed|link|meta|form|input|button|textarea)\b|\son[a-z]+\s*=|javascript\s*:", re.I)
ANTIBOT_RE = re.compile(r"(vérification de sécurité|verification de securite|just a moment|cloudflare|ray id|robots malveillants|n'est pas un bot|not a bot|s'assure que l'utilisateur n'est pas un bot)", re.I)
ALLOWED_ARTICLE_TAGS = {"a", "p", "ul", "ol", "li", "strong", "b", "em", "i", "br", "h2", "h3", "h4", "table", "thead", "tbody", "tr", "th", "td", "span"}


def fail(message: str) -> None:
    print(f"❌ {message}", file=sys.stderr)
    raise SystemExit(1)


def warn(message: str) -> None:
    print(f"⚠️  {message}")


def ok(message: str) -> None:
    print(f"✅ {message}")


def load_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        fail(f"Fichier absent ou vide : {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        fail(f"JSON invalide dans {path}: {exc}")
    if not isinstance(value, dict):
        fail(f"Racine JSON inattendue dans {path}")
    return value


def public_url(value: Any) -> bool:
    try:
        parsed = urlparse(str(value or ""))
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except Exception:
        return False


def plain_text_from_html(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")


def parse_iso_date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or "")[:10])
    except Exception:
        return None


def validate_records(app: dict[str, Any]) -> list[dict[str, Any]]:
    records = app.get("records")
    if not isinstance(records, list):
        fail("records doit être une liste")
    if len(records) < MIN_RECORDS:
        fail(f"Base trop petite pour publication : {len(records)} actes")
    if len(records) < MIN_MAIN_RECORDS:
        warn(f"Base exploitable mais inhabituellement petite : {len(records)} actes")
    bad_codes = []
    missing_labels = 0
    sample = records[:500] + records[-500:]
    for record in sample:
        if not isinstance(record, dict):
            fail("Chaque record doit être un objet")
        code = str(record.get("code", ""))
        if not CODE_RE.match(code):
            bad_codes.append(code)
        if not str(record.get("libelle", "")).strip():
            missing_labels += 1
    if bad_codes:
        fail(f"Codes CCAM invalides détectés, exemples : {bad_codes[:8]}")
    if missing_labels:
        fail(f"Libellés absents dans l'échantillon : {missing_labels}")
    ok(f"{len(records):,} actes contrôlés pour publication".replace(",", " "))
    return records


def validate_meta(app: dict[str, Any], records: list[dict[str, Any]]) -> None:
    meta = app.get("meta")
    if not isinstance(meta, dict):
        fail("meta doit être un objet")
    if meta.get("status") != "ok":
        fail(f"meta.status doit être ok, reçu : {meta.get('status')}")
    if meta.get("sync_mode") not in {"fresh", "stale"}:
        fail(f"sync_mode inattendu : {meta.get('sync_mode')}")
    total = int(meta.get("total") or 0)
    if total and abs(total - len(records)) > 5:
        fail(f"meta.total incohérent : {total} vs {len(records)} records")
    if not meta.get("generated"):
        fail("meta.generated absent")
    source = meta.get("source") or meta.get("selected_source") or {}
    if isinstance(source, dict) and source.get("url") and not public_url(source.get("url")):
        fail("URL de source non publique")
    ok("Métadonnées cohérentes")


def validate_articles(app: dict[str, Any]) -> None:
    articles = app.get("articles", [])
    if not isinstance(articles, list):
        fail("articles doit être une liste")
    previous_date: dt.date | None = None
    for article in articles:
        if not isinstance(article, dict):
            fail("Chaque article doit être un objet")
        title = str(article.get("title", "")).strip()
        if not title:
            fail("Article sans titre")
        if article.get("category") == "Sources & API" or article.get("tag") == "Sources & API":
            fail(f"Fiche Sources & API mélangée aux dossiers d’actualité : {title}")
        article_date = parse_iso_date(article.get("date"))
        if not article_date:
            fail(f"Article sans date ISO exploitable : {title}")
        if article_date < MIN_ARTICLE_DATE:
            fail(f"Article trop ancien pour la page Dossiers : {title} ({article_date.isoformat()})")
        if previous_date and article_date > previous_date:
            fail(f"Articles non triés par date décroissante autour de : {title}")
        previous_date = article_date
        html = str(article.get("content_html", ""))
        source_text = str(article.get("source_text_excerpt", ""))
        combined = f"{title}\n{plain_text_from_html(html)}\n{source_text}"
        if ANTIBOT_RE.search(combined):
            fail(f"Contenu anti-bot publié par erreur : {title}")
        if UNSAFE_HTML_RE.search(html):
            fail(f"HTML dangereux détecté dans l'article : {title}")
        for tag in re.findall(r"</?\s*([a-zA-Z0-9:-]+)", html):
            if tag.lower() not in ALLOWED_ARTICLE_TAGS:
                fail(f"Balise HTML non autorisée <{tag}> dans l'article : {title}")
        source_url = article.get("source_url") or article.get("url")
        if source_url and not public_url(source_url):
            fail(f"URL source invalide pour l'article : {title}")
    ok(f"{len(articles)} article(s) récent(s), trié(s) et contrôlé(s)")


def validate_news(app: dict[str, Any]) -> None:
    news = app.get("news", [])
    if not isinstance(news, list):
        fail("news doit être une liste")
    for item in news:
        if not isinstance(item, dict):
            fail("Chaque actualité doit être un objet")
        if item.get("url") and not public_url(item.get("url")):
            fail(f"URL d'actualité invalide : {item.get('url')}")
    ok(f"{len(news)} actualité(s) contrôlée(s)")


def validate_status() -> None:
    if not STATUS.exists():
        warn("sync-status.json absent : conseillé mais non bloquant")
        return
    status = load_json(STATUS)
    if status.get("status") != "ok":
        fail(f"sync-status.json indique un état non publiable : {status.get('status')}")
    ok("Statut de synchronisation publiable")


def main() -> None:
    app = load_json(DATA)
    records = validate_records(app)
    validate_meta(app, records)
    validate_articles(app)
    validate_news(app)
    validate_status()
    ok("Validation publique terminée")


if __name__ == "__main__":
    main()
