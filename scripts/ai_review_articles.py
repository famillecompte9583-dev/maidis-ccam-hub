#!/usr/bin/env python3
"""Relecture éditoriale optionnelle des dossiers via Gemini.

Gemini sert uniquement à relire et structurer les contenus réellement extraits.
Il ne doit pas inventer de dossier, de règle métier ou de code CCAM.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APP_PATH = DATA_DIR / "app-data.json"
STATUS_PATH = DATA_DIR / "sync-status.json"
PARIS = ZoneInfo("Europe/Paris")

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
MAX_ARTICLES = int(os.environ.get("AI_REVIEW_MAX_ARTICLES", "12"))
TIMEOUT_SECONDS = int(os.environ.get("AI_REVIEW_TIMEOUT", "45"))

SAFE_TAGS = {"p", "ul", "ol", "li", "strong", "b", "em", "i", "br", "h2", "h3", "h4", "a", "span"}
UNSAFE_RE = re.compile(r"<\s*(script|iframe|object|embed|link|meta|form|input|button|textarea)\b|\son[a-z]+\s*=|javascript\s*:", re.I)
CODE_RE = re.compile(r"\b[A-Z]{4}\d{3}\b")


def now_fr() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS).isoformat(timespec="seconds")


def load_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        raise SystemExit(f"Fichier absent ou vide : {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_app(app: dict[str, Any]) -> None:
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
    current["ai_review"] = {"status": status, "generated": now_fr(), **details}
    STATUS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def plain_text_from_html(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", value or "", flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def safe_public_url(value: Any) -> str:
    try:
        parsed = urllib.parse.urlparse(str(value or ""))
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return str(value)
    except Exception:
        pass
    return ""


def sanitize_html_fragment(fragment: str) -> str:
    fragment = str(fragment or "")
    if UNSAFE_RE.search(fragment):
        fragment = UNSAFE_RE.sub(" ", fragment)

    def repl(match: re.Match[str]) -> str:
        slash, tag, attrs = match.group(1), match.group(2).lower(), match.group(3) or ""
        if tag not in SAFE_TAGS:
            return ""
        if slash:
            return f"</{tag}>"
        if tag == "a":
            href_match = re.search(r"href=[\"']([^\"']+)[\"']", attrs, flags=re.I)
            href = safe_public_url(html.unescape(href_match.group(1))) if href_match else ""
            if href:
                return f'<a href="{html.escape(href, quote=True)}" target="_blank" rel="noopener noreferrer">'
            return "<span>"
        return f"<{tag}>"

    fragment = re.sub(r"<\s*(/?)\s*([a-zA-Z0-9:-]+)([^>]*)>", repl, fragment)
    return fragment.strip()


def allowed_codes(article: dict[str, Any], record_codes: set[str]) -> set[str]:
    # Strict : uniquement les codes déjà détectés par le scraper dans la page source.
    detected = {code for code in article.get("codes_detectes", []) if isinstance(code, str)}
    known = {code for code in article.get("codes", []) if isinstance(code, str)}
    return (detected | known) & record_codes


def compact_article(article: dict[str, Any]) -> dict[str, Any]:
    source_text = str(article.get("source_text_excerpt") or "").strip()
    if not source_text:
        source_text = plain_text_from_html(article.get("content_html", ""))
    return {
        "id": article.get("id"),
        "title": article.get("title"),
        "category": article.get("category") or article.get("tag"),
        "summary": article.get("summary"),
        "source": article.get("source"),
        "source_url": article.get("source_url") or article.get("url"),
        "codes_detectes": article.get("codes_detectes", [])[:80],
        "source_text_reel": source_text[:12000],
        "generation": article.get("generation"),
    }


def build_prompt(article: dict[str, Any], allowed: set[str]) -> str:
    allowed_codes_text = ", ".join(sorted(allowed)[:120]) or "aucun"
    payload = compact_article(article)
    return f"""
Tu es relecteur éditorial pour un site public français d'aide à la lecture CCAM.
Tu dois créer une fiche claire à partir du texte réel extrait d'une page Ameli publique.

Règles strictes :
- Base-toi uniquement sur le champ source_text_reel.
- Ne crée aucune information absente du texte source.
- Ne donne pas de conseil médical individuel.
- Ne présente jamais les montants/taux comme une vérité opposable.
- La source officielle reste prioritaire.
- N'utilise que ces balises HTML : <p>, <h2>, <h3>, <ul>, <ol>, <li>, <strong>, <em>, <br>, <a>.
- Pas de script, iframe, style inline, attribut on*, javascript:, tableau complexe ou image.
- Les codes CCAM renvoyés doivent appartenir exclusivement à cette liste explicitement détectée : {allowed_codes_text}.
- Si aucun code n'est autorisé, renvoie codes: [] ; n'invente jamais de code.
- Réponds uniquement avec un JSON valide, sans markdown.

Schéma attendu :
{{
  "title": "titre clair et fidèle à la source",
  "summary": "résumé public en 1 à 2 phrases, fidèle au texte source",
  "category": "CCAM|Tarifs|Dentaire|100 % Santé|Convention|Dossier",
  "content_html": "HTML structuré et sourcé, sans ajout non présent dans la source",
  "codes": ["codes CCAM autorisés uniquement"],
  "confidence": "Haute|Moyenne|Basse"
}}

Article source JSON :
{json.dumps(payload, ensure_ascii=False)}
""".strip()


def call_gemini(prompt: str, api_key: str) -> dict[str, Any]:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.15,
            "topP": 0.7,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
        raw = json.loads(response.read().decode("utf-8"))
    text = raw.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    if not text:
        raise RuntimeError("Réponse Gemini vide")
    return json.loads(strip_code_fences(text))


def normalize_ai_result(result: dict[str, Any], original: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("La réponse IA n'est pas un objet JSON")

    title = str(result.get("title") or original.get("title") or "Dossier").strip()[:180]
    summary = str(result.get("summary") or original.get("summary") or "").strip()[:420]
    category = str(result.get("category") or original.get("category") or original.get("tag") or "Dossier").strip()
    if category not in {"CCAM", "Tarifs", "Dentaire", "100 % Santé", "Convention", "Dossier"}:
        category = original.get("category") or original.get("tag") or "Dossier"

    content_html = sanitize_html_fragment(str(result.get("content_html") or original.get("content_html") or ""))
    if not content_html or len(plain_text_from_html(content_html)) < 120:
        raise ValueError("Contenu IA trop court ou vide")

    codes = []
    for code in result.get("codes", []):
        if isinstance(code, str) and code in allowed and code not in codes:
            codes.append(code)

    confidence = str(result.get("confidence") or "Moyenne").strip()
    if confidence not in {"Haute", "Moyenne", "Basse"}:
        confidence = "Moyenne"

    return {
        **original,
        "title": title,
        "summary": summary,
        "category": category,
        "tag": category,
        "content_html": content_html,
        "codes": codes,
        "confidence": confidence,
        "ai_review": {
            "provider": "gemini",
            "model": MODEL,
            "reviewed_at": now_fr(),
            "mode": "grounded_editorial_review_only",
        },
    }


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        update_status("skipped", {"reason": "GEMINI_API_KEY absent", "model": MODEL})
        print("Gemini désactivé : secret GEMINI_API_KEY absent.")
        return

    app = load_json(APP_PATH)
    articles = app.get("articles", [])
    records = app.get("records", [])
    if not isinstance(articles, list) or not articles:
        update_status("skipped", {"reason": "aucun article réel à relire", "model": MODEL})
        print("Gemini désactivé : aucun article.")
        return
    record_codes = {r.get("code") for r in records if isinstance(r, dict) and isinstance(r.get("code"), str)}

    reviewed = []
    errors = []
    for index, article in enumerate(articles):
        if index >= MAX_ARTICLES:
            reviewed.append(article)
            continue
        try:
            allowed = allowed_codes(article, record_codes)
            prompt = build_prompt(article, allowed)
            result = call_gemini(prompt, api_key)
            reviewed.append(normalize_ai_result(result, article, allowed))
            print(f"Article relu par Gemini : {article.get('title')}")
            time.sleep(1.2)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            errors.append({"title": article.get("title"), "error": f"HTTP {exc.code}: {body}"})
            reviewed.append(article)
            print(f"Gemini ignoré pour un article : HTTP {exc.code}", file=sys.stderr)
        except Exception as exc:
            errors.append({"title": article.get("title"), "error": f"{type(exc).__name__}: {exc}"})
            reviewed.append(article)
            print(f"Gemini ignoré pour un article : {exc}", file=sys.stderr)

    if len(articles) > len(reviewed):
        reviewed.extend(articles[len(reviewed):])

    app["articles"] = reviewed
    app.setdefault("meta", {})["ai_review"] = {
        "provider": "gemini",
        "model": MODEL,
        "generated": now_fr(),
        "reviewed_articles": sum(1 for article in reviewed if isinstance(article, dict) and article.get("ai_review")),
        "attempted_articles": min(len(articles), MAX_ARTICLES),
        "errors": len(errors),
    }
    save_app(app)
    update_status("ok" if not errors else "partial", {
        "provider": "gemini",
        "model": MODEL,
        "attempted_articles": min(len(articles), MAX_ARTICLES),
        "reviewed_articles": app["meta"]["ai_review"]["reviewed_articles"],
        "errors": errors[:8],
    })
    print("Relecture Gemini terminée.")


if __name__ == "__main__":
    main()
