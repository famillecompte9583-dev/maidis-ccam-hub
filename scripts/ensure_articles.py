#!/usr/bin/env python3
"""Ne publie jamais de faux dossiers.

Ce script vérifie seulement que le pipeline a produit de vrais articles.
S'il n'y en a pas, il garde `articles` vide et écrit un diagnostic clair.
"""
from __future__ import annotations

from scripts.common_app import load_app, now_fr, save_app, update_status


def main() -> None:
    app = load_app()
    articles = app.get("articles", [])
    if isinstance(articles, list) and articles:
        update_status("articles_guard", "ok", {"count": len(articles), "message": "Vrais articles présents ; aucun fallback publié."})
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
    update_status("articles_guard", "empty", {"count": 0, "message": "Aucun vrai article extrait ; aucun faux dossier publié."})
    print("Aucun vrai article extrait ; aucun faux dossier publié.")


if __name__ == "__main__":
    main()
