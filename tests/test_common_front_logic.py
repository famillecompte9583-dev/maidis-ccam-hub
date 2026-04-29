from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DATA = ROOT / "data" / "app-data.json"


def load_app() -> dict:
    return json.loads(APP_DATA.read_text(encoding="utf-8"))


def test_app_data_has_records() -> None:
    app = load_app()
    assert isinstance(app.get("records"), list)
    assert len(app["records"]) >= 3000


def test_records_have_expected_keys() -> None:
    app = load_app()
    sample = app["records"][:20]
    required = {"code", "libelle", "domaine", "panier_100_sante"}
    for record in sample:
        assert required.issubset(record.keys())


def test_articles_are_separate_from_public_api_sources() -> None:
    app = load_app()
    articles = app.get("articles", [])
    public_sources = app.get("public_api_sources", [])
    assert isinstance(articles, list)
    assert isinstance(public_sources, list)
    article_titles = {item.get("title") for item in articles if isinstance(item, dict)}
    source_titles = {item.get("title") for item in public_sources if isinstance(item, dict)}
    assert not (article_titles & source_titles)
