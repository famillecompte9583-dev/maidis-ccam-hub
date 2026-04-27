#!/usr/bin/env python3
"""Filtre pragmatique des actualités vers une veille réglementaire CCAM/Assurance maladie.

Le but n'est pas de publier toute l'actualité médicale, mais uniquement ce qui est utile
aux actes, tarifs, conventions, remboursement, CCAM/NGAP, dentaire, 100 % Santé et facturation.
Le script trace aussi la date de publication reconnue à la source quand elle est disponible.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from typing import Any
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APP_PATH = DATA_DIR / "app-data.json"
STATUS_PATH = DATA_DIR / "sync-status.json"
PARIS = ZoneInfo("Europe/Paris")
MAX_NEWS = int(os.environ.get("REGULATORY_NEWS_MAX", "18"))
FETCH_SOURCE_DATES = os.environ.get("REG_NEWS_REFRESH_SOURCE_DATES", "1") != "0"
MIN_YEAR = int(os.environ.get("MIN_ARTICLE_YEAR", str(dt.date.today().year - 2)))
MIN_DATE = dt.date(MIN_YEAR, 1, 1)

STRONG_TERMS = [
    "ccam", "ngap", "nomenclature", "codage", "acte", "actes", "tarif", "tarifs",
    "tarification", "honoraire", "honoraires", "brss", "base de remboursement",
    "remboursement", "prise en charge", "amo", "amc", "tiers payant", "facturation",
    "convention", "avenant", "assurance maladie", "cnam", "ameli", "accord préalable",
    "dentaire", "chirurgien-dentiste", "bucco-dentaire", "devis", "prothèse", "prothétique",
    "100 % santé", "100% santé", "reste à charge", "rac 0", "panier de soins",
]
SECONDARY_TERMS = [
    "professionnel de santé", "professionnels de santé", "libéral", "libéraux",
    "centre de santé", "calendrier conventionnel", "logiciel", "téléservice",
]
BROAD_MEDICAL_NOISE = [
    "épidémie", "epidemie", "infection", "vaccination", "vaccin", "dépistage", "depistage",
    "canicule", "grippe", "covid", "bronchiolite", "prévention", "prevention", "santé publique",
]
OFFICIAL_SOURCES = ["ameli", "assurance maladie", "cnam", "has", "haute autorité de santé", "vie-publique", "dgs"]

DATE_META_RE = re.compile(
    r'<meta[^>]+(?:property|name|itemprop)=["\'](?P<key>article:published_time|article:modified_time|datePublished|dateModified|pubdate|date|dc.date|dc.date.issued|og:updated_time)["\'][^>]+content=["\'](?P<value>[^"\']+)["\']',
    re.I,
)
TIME_RE = re.compile(r'<time[^>]+datetime=["\'](?P<value>[^"\']+)["\']', re.I)
FRENCH_DATE_RE = re.compile(
    r'(?:publié|publie|mise? à jour|mis à jour|actualisé|actualise|date de publication)\s*(?:le|:)\s*'
    r'(?P<value>\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{1,2}-\d{1,2})',
    re.I,
)
ANY_DATE_RE = re.compile(
    r'\b(?P<value>\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+\d{4})\b',
    re.I,
)
MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
}


def now_fr() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS).isoformat(timespec="seconds")


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
    payload["regulatory_news_filter"] = {"status": status, "generated": now_fr(), **details}
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def plain_text(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(PARIS).date()
    except Exception:
        pass
    try:
        normalized = raw.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(normalized[:10] if len(normalized) == 10 else normalized).date()
    except Exception:
        pass
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s+(janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre)\s+(\d{4})", raw, re.I)
    if m:
        try:
            return dt.date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            return None
    return None


def plausible_date(value: dt.date | None) -> bool:
    return bool(value and dt.date(2000, 1, 1) <= value <= dt.date.today() + dt.timedelta(days=45))


def fetch_text(url: str, timeout: int = 25) -> str:
    parsed = urllib.parse.urlparse(str(url or ""))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL source invalide")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; maidis-ccam-hub-regulatory-news/1.0)",
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.4",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def date_from_html(raw_html: str) -> dict[str, Any] | None:
    candidates: list[tuple[int, str, str, str]] = []
    for match in DATE_META_RE.finditer(raw_html or ""):
        key = match.group("key")
        value = html.unescape(match.group("value")).strip()
        parsed = parse_date(value)
        if plausible_date(parsed):
            priority = 1 if "published" in key.lower() or "issued" in key.lower() or key.lower() == "pubdate" else 2
            candidates.append((priority, parsed.isoformat(), f"meta:{key}", value))
    for match in TIME_RE.finditer(raw_html or ""):
        value = html.unescape(match.group("value")).strip()
        parsed = parse_date(value)
        if plausible_date(parsed):
            candidates.append((3, parsed.isoformat(), "time:datetime", value))
    text = plain_text(raw_html[:120000])
    for regex, source_type, priority in [(FRENCH_DATE_RE, "texte:publication_label", 4), (ANY_DATE_RE, "texte:date_detectee", 6)]:
        for match in regex.finditer(text[:30000]):
            value = match.group("value")
            parsed = parse_date(value)
            if plausible_date(parsed):
                candidates.append((priority, parsed.isoformat(), source_type, value))
                break
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=False)
    priority, iso, source_type, raw = candidates[0]
    return {"date": iso, "source_type": source_type, "raw": raw, "confidence": "Haute" if priority <= 3 else "Moyenne" if priority == 4 else "Basse"}


def text_for_article(article: dict[str, Any]) -> str:
    fields = [
        article.get("title"), article.get("summary"), article.get("category"), article.get("tag"),
        article.get("source"), article.get("source_url"), article.get("url"),
        article.get("source_text_excerpt"), plain_text(str(article.get("content_html") or "")),
    ]
    return " ".join(str(v or "") for v in fields).lower()


def relevance(article: dict[str, Any]) -> tuple[int, list[str], str]:
    text = text_for_article(article)
    score = 0
    reasons: list[str] = []
    strong_hits = sorted({term for term in STRONG_TERMS if term in text})
    secondary_hits = sorted({term for term in SECONDARY_TERMS if term in text})
    official_hits = sorted({term for term in OFFICIAL_SOURCES if term in text})
    noise_hits = sorted({term for term in BROAD_MEDICAL_NOISE if term in text})
    if strong_hits:
        score += min(12, len(strong_hits) * 3)
        reasons.append("termes réglementaires: " + ", ".join(strong_hits[:6]))
    if secondary_hits:
        score += min(4, len(secondary_hits))
    if official_hits:
        score += 2
        reasons.append("source officielle détectée")
    if noise_hits and not strong_hits:
        score -= 5
        reasons.append("actualité médicale trop générale sans lien actes/facturation")
    category = "Réglementation actes / Assurance maladie" if score >= 7 else "À vérifier"
    return score, reasons, category


def normalize_date(article: dict[str, Any], source_date: dict[str, Any] | None) -> dict[str, Any]:
    existing = parse_date(article.get("date") or article.get("publication_date") or article.get("published_at"))
    selected: dict[str, Any] | None = None
    if source_date and parse_date(source_date.get("date")):
        selected = source_date
    elif plausible_date(existing):
        selected = {
            "date": existing.isoformat(),
            "source_type": article.get("date_source_type") or "pipeline:rss_ou_source_precedente",
            "raw": article.get("date_raw") or article.get("date") or existing.isoformat(),
            "confidence": article.get("date_confidence") or "Moyenne",
        }
    if selected:
        article["date"] = selected["date"]
        article["publication_date"] = selected["date"]
        article["publication_date_source"] = selected["source_type"]
        article["publication_date_raw"] = selected.get("raw", selected["date"])
        article["publication_date_confidence"] = selected.get("confidence", "Moyenne")
    else:
        article["publication_date_source"] = "non_reconnue"
        article["publication_date_confidence"] = "Basse"
    article["date_checked_at"] = now_fr()
    return article


def article_url(article: dict[str, Any]) -> str:
    return str(article.get("source_url") or article.get("url") or "")


def main() -> None:
    app = load_app()
    input_articles = app.get("articles", [])
    if not isinstance(input_articles, list):
        input_articles = []
    kept: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for original in input_articles:
        if not isinstance(original, dict):
            continue
        article = dict(original)
        source_date = None
        url = article_url(article)
        if FETCH_SOURCE_DATES and url:
            try:
                raw = fetch_text(url)
                source_date = date_from_html(raw)
                if raw and not article.get("source_text_excerpt"):
                    article["source_text_excerpt"] = plain_text(raw)[:24000]
            except Exception as exc:
                errors.append({"source": url, "error": f"{type(exc).__name__}: {exc}"})
        article = normalize_date(article, source_date)
        score, reasons, scope = relevance(article)
        article["regulatory_relevance_score"] = score
        article["regulatory_relevance_reason"] = reasons
        article["regulatory_scope"] = scope
        article["actionability"] = "À suivre pour paramétrage CCAM/Maidis" if score >= 7 else "Information générale"
        article["audit_filter"] = {"mode": "ccam_assurance_maladie_reglementaire", "minimum_score": 7, "checked_at": now_fr()}
        parsed = parse_date(article.get("date"))
        date_ok = plausible_date(parsed) and parsed >= MIN_DATE if parsed else False
        if score >= 7 and date_ok:
            kept.append(article)
        else:
            removed.append({
                "id": article.get("id"),
                "title": article.get("title"),
                "date": article.get("date"),
                "score": score,
                "date_ok": date_ok,
                "reason": reasons[:4] or ["hors périmètre réglementaire CCAM/Assurance maladie"],
            })
    kept.sort(key=lambda item: item.get("date") or "0000-00-00", reverse=True)
    kept = kept[:MAX_NEWS]
    app["articles"] = kept
    app["news"] = [{
        "id": a.get("id"),
        "title": a.get("title"),
        "date": a.get("date"),
        "publication_date": a.get("publication_date"),
        "publication_date_source": a.get("publication_date_source"),
        "publication_date_confidence": a.get("publication_date_confidence"),
        "source": a.get("source"),
        "url": a.get("source_url") or a.get("url"),
        "tag": a.get("category") or a.get("tag") or "Veille réglementaire",
        "summary": a.get("summary"),
        "regulatory_relevance_score": a.get("regulatory_relevance_score"),
        "regulatory_scope": a.get("regulatory_scope"),
        "actionability": a.get("actionability"),
    } for a in kept]
    app["archived_non_regulatory_articles"] = removed[:30]
    app.setdefault("meta", {})["articles"] = len(kept)
    app["meta"]["regulatory_news_filter"] = {
        "generated": now_fr(),
        "mode": "ccam_assurance_maladie_reglementaire",
        "input_articles": len(input_articles),
        "kept_articles": len(kept),
        "removed_articles": len(removed),
        "minimum_date": MIN_DATE.isoformat(),
        "date_recognition": "meta/time/labels HTML si accessible, sinon date RSS ou date pipeline",
        "description": "Filtre les actualités médicales larges pour ne publier que des contenus utiles aux actes, tarifs, conventions, remboursement, CCAM/NGAP, dentaire, 100 % Santé et facturation.",
        "errors": errors[:12],
    }
    save_app(app)
    update_status("ok" if kept else "empty", {
        "input_articles": len(input_articles),
        "kept_articles": len(kept),
        "removed_articles": len(removed),
        "minimum_date": MIN_DATE.isoformat(),
        "errors": errors[:12],
    })
    print(f"Veille réglementaire filtrée : {len(kept)} retenu(s), {len(removed)} écarté(s).")


if __name__ == "__main__":
    main()
