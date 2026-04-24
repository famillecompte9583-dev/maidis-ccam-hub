#!/usr/bin/env python3
"""Reconstruit la base embarquée du site.
- Récupère la CCAM open data.
- Recalcule les champs d'aide au paramétrage Maidis.
- Récupère des sources de veille côté serveur pour éviter les blocages CORS.
- Produit data/app-data.json et data/app-data.js, utilisables hors ligne.
"""
import datetime, json, pathlib, re, urllib.request, xml.etree.ElementTree as ET
ROOT = pathlib.Path(__file__).resolve().parents[1]
CCAM_URL = "https://data.smartidf.services/api/records/1.0/download/?dataset=healthref-france-ccam&format=json"
RSS_FEEDS = [
    ("Faculté de chirurgie dentaire de Strasbourg", "https://chirurgie-dentaire.unistra.fr/actualites/feed.xml"),
]
RAC0 = set("HBKD140 HBKD212 HBKD213 HBKD244 HBKD300 HBKD396 HBKD431 HBKD462 HBLD031 HBLD032 HBLD033 HBLD035 HBLD038 HBLD083 HBLD090 HBLD101 HBLD123 HBLD138 HBLD148 HBLD203 HBLD215 HBLD224 HBLD231 HBLD232 HBLD259 HBLD262 HBLD349 HBLD350 HBLD364 HBLD370 HBLD474 HBLD490 HBLD634 HBLD680 HBLD734 HBLD785".split())
MOD = set("HBLD040 HBLD043 HBLD073 HBLD131 HBLD158 HBLD227 HBLD332 HBLD486 HBLD491 HBLD724 HBLD745".split())
PROTH_TERMS = ["couronne dentaire","prothèse dentaire","prothese dentaire","prothèse amovible","prothese amovible","bridge","inlay core","infrastructure coronoradiculaire"]
DENTAL_TERMS = ["dentaire","dent","bucco","bouche","mandibul","maxill","gingiv","parodont","pulpe","carie","racine","couronne","prothèse dentaire","prothese dentaire","bridge","incisive","canine","molaire","prémolaire","premolaire","édent","edent","occlus","arcade dentaire","alvéol","alveol","orthodont","endodont","détartrage","detartrage","inlay","onlay","plaque base résine","scellement prophylactique","sillons"]

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Maidis-CCAM-Hub/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def to_float(v):
    if v in (None, ""): return None
    try: return round(float(str(v).replace(",", ".")), 2)
    except Exception: return None

def is_dentalish(lib):
    t=(lib or "").lower()
    return any(term in t for term in DENTAL_TERMS)

def is_panier_scope(code, lib):
    t=(lib or "").lower()
    return code in RAC0 or code in MOD or any(term in t for term in PROTH_TERMS)

def classify_panier(code, lib):
    if code in RAC0:
        return "RAC 0 / 100 % Santé", "Haute", "Code prothétique reconnu dans le panier sans reste à charge."
    if code in MOD:
        return "RAC modéré / tarif maîtrisé", "Haute", "Code prothétique reconnu dans le panier à honoraires maîtrisés."
    if is_panier_scope(code, lib):
        return "Tarif libre ou à vérifier", "Moyenne", "Acte prothétique/bucco-dentaire détecté, mais non présent dans les listes embarquées RAC 0/modéré."
    return "Hors périmètre panier 100 % Santé", "Haute", "Les paniers 100 % Santé concernent les prothèses dentaires : couronnes, bridges et prothèses amovibles. Cet acte n’entre pas dans ce périmètre."

def normalize_record(raw):
    fields = raw.get("fields", raw)
    code = str(fields.get("code", "")).strip()
    lib = str(fields.get("libelle", "")).strip()
    brss = to_float(fields.get("tarif_1") or fields.get("tarif_base") or fields.get("brss"))
    if not code or brss is None:
        return None
    dental = is_dentalish(lib)
    scope = is_panier_scope(code, lib)
    panier, cert, reason = classify_panier(code, lib)
    taux = 60 if dental or scope else 70
    amo = round(brss*taux/100, 2)
    return {
        "code": code,
        "activite": str(fields.get("activite", "")),
        "phase": str(fields.get("phase", "")),
        "libelle": lib,
        "brss": brss,
        "tarif_secteur_1_optam": brss,
        "taux_amo_standard": taux,
        "montant_amo_standard": amo,
        "panier_100_sante": panier,
        "certitude_panier": cert,
        "justification_panier": reason,
        "perimetre_panier_100_sante": scope,
        "hors_perimetre_panier": not scope,
        "domaine": "Bucco-dentaire / stomatologie" if dental or scope else "Médical CCAM",
        "accord_prealable": fields.get("accord_prealable") or "",
        "code_maidis_suggere": f"{code}-{fields.get('activite','')}-{fields.get('phase','')}",
        "notes_parametrage": "Taux et montant AMO indicatifs : à ajuster selon contexte patient (ALD, maternité, AT/MP, C2S, Alsace-Moselle, DOM), majorations et règles Maidis."
    }

def read_rss():
    items=[]
    for source,url in RSS_FEEDS:
        try:
            xml=fetch(url)
            root=ET.fromstring(xml)
            for item in root.findall(".//item")[:5]:
                title=(item.findtext("title") or "").strip()
                link=(item.findtext("link") or "").strip()
                date=(item.findtext("pubDate") or datetime.date.today().isoformat()).strip()
                if title and link:
                    items.append({"date": date, "source": source, "title": title, "url": link, "tag":"RSS"})
        except Exception as e:
            print("RSS ignoré", source, e)
    # sources permanentes si aucun RSS ou en complément
    items.extend([
        {"date": datetime.date.today().isoformat(), "source":"Ameli", "title":"Tarifs conventionnels et honoraires limites dentaires", "url":"https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs", "tag":"Tarifs"},
        {"date": datetime.date.today().isoformat(), "source":"Ameli", "title":"Matériaux et actes prothétiques inclus dans l’offre 100 % Santé dentaire", "url":"https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire", "tag":"100 % Santé"},
        {"date": datetime.date.today().isoformat(), "source":"Ameli", "title":"CCAM : codage des actes médicaux et téléchargement des versions PDF/Excel", "url":"https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam", "tag":"CCAM"},
    ])
    return items[:20]

def main():
    raw=json.loads(fetch(CCAM_URL).decode("utf-8"))
    if isinstance(raw, dict) and "records" in raw:
        raw = raw["records"]
    records=[r for r in (normalize_record(x) for x in raw) if r]
    meta={
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "total": len(records),
        "medical": sum(1 for r in records if r["domaine"] == "Médical CCAM"),
        "bucco_dentaire": sum(1 for r in records if r["domaine"] != "Médical CCAM"),
        "hors_perimetre_panier": sum(1 for r in records if r["hors_perimetre_panier"]),
        "rac0": sum(1 for r in records if r["panier_100_sante"].startswith("RAC 0")),
        "modere": sum(1 for r in records if r["panier_100_sante"].startswith("RAC modéré")),
        "source": "CCAM open data + règles Ameli 100 % Santé + veille RSS",
        "version": "v3-maidis"
    }
    app={"meta":meta,"records":records,"news":read_rss(),"profiles":{"medical_standard":70,"dental_standard":60,"user_example":70}}
    (ROOT/"data").mkdir(exist_ok=True)
    (ROOT/"data"/"app-data.json").write_text(json.dumps(app, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT/"data"/"app-data.js").write_text("window.CCAM_APP_DATA = "+json.dumps(app, ensure_ascii=False)+";\n", encoding="utf-8")
    print("OK", meta)

if __name__ == "__main__":
    main()
