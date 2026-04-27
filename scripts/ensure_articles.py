#!/usr/bin/env python3
"""Ne publie jamais de faux dossiers.

Ce script vérifie seulement que le pipeline a produit de vrais articles.
S'il n'y en a pas, il garde `articles` vide et écrit un diagnostic clair.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APP_PATH = DATA_DIR / "app-data.json"
STATUS_PATH = DATA_DIR / "sync-status.json"
PARIS = ZoneInfo("Europe/Paris")


def now_fr() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS).isoformat(timespec="seconds")


def load_app() -> dict:
    if not APP_PATH.exists() or APP_PATH.stat().st_size == 0:
        raise SystemExit("data/app-data.json absent ou vide")
    return json.loads(APP_PATH.read_text(encoding="utf-8"))


def save_app(app: dict) -> None:
    APP_PATH.write_text(json.dumps(app, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "app-data.js").write_text("window.CCAM_APP_DATA = " + json.dumps(app, ensure_ascii=False) + ";\n", encoding="utf-8")


def update_status(status: str, count: int, message: str) -> None:
    if STATUS_PATH.exists() and STATUS_PATH.stat().st_size:
        try:
            payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    else:
        payload = {}
    payload["articles_guard"] = {
        "status": status,
        "generated": now_fr(),
        "count": count,
        "message": message,
    }
    STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    app = load_app()
    articles = app.get("articles", [])
    if isinstance(articles, list) and articles:
        update_status("ok", len(articles), "Vrais articles présents ; aucun fallback publié.")
        print(f"Articles réels présents : {len(articles)}")
        return

    app["articles"] = []
    app.setdefault("meta", {})["articles"] = 0
    app["meta"]["article_generation"] = {
        "mode": "strict-no-fallback",
        "generated": now_fr(),
        "pages_scanned": 0,
        "description": "Aucun vrai article extrait ; aucun dossier de substitution n'est publié.",
    }
    save_app(app)
    update_status("empty", 0, "Aucun vrai article extrait ; aucun faux dossier publié.")
    print("Aucun vrai article extrait ; aucun faux dossier publié.")


if __name__ == "__main__":
    main()
