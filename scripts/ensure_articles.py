#!/usr/bin/env python3
"""Garantit qu'il existe des dossiers publics même si le crawl Ameli ne produit rien.

Le crawler reste prioritaire. Ce script n'intervient que si `articles` est vide.
Il crée alors quelques dossiers prudents, traçables et reliés à la base CCAM locale,
afin que la page Dossiers ne soit jamais vide et que la relecture Gemini ait une
matière éditoriale à améliorer.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
from typing import Any
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
APP_PATH = DATA_DIR / "app-data.json"
STATUS_PATH = DATA_DIR / "sync-status.json"
PARIS = ZoneInfo("Europe/Paris")

SOURCES = [
    {
        "id": "codage-ccam-medecins",
        "title": "Codage CCAM : repères pratiques pour contrôler un acte",
        "category": "CCAM",
        "source_url": "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam",
        "selector": "medical",
    },
    {
        "id": "tarifs-conventionnels-brss",
        "title": "Tarifs conventionnels, BRSS et montant AMO : lecture prudente",
        "category": "Tarifs",
        "source_url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs",
        "selector": "dental",
    },
    {
        "id": "cent-pour-cent-sante-dentaire",
        "title": "100 % Santé dentaire : paniers, codes et points de vigilance",
        "category": "100 % Santé",
        "source_url": "https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire",
        "selector": "rac",
    },
    {
        "id": "convention-dentaire-2023-2028",
        "title": "Convention dentaire 2023-2028 : impact pour le suivi des actes",
        "category": "Convention",
        "source_url": "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028",
        "selector": "dental",
    },
    {
        "id": "calendrier-mesures-conventionnelles",
        "title": "Calendrier conventionnel : vérifier les dates et le paramétrage",
        "category": "Dentaire",
        "source_url": "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles",
        "selector": "dental",
    },
]


def now_fr() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS).isoformat(timespec="seconds")


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def load_app() -> dict[str, Any]:
    if not APP_PATH.exists() or APP_PATH.stat().st_size == 0:
        raise SystemExit("data/app-data.json absent ou vide")
    return json.loads(APP_PATH.read_text(encoding="utf-8"))


def save_app(app: dict[str, Any]) -> None:
    APP_PATH.write_text(json.dumps(app, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "app-data.js").write_text("window.CCAM_APP_DATA = " + json.dumps(app, ensure_ascii=False) + ";\n", encoding="utf-8")


def update_status(count: int, mode: str) -> None:
    if STATUS_PATH.exists() and STATUS_PATH.stat().st_size:
        try:
            status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except Exception:
            status = {}
    else:
        status = {}
    status["articles"] = {
        "status": "ok",
        "generated": now_fr(),
        "count": count,
        "mode": mode,
        "note": "Dossiers de secours générés car le crawl Ameli n'a produit aucun article exploitable." if mode == "curated-fallback" else "Articles issus du crawl principal.",
    }
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def select_codes(records: list[dict[str, Any]], selector: str, limit: int = 80) -> list[str]:
    out: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        code = record.get("code")
        if not isinstance(code, str) or code in out:
            continue
        domaine = str(record.get("domaine", ""))
        panier = str(record.get("panier_100_sante", ""))
        if selector == "medical" and domaine == "Médical CCAM":
            out.append(code)
        elif selector == "dental" and domaine != "Médical CCAM":
            out.append(code)
        elif selector == "rac" and panier.startswith(("RAC 0", "RAC mod")):
            out.append(code)
        if len(out) >= limit:
            break
    return out


def build_article(source: dict[str, str], records: list[dict[str, Any]]) -> dict[str, Any]:
    codes = select_codes(records, source["selector"])
    category = source["category"]
    title = source["title"]
    source_url = source["source_url"]
    sample = ", ".join(codes[:30]) if codes else "aucun code associé automatiquement"
    generated = now_fr()

    if category == "100 % Santé":
        focus = "les paniers de soins, les matériaux, la localisation, le devis et le contexte patient"
        caution = "Un code associé au 100 % Santé ne suffit jamais à conclure seul : le panier doit être vérifié avec les règles officielles et le cas réel."
    elif category == "Tarifs":
        focus = "la BRSS, le taux indicatif, le montant AMO estimé et les écarts possibles selon le patient"
        caution = "Les montants affichés sont des repères de contrôle et ne remplacent pas les règles opposables ni le logiciel métier."
    elif category == "Convention":
        focus = "les mesures conventionnelles, leur calendrier d'application et leurs conséquences de paramétrage"
        caution = "Toute date ou mesure conventionnelle doit être rapprochée de la source officielle avant mise en production."
    elif category == "CCAM":
        focus = "le couple code, activité, phase, libellé et base tarifaire"
        caution = "La recherche dans l'annuaire aide au contrôle, mais la source CCAM officielle reste prioritaire."
    else:
        focus = "les actes bucco-dentaires, les tarifs et les points de vigilance de prise en charge"
        caution = "Les informations doivent être validées avec les textes officiels et le contexte patient."

    content_html = "".join([
        "<p>Ce dossier de secours a été généré automatiquement parce que le crawl direct des pages suivies n'a pas produit d'article exploitable. Il sert de base prudente de lecture et peut être relu par Gemini si la clé API est disponible.</p>",
        "<h2>Objectif du dossier</h2>",
        f"<p>Il aide à contrôler {esc(focus)} à partir de la base CCAM synchronisée et des sources institutionnelles suivies.</p>",
        "<h2>Points de contrôle</h2>",
        "<ul>",
        "<li>Identifier le code CCAM, l'activité et la phase avant toute interprétation.</li>",
        "<li>Comparer le libellé, la BRSS et le panier affiché avec la source officielle.</li>",
        "<li>Ne pas déduire automatiquement une prise en charge sans contexte patient.</li>",
        "<li>Conserver la source Ameli comme référence prioritaire.</li>",
        "</ul>",
        "<h2>Codes associés</h2>",
        f"<p>Exemples de codes reliés à ce thème : {esc(sample)}.</p>",
        "<h2>Prudence métier</h2>",
        f"<p>{esc(caution)}</p>",
        "<h2>Source et traçabilité</h2>",
        f"<p>Source officielle suivie : <a href=\"{esc(source_url)}\" target=\"_blank\" rel=\"noopener noreferrer\">{esc(title)}</a>. Dossier généré le {esc(generated)}.</p>",
    ])

    return {
        "id": source["id"],
        "title": title,
        "date": dt.date.today().isoformat(),
        "source": "Ameli",
        "source_url": source_url,
        "category": category,
        "tag": category,
        "summary": f"Dossier prudent sur {category.lower()} généré à partir de la base CCAM synchronisée et des sources institutionnelles suivies.",
        "content_html": content_html,
        "codes": codes,
        "codes_detectes": codes,
        "pdf_count": 0,
        "extracted_chars": len(content_html),
        "confidence": "Moyenne",
        "fallback_generation": {
            "mode": "curated-fallback",
            "generated": generated,
            "reason": "crawl_ameli_empty",
        },
    }


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
    current = app.get("articles", [])
    if isinstance(current, list) and len(current) > 0:
        update_status(len(current), "ameli-crawl-blog")
        print(f"Articles déjà présents : {len(current)}")
        return

    records = app.get("records", [])
    if not isinstance(records, list) or not records:
        raise SystemExit("Aucun record CCAM disponible pour créer les dossiers de secours")

    articles = [build_article(source, records) for source in SOURCES]
    app["articles"] = articles
    app.setdefault("meta", {})["articles"] = len(articles)
    app["meta"]["article_generation"] = {
        "mode": "curated-fallback",
        "generated": now_fr(),
        "pages_scanned": 0,
        "description": "Dossiers de secours générés car le crawl Ameli n'a produit aucun article exploitable.",
    }
    link_articles_to_records(app)
    save_app(app)
    update_status(len(articles), "curated-fallback")
    print(f"Dossiers de secours générés : {len(articles)}")


if __name__ == "__main__":
    main()
