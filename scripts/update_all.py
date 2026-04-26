#!/usr/bin/env python3
"""Générateur de données pour Annuaire CCAM Santé.
Produit data/app-data.json et data/app-data.js avec actes, veille, dossiers réécrits et changements.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import pathlib
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CACHE = ROOT / "cache" / "pdf"
PARIS = ZoneInfo("Europe/Paris")
CCAM_URL = "https://data.smartidf.services/api/records/1.0/download/?dataset=healthref-france-ccam&format=json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
]

RSS_FEEDS: list[tuple[str, str]] = []
AMELI_DOC_PAGES = [
    ("convention_dentistes", "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028"),
    ("calendrier_convention", "https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles"),
    ("ccam_medecins", "https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam"),
]
ARTICLE_SOURCES = [
    {"id":"convention-dentaire-2023-2028","category":"Dentaire","tag":"Convention","title":"Convention dentaire 2023-2028 : ce qu'il faut retenir","url":"https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028"},
    {"id":"calendrier-mesures-conventionnelles","category":"Dentaire","tag":"Calendrier","title":"Calendrier des mesures conventionnelles : points de vigilance","url":"https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles"},
    {"id":"tarifs-dentaires","category":"Tarifs","tag":"Tarifs","title":"Tarifs conventionnels dentaires : repères pratiques","url":"https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs"},
    {"id":"cent-pour-cent-sante-dentaire","category":"100 % Santé","tag":"100 % Santé","title":"100 % Santé dentaire : actes, matériaux et paniers de soins","url":"https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire"},
    {"id":"codage-ccam-medecins","category":"CCAM","tag":"CCAM","title":"Codage CCAM : retrouver et contrôler les actes médicaux","url":"https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam"},
]

RAC0 = set("HBKD140 HBKD212 HBKD213 HBKD244 HBKD300 HBKD396 HBKD431 HBKD462 HBLD031 HBLD032 HBLD033 HBLD035 HBLD038 HBLD083 HBLD090 HBLD101 HBLD123 HBLD138 HBLD148 HBLD203 HBLD215 HBLD224 HBLD231 HBLD232 HBLD259 HBLD262 HBLD349 HBLD350 HBLD364 HBLD370 HBLD474 HBLD490 HBLD634 HBLD680 HBLD734 HBLD785".split())
MOD = set("HBLD040 HBLD043 HBLD073 HBLD131 HBLD158 HBLD227 HBLD332 HBLD486 HBLD491 HBLD724 HBLD745".split())
PROTH_TERMS = ["couronne dentaire","prothese dentaire","prothèse dentaire","prothese amovible","prothèse amovible","bridge","inlay core","infrastructure coronoradiculaire"]
DENTAL_TERMS = "dentaire dent bucco bouche mandibul maxill gingiv parodont pulpe carie racine couronne prothese prothèse bridge incisive canine molaire premolaire prémolaire edent édent occlus arcade alveol alvéol orthodont endodont detartrage détartrage inlay onlay résine sillons".split()

STATIC_NEWS = [
    {"date":dt.date.today().isoformat(),"source":"Ameli","title":"Tarifs conventionnels et honoraires limites dentaires","url":"https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs","tag":"Tarifs"},
    {"date":dt.date.today().isoformat(),"source":"Ameli","title":"Matériaux et actes prothétiques inclus dans l'offre 100 % Santé dentaire","url":"https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire","tag":"100 % Santé"},
    {"date":dt.date.today().isoformat(),"source":"Ameli","title":"CCAM : codage des actes médicaux et téléchargement des versions PDF/Excel","url":"https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam","tag":"CCAM"},
]

def now_fr() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone(PARIS)

def fetch(url: str, timeout: int = 60, retries: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/json,application/pdf,*/*",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Cache-Control": "no-cache",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in {403,408,409,425,429,500,502,503,504}:
                raise
        except Exception as e:
            last = e
        time.sleep(min(2**attempt, 10) + random.random())
    raise last or RuntimeError(url)

def fnum(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return round(float(str(v).replace(",", ".")), 2)
    except Exception:
        return None

def dental(lib: str) -> bool:
    t = (lib or "").lower()
    return any(x in t for x in DENTAL_TERMS)

def panier_scope(code: str, lib: str) -> bool:
    t = (lib or "").lower()
    return code in RAC0 or code in MOD or any(x in t for x in PROTH_TERMS)

def classify(code: str, lib: str) -> tuple[str, str, str]:
    if code in RAC0:
        return "RAC 0 / 100 % Santé", "Haute", "Code prothétique reconnu dans le panier sans reste à charge."
    if code in MOD:
        return "RAC modéré / tarif maîtrisé", "Haute", "Code prothétique reconnu dans le panier à honoraires maîtrisés."
    if panier_scope(code, lib):
        return "Tarif libre ou à vérifier", "Moyenne", "Acte prothétique ou bucco-dentaire détecté, à vérifier selon le contexte."
    return "Hors périmètre panier 100 % Santé", "Haute", "Cet acte n'entre pas dans le périmètre des paniers 100 % Santé dentaires."

def normalize(raw: dict[str, Any]) -> dict[str, Any] | None:
    x = raw.get("fields", raw)
    code = str(x.get("code", "")).strip()
    lib = str(x.get("libelle", "")).strip()
    brss = fnum(x.get("tarif_1") or x.get("tarif_base") or x.get("brss"))
    if not code or brss is None:
        return None
    isdent = dental(lib)
    scope = panier_scope(code, lib)
    pan, cert, why = classify(code, lib)
    taux = 60 if isdent or scope else 70
    amo = round(brss * taux / 100, 2)
    return {"code":code,"activite":str(x.get("activite","")),"phase":str(x.get("phase","")),"libelle":lib,"brss":brss,"tarif_secteur_1_optam":brss,"taux_amo_standard":taux,"montant_amo_standard":amo,"panier_100_sante":pan,"certitude_panier":cert,"justification_panier":why,"perimetre_panier_100_sante":scope,"hors_perimetre_panier":not scope,"domaine":"Bucco-dentaire / stomatologie" if isdent or scope else "Médical CCAM","accord_prealable":x.get("accord_prealable") or "","code_maidis_suggere":f"{code}-{x.get('activite','')}-{x.get('phase','')}","notes_parametrage":"Taux et montant AMO indicatifs : à ajuster selon contexte patient, majorations et règles applicables."}

def local_app() -> dict[str, Any]:
    p = DATA / "app-data.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print("Lecture locale impossible", e)
        return {}

def load_records() -> list[dict[str, Any]]:
    try:
        raw = json.loads(fetch(CCAM_URL).decode("utf-8"))
        raw = raw.get("records", raw) if isinstance(raw, dict) else raw
        rec = [r for r in (normalize(i) for i in raw) if r]
        if rec:
            return rec
    except Exception as e:
        print("CCAM en ligne indisponible, repli local", e)
    return local_app().get("records", [])

def clean_text(src: str) -> str:
    src = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", src, flags=re.I|re.S)
    src = re.sub(r"<(nav|footer|header|aside)\b.*?</\1>", " ", src, flags=re.I|re.S)
    src = re.sub(r"<(h[1-4]|p|li|td|th|div|section|article)\b[^>]*>", "\n", src, flags=re.I)
    src = re.sub(r"<[^>]+>", " ", src)
    src = html.unescape(src)
    src = re.sub(r"\s+", " ", src).strip()
    junk = ["Javascript est désactivé", "Vous utilisez un navigateur obsolète", "accepter les cookies"]
    for j in junk:
        src = src.replace(j, "")
    return src.strip()

def codes(text: str) -> set[str]:
    return set(re.findall(r"\b[A-Z]{4}[0-9]{3}\b", text or ""))

def relevant_sentences(text: str, n: int = 8) -> list[str]:
    keys = "ccam tarif honoraires convention dentaire santé prise en charge acte remboursement prothèse panier devis patient chirurgien-dentiste".split()
    out: list[str] = []
    for s in re.split(r"(?<=[.!?])\s+", text or ""):
        s = re.sub(r"\s+", " ", s).strip()
        low = s.lower()
        if 80 <= len(s) <= 360 and any(k in low for k in keys):
            out.append(s)
        if len(out) >= n:
            break
    return out

def pdf_links(page_url: str, page: str) -> list[tuple[str, str]]:
    pat = re.compile(r"<a\b[^>]*href=[\"'](?P<href>[^\"']+\.pdf(?:\?[^\"']*)?)[\"'][^>]*>(?P<title>.*?)</a>", re.I|re.S)
    seen, out = set(), []
    for m in pat.finditer(page):
        url = urllib.parse.urljoin(page_url, html.unescape(m.group("href").strip()))
        title = re.sub(r"<[^>]+>", " ", m.group("title"))
        title = re.sub(r"\s+", " ", html.unescape(title)).strip() or pathlib.Path(url).name
        if url not in seen:
            out.append((title, url))
            seen.add(url)
    return out

def pdf_name(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", pathlib.Path(urllib.parse.urlparse(url).path).name or "document.pdf")

def download_pdf(url: str) -> pathlib.Path | None:
    try:
        data = fetch(url)
        if not data.startswith(b"%PDF"):
            return None
        CACHE.mkdir(parents=True, exist_ok=True)
        p = CACHE / pdf_name(url)
        p.write_bytes(data)
        return p
    except Exception as e:
        print("PDF ignoré", url, e)
        return None

def pdf_text(path: pathlib.Path | None, pages: int = 8) -> str:
    if not path:
        return ""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            txt = " ".join((p.extract_text() or "") for p in pdf.pages[:pages])
        return re.sub(r"\s+", " ", txt).strip()
    except Exception as e:
        print("Analyse PDF impossible", path, e)
        return ""

def docs_from_ameli(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    docs, found = [], set()
    for _, url in AMELI_DOC_PAGES:
        try:
            page = fetch(url).decode("utf-8", errors="ignore")
            for title, pdfurl in pdf_links(url, page):
                text = pdf_text(download_pdf(pdfurl), 10)
                c = codes(text)
                found |= c
                docs.append({"date":dt.date.today().isoformat(),"source":"Ameli","title":title,"url":pdfurl,"tag":"Document","summary":text[:300]+("…" if len(text)>300 else ""),"codes":sorted(c)})
        except Exception as e:
            print("Docs ignorés", url, e)
    known = {r["code"] for r in records}
    for code in sorted(found - known):
        records.append({"code":code,"activite":"","phase":"","libelle":"Code détecté dans un document institutionnel (à vérifier)","brss":None,"tarif_secteur_1_optam":None,"taux_amo_standard":None,"montant_amo_standard":None,"panier_100_sante":"À vérifier","certitude_panier":"Basse","justification_panier":"Code non présent dans la base principale, détecté dans un document de référence.","perimetre_panier_100_sante":False,"hors_perimetre_panier":True,"domaine":"Médical CCAM","accord_prealable":"","code_maidis_suggere":f"{code}--","notes_parametrage":"Information détectée automatiquement : à vérifier avant utilisation."})
    return docs

def rss_news() -> list[dict[str, Any]]:
    items = []
    for src, url in RSS_FEEDS:
        try:
            root = ET.fromstring(fetch(url))
            for it in root.findall(".//item")[:5]:
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                date = (it.findtext("pubDate") or dt.date.today().isoformat()).strip()
                if title and link:
                    items.append({"date":date,"source":src,"title":title,"url":link,"tag":"RSS"})
        except Exception as e:
            print("RSS ignoré", src, e)
    return (items + STATIC_NEWS)[:20]

def sample_codes(records: list[dict[str, Any]], predicate, limit: int = 80) -> list[str]:
    out = []
    for r in records:
        if r.get("code") and predicate(r):
            out.append(r["code"])
    return sorted(set(out))[:limit]

def stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    dental_records = [r for r in records if r.get("domaine") != "Médical CCAM"]
    medical_records = [r for r in records if r.get("domaine") == "Médical CCAM"]
    rac0 = [r for r in records if str(r.get("panier_100_sante", "")).startswith("RAC 0")]
    mod = [r for r in records if str(r.get("panier_100_sante", "")).startswith("RAC modéré")]
    brss_values = [r["brss"] for r in records if isinstance(r.get("brss"), (int, float))]
    return {"total":len(records),"dental":len(dental_records),"medical":len(medical_records),"rac0":len(rac0),"mod":len(mod),"brss_min":min(brss_values) if brss_values else None,"brss_max":max(brss_values) if brss_values else None}

def article_codes(source: dict[str, str], records: list[dict[str, Any]], extracted: set[str]) -> list[str]:
    sid = source["id"]
    linked = set(extracted)
    if "cent-pour-cent" in sid:
        linked |= RAC0 | MOD
    elif "tarifs" in sid:
        linked |= set(sample_codes(records, lambda r: r.get("domaine") != "Médical CCAM" and r.get("brss") is not None, 70))
    elif "convention" in sid or "calendrier" in sid:
        linked |= set(sample_codes(records, lambda r: r.get("domaine") != "Médical CCAM", 70))
    elif "codage" in sid:
        linked |= set(sample_codes(records, lambda r: r.get("domaine") == "Médical CCAM", 70))
    existing = {r["code"] for r in records if r.get("code")}
    return sorted(c for c in linked if c in existing)[:120]

def build_body(source: dict[str, str], records: list[dict[str, Any]], extracted_text: str, extracted_bits: list[str], linked_codes: list[str], pdf_count: int) -> tuple[str, str]:
    st = stats(records)
    title = source["title"]
    source_note = f"Source suivie : <a href=\"{html.escape(source['url'])}\" target=\"_blank\" rel=\"noopener\">page officielle Ameli</a>."
    intro = f"Ce dossier est réécrit automatiquement à partir des données CCAM synchronisées, des documents suivis et de la page institutionnelle associée. La génération actuelle contient {st['total']:,} actes, dont {st['dental']:,} actes bucco-dentaires et {st['medical']:,} actes médicaux.".replace(",", " ")
    facts = []
    if extracted_bits:
        facts.extend(extracted_bits[:4])
    if "cent-pour-cent" in source["id"]:
        facts.extend([
            f"L’annuaire identifie {st['rac0']} codes classés RAC 0 / 100 % Santé et {st['mod']} codes classés RAC modéré ou tarif maîtrisé.",
            "Les actes concernés doivent être vérifiés avec le matériau, la localisation, le panier de soins et le contexte patient.",
            "Un code dentaire ne suffit pas toujours à déterminer seul le panier applicable : la règle métier doit être rapprochée du devis et de la prise en charge.",
        ])
    elif "tarifs" in source["id"]:
        facts.extend([
            "La BRSS sert de base de lecture pour estimer le remboursement AMO, mais elle ne remplace pas les règles applicables au patient.",
            f"Dans la génération actuelle, les tarifs de base disponibles s’étendent de {st['brss_min']} € à {st['brss_max']} € selon les actes référencés." if st['brss_min'] is not None else "Les tarifs de base sont repris lorsqu’ils sont présents dans la source CCAM synchronisée.",
            "Les honoraires limites et paniers dentaires doivent être rapprochés des textes officiels avant validation.",
        ])
    elif "codage" in source["id"]:
        facts.extend([
            "La lecture fiable d’un acte repose sur le code, l’activité, la phase, le libellé et la base tarifaire.",
            "Le moteur de recherche permet de contrôler rapidement un code, un libellé, un domaine ou un panier de soins.",
            "Les actes médicaux non dentaires sont conservés dans l’annuaire même lorsqu’ils sont hors périmètre des paniers 100 % Santé dentaires.",
        ])
    else:
        facts.extend([
            "Les mesures conventionnelles doivent être rapprochées des actes CCAM réellement utilisés et de leur paramétrage métier.",
            "Les actes prothétiques demandent une attention particulière sur le panier de soins, le tarif et la justification affichée.",
            "Les cas particuliers comme C2S, ALD, maternité, AT/MP, régime local ou majorations peuvent modifier la lecture du remboursement.",
        ])
    facts = [f for i, f in enumerate(facts) if f and f not in facts[:i]][:7]
    summary = facts[0] if facts else f"Dossier pratique généré pour {title}."
    html_bits = [
        f"<p>{html.escape(intro)}</p>",
        "<h2>À retenir</h2><ul>",
        "".join(f"<li>{html.escape(x)}</li>" for x in facts[:5]),
        "</ul>",
        "<h2>Impact pratique</h2>",
        "<p>Ce dossier aide à contrôler les actes, les paniers, les tarifs de base et les points de vigilance avant export ou paramétrage. Les valeurs affichées restent une aide de lecture et doivent être validées avec les règles officielles et le contexte patient.</p>",
        "<h2>Codes liés</h2>",
        f"<p>{html.escape(', '.join(linked_codes[:80])) if linked_codes else 'Aucun code lié n’a pu être déterminé pour cette génération.'}</p>",
        "<h2>Traçabilité</h2>",
        f"<p>{source_note} {pdf_count} document(s) PDF lié(s) détecté(s) pendant la synchronisation. Longueur de texte institutionnel exploitable : {len(extracted_text)} caractères.</p>",
    ]
    return summary, "".join(html_bits)

def make_article(source: dict[str, str], records: list[dict[str, Any]]) -> dict[str, Any]:
    page_text = ""
    pdf_texts: list[str] = []
    pdf_count = 0
    extracted_codes: set[str] = set()
    try:
        page = fetch(source["url"]).decode("utf-8", errors="ignore")
        page_text = clean_text(page)
        extracted_codes |= codes(page_text)
        for _title, url in pdf_links(source["url"], page)[:5]:
            txt = pdf_text(download_pdf(url), 8)
            if txt:
                pdf_count += 1
                pdf_texts.append(txt)
                extracted_codes |= codes(txt)
    except Exception as e:
        print("Article page ignorée", source["url"], e)
    extracted_text = (page_text + " " + " ".join(pdf_texts)).strip()
    bits = relevant_sentences(extracted_text, 8)
    linked = article_codes(source, records, extracted_codes)
    summary, body = build_body(source, records, extracted_text, bits, linked, pdf_count)
    return {"id":source["id"],"title":source["title"],"date":dt.date.today().isoformat(),"source":"Ameli","source_url":source["url"],"category":source["category"],"tag":source["tag"],"summary":summary,"content_html":body,"codes":linked,"codes_detectes":sorted(extracted_codes),"pdf_count":pdf_count,"extracted_chars":len(extracted_text),"confidence":"Haute" if len(extracted_text) > 500 else "Moyenne"}

def build_articles(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    arts = [make_article(s, records) for s in ARTICLE_SOURCES]
    link: dict[str, list[str]] = {}
    for a in arts:
        for c in a.get("codes", []):
            link.setdefault(c, []).append(a["id"])
    for r in records:
        if r.get("code") in link:
            r["articles_lies"] = link[r["code"]][:8]
    return arts

def key(r: dict[str, Any]) -> str:
    return f"{r.get('code','')}|{r.get('activite','')}|{r.get('phase','')}"

def changes(prev: list[dict[str, Any]], cur: list[dict[str, Any]]) -> dict[str, Any]:
    old = {key(r):r for r in prev if r.get("code")}
    new = {key(r):r for r in cur if r.get("code")}
    mod = []
    for k in sorted(set(old) & set(new)):
        b, a = old[k], new[k]
        fields = [f for f in ["libelle","brss","panier_100_sante","domaine","accord_prealable"] if b.get(f) != a.get(f)]
        if fields:
            mod.append({"code":a.get("code"),"activite":a.get("activite"),"phase":a.get("phase"),"libelle":a.get("libelle"),"fields":fields,"before":{f:b.get(f) for f in fields},"after":{f:a.get(f) for f in fields}})
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    return {"date":now_fr().isoformat(timespec="seconds"),"added_count":len(added),"removed_count":len(removed),"modified_count":len(mod),"added":[new[k] for k in added[:80]],"removed":[old[k] for k in removed[:80]],"modified":mod[:120]}

def meta(records: list[dict[str, Any]], articles: list[dict[str, Any]]) -> dict[str, Any]:
    return {"generated":now_fr().isoformat(timespec="seconds"),"timezone":"Europe/Paris","total":len(records),"medical":sum(1 for r in records if r["domaine"]=="Médical CCAM"),"bucco_dentaire":sum(1 for r in records if r["domaine"]!="Médical CCAM"),"hors_perimetre_panier":sum(1 for r in records if r["hors_perimetre_panier"]),"rac0":sum(1 for r in records if str(r["panier_100_sante"]).startswith("RAC 0")),"modere":sum(1 for r in records if str(r["panier_100_sante"]).startswith("RAC modéré")),"articles":len(articles),"source":"CCAM open data + veille institutionnelle","version":"v6-articles-enrichis"}

def fingerprint(app: dict[str, Any]) -> str:
    lite = {"meta":{k:v for k,v in app.get("meta",{}).items() if k != "generated"},"records":app.get("records",[]),"articles":app.get("articles",[]),"news":app.get("news",[])}
    return hashlib.sha256(json.dumps(lite, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

def main() -> None:
    previous = local_app()
    prev_records = previous.get("records", [])
    records = load_records()
    news = (rss_news() + docs_from_ameli(records))[:40]
    articles = build_articles(records)
    app = {"meta":meta(records, articles),"records":records,"news":news,"articles":articles,"changes":changes(prev_records, records),"profiles":{"medical_standard":70,"dental_standard":60,"user_example":70}}
    app["meta"]["fingerprint"] = fingerprint(app)
    DATA.mkdir(exist_ok=True)
    (DATA / "app-data.json").write_text(json.dumps(app, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "app-data.js").write_text("window.CCAM_APP_DATA = " + json.dumps(app, ensure_ascii=False) + ";\n", encoding="utf-8")
    print("OK", app["meta"], "articles", len(articles))

if __name__ == "__main__":
    main()
