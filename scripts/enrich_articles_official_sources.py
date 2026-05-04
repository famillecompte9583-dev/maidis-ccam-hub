#!/usr/bin/env python3
"""Génère des dossiers ciblés CCAM/conventions depuis sources institutionnelles fiables.

Sources privilégiées :
- Ameli / Assurance Maladie : nomenclatures, codage CCAM, conventions, tarifs.
- ATIH : informations de campagne, nomenclatures et changements de codage.
- Légifrance : arrêtés/avis portant modification de la CCAM ou conventions.

Le script ne publie que des contenus reliés à CCAM, actes, tarifs, conventions,
remboursement, 100 % Santé, dentaire, NGAP ou nomenclatures. Les autres contenus
sont ignorés et tracés dans le statut.
"""
from __future__ import annotations

import datetime as dt
import html
import json
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
DATA_DIR = ROOT / 'data'
APP_PATH = DATA_DIR / 'app-data.json'
STATUS_PATH = DATA_DIR / 'sync-status.json'
PARIS = ZoneInfo('Europe/Paris')

MAX_ARTICLES = 24
MAX_TEXT_CHARS = 38000
MIN_TEXT_CHARS = 450
MIN_YEAR = dt.date.today().year - 3
MIN_DATE = dt.date(MIN_YEAR, 1, 1)

OFFICIAL_INDEX_SOURCES = [
    {
        'name': 'Ameli - CCAM actes médicaux',
        'url': 'https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam',
        'category': 'CCAM',
        'priority': 1,
    },
    {
        'name': 'Ameli - convention nationale chirurgiens-dentistes 2023-2028',
        'url': 'https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028',
        'category': 'Convention dentaire',
        'priority': 2,
    },
    {
        'name': 'Ameli - calendrier des mesures conventionnelles dentaires',
        'url': 'https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/calendrier-mesures-conventionnelles',
        'category': 'Convention dentaire',
        'priority': 3,
    },
    {
        'name': 'Ameli - tarifs conventionnels dentaires',
        'url': 'https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs',
        'category': 'Tarifs dentaires',
        'priority': 4,
    },
    {
        'name': 'Ameli - 100 % Santé dentaire',
        'url': 'https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/prescription-prise-charge/materieux-actes-prothetiques-100-sante-dentaire',
        'category': '100 % Santé',
        'priority': 5,
    },
    {
        'name': 'ATIH - informations médicales et nomenclatures',
        'url': 'https://www.atih.sante.fr/informations-medicales',
        'category': 'Nomenclatures / ATIH',
        'priority': 6,
    },
    {
        'name': 'Légifrance - recherche CCAM',
        'url': 'https://www.legifrance.gouv.fr/search/all?tab_selection=all&searchField=ALL&query=CCAM%20nomenclature%20actes%20tarifs',
        'category': 'Textes officiels',
        'priority': 7,
    },
]

FALLBACK_ARTICLE_TOPICS = [
    {
        'id': 'veille-ccam-changements-codes-et-tarifs',
        'title': 'Veille CCAM : changements de codes, tarifs et règles de facturation',
        'category': 'CCAM',
        'source': 'Ameli / Assurance Maladie / Légifrance / ATIH',
        'source_url': 'https://www.ameli.fr/medecin/exercice-liberal/facturation-remuneration/consultations-actes/nomenclatures-codage/codage-actes-medicaux-ccam',
        'summary': 'Synthèse opérationnelle centrée sur les changements de codes CCAM, les tarifs et les règles de facturation à surveiller.',
    },
    {
        'id': 'veille-convention-dentaire-2023-2028',
        'title': 'Convention dentaire 2023-2028 : impacts sur actes, paniers et paramétrage',
        'category': 'Convention dentaire',
        'source': 'Ameli / Assurance Maladie',
        'source_url': 'https://www.ameli.fr/chirurgien-dentiste/textes-reference/convention/convention-nationale-2023-2028',
        'summary': 'Points de vigilance pour relier la convention dentaire aux actes CCAM, aux paniers 100 % Santé et aux tarifs maîtrisés.',
    },
    {
        'id': 'veille-tarifs-dentaires-et-100-sante',
        'title': 'Tarifs dentaires et 100 % Santé : contrôles à prévoir dans les dossiers CCAM',
        'category': 'Tarifs dentaires',
        'source': 'Ameli / Assurance Maladie',
        'source_url': 'https://www.ameli.fr/chirurgien-dentiste/exercice-liberal/facturation-remuneration/tarifs-conventionnels/tarifs',
        'summary': 'Dossier de suivi des tarifs conventionnels dentaires, honoraires limites, RAC 0 et paniers de soins.',
    },
]

KEYWORDS = [
    'ccam','classification commune des actes médicaux','acte','actes médicaux','codage','code','nomenclature',
    'tarif','tarifs','honoraire','honoraires','facturation','remboursement','prise en charge','brss','base de remboursement',
    'convention','avenant','chirurgien-dentiste','dentaire','bucco-dentaire','100 % santé','100% santé','panier','prothèse',
    'ngap','assurance maladie','ameli','atih','légifrance','legifrance','arrêté','arrete','journal officiel',
]
ANTIBOT_RE = re.compile(r'(cloudflare|just a moment|captcha|ray id|not a bot|vérification de sécurité|verification de securite)', re.I)
CODE_RE = re.compile(r'\b[A-Z]{4}\d{3}\b')
DATE_RE = re.compile(r'\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b|\b(\d{1,2})/(\d{1,2})/(20\d{2})\b')

class Extractor(HTMLParser):
    skip = {'script','style','svg','nav','footer','header','aside','form','iframe'}
    block = {'h1','h2','h3','h4','p','li','td','th','div','section','article','br','time'}
    def __init__(self):
        super().__init__(); self.parts=[]; self.links=[]; self.href=None; self.linktext=[]; self.depth=0
    def handle_starttag(self, tag, attrs):
        tag=tag.lower(); attrs=dict(attrs)
        if tag in self.skip: self.depth+=1
        if self.depth: return
        if tag=='a': self.href=attrs.get('href'); self.linktext=[]
        if tag=='time' and attrs.get('datetime'): self.parts.append('\n'+attrs['datetime']+'\n')
        if tag in {'h1','h2','h3','h4'}: self.parts.append('\n## ')
        elif tag=='li': self.parts.append('\n- ')
        elif tag in self.block: self.parts.append('\n')
    def handle_endtag(self, tag):
        tag=tag.lower()
        if tag in self.skip and self.depth: self.depth-=1; return
        if self.depth: return
        if tag=='a' and self.href:
            label=' '.join(self.linktext).strip()
            self.links.append((label,self.href)); self.href=None; self.linktext=[]
        if tag in self.block: self.parts.append('\n')
    def handle_data(self, data):
        if self.depth: return
        val=re.sub(r'\s+',' ', html.unescape(data or '')).strip()
        if not val: return
        self.parts.append(val+' ')
        if self.href: self.linktext.append(val)
    def result(self):
        txt=''.join(self.parts)
        txt=re.sub(r'\n{3,}','\n\n',txt); txt=re.sub(r'[ \t]{2,}',' ',txt)
        return txt.strip(), self.links

def now_fr(): return dt.datetime.now(dt.timezone.utc).astimezone(PARIS).isoformat(timespec='seconds')
def esc(v): return html.escape(str(v or ''), quote=True)
def slugify(s):
    s=s.lower().translate(str.maketrans('éèêëàâäçîïôöùûüÿñ','eeeeaaaciioouuuyn'))
    return re.sub(r'[^a-z0-9]+','-',s).strip('-')[:92] or 'article-ccam'
def clean(t):
    t=html.unescape(t or ''); t=re.sub(r'<[^>]+>',' ',t); t=re.sub(r'\s+',' ',t)
    return t.strip()
def fetch(url, timeout=35):
    req=urllib.request.Request(url, headers={'User-Agent':'maidis-ccam-hub/1.0 veille CCAM officielle','Accept':'text/html,application/xml,text/xml,text/plain,*/*;q=0.5','Accept-Language':'fr-FR,fr;q=0.9'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')
def text_and_links(raw, base):
    p=Extractor(); p.feed(raw); text, links=p.result()
    out=[]
    for label, href in links:
        url=urllib.parse.urljoin(base, href)
        if url.startswith('http'): out.append((clean(label), url))
    return clean(text), out
def date_from_text(text):
    # ISO or French numeric dates; fallback today for official index pages only.
    m=DATE_RE.search(text or '')
    if not m: return None
    try:
        if m.group(1): return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return dt.date(int(m.group(6)), int(m.group(5)), int(m.group(4)))
    except Exception: return None
def relevant(text):
    low=(text or '').lower()
    score=sum(1 for k in KEYWORDS if k in low)
    return score>=2, score
def load_app():
    if not APP_PATH.exists(): raise SystemExit('data/app-data.json absent')
    return json.loads(APP_PATH.read_text(encoding='utf-8'))
def save_app(app):
    DATA_DIR.mkdir(exist_ok=True)
    APP_PATH.write_text(json.dumps(app, ensure_ascii=False, indent=2), encoding='utf-8')
    (DATA_DIR/'app-data.js').write_text('window.CCAM_APP_DATA = '+json.dumps(app, ensure_ascii=False)+';\n', encoding='utf-8')
def update_status(status, payload):
    current={}
    if STATUS_PATH.exists():
        try: current=json.loads(STATUS_PATH.read_text(encoding='utf-8'))
        except Exception: current={}
    current['regulatory_ccam_articles']={'status':status,'generated':now_fr(),**payload}
    STATUS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
def paragraphs(text, limit=16):
    out=[]
    for block in re.split(r'\n+|(?<=[.!?])\s+(?=[A-ZÉÈÀÂÎÔÙÇ])', text or ''):
        b=re.sub(r'\s+',' ',block).strip(' -•\t')
        if 70 <= len(b) <= 900 and not ANTIBOT_RE.search(b): out.append(b)
        if len(out)>=limit: break
    return out
def build_article(item, text, codes, score):
    parts=paragraphs(text)
    if not parts:
        parts=[item['summary'], 'Ce dossier est volontairement limité aux changements utiles pour le paramétrage CCAM : codes, tarifs, conventions, remboursement, paniers 100 % Santé et règles de facturation.']
    body=''.join([
        f'<p><strong>Source officielle suivie :</strong> <a href="{esc(item["source_url"])}" target="_blank" rel="noopener noreferrer">{esc(item["source"])}</a>.</p>',
        '<h2>Pourquoi ce dossier est pertinent pour le site</h2>',
        '<p>Ce contenu est retenu parce qu’il concerne prioritairement les codes CCAM, les mises à jour de nomenclature, les tarifs, les conventions, la facturation ou la prise en charge. Les actualités médicales générales sont exclues.</p>',
        '<h2>Points à surveiller</h2><ul>',
        ''.join(f'<li>{esc(p)}</li>' for p in parts[:10]),
        '</ul>',
        '<h2>Codes CCAM détectés</h2>',
        f'<p>{esc(", ".join(codes[:80])) if codes else "Aucun code CCAM explicite détecté dans le texte source ; surveillance par thème réglementaire."}</p>',
        '<h2>Traçabilité</h2>',
        f'<p>Score de pertinence CCAM/convention : {score}. Généré le {esc(now_fr())}. Source : <a href="{esc(item["source_url"])}" target="_blank" rel="noopener noreferrer">{esc(item["source_url"])}</a>.</p>'
    ])
    return {
        'id': item['id'], 'title': item['title'], 'date': item.get('date') or dt.date.today().isoformat(),
        'source': item['source'], 'source_url': item['source_url'], 'category': item['category'], 'tag': item['category'],
        'summary': item['summary'], 'content_html': body, 'codes': codes[:80], 'codes_detectes': codes[:160],
        'confidence': 'Haute' if score>=5 else 'Moyenne',
        'generation': {'mode':'regulatory-ccam-official-sources-only','generated':now_fr(),'score':score,'minimum_date':MIN_DATE.isoformat()}
    }
def collect_from_source(src):
    out=[]
    try:
        raw=fetch(src['url'])
        text, links=text_and_links(raw, src['url'])
        if ANTIBOT_RE.search(text): raise ValueError('contenu antibot rejeté')
        ok, score=relevant(text)
        codes=sorted(set(CODE_RE.findall(text)))
        if ok and len(text)>=MIN_TEXT_CHARS:
            title=src['name'].replace('Ameli - ','').replace('ATIH - ','').replace('Légifrance - ','')
            out.append({'id':slugify(title),'title':title,'summary':f'Dossier issu de {src["name"]}, ciblé sur les changements CCAM/conventions/tarifs.','source':src['name'],'source_url':src['url'],'category':src['category'],'text':text[:MAX_TEXT_CHARS],'codes':codes,'score':score,'priority':src['priority']})
        # relevant linked pages, limited
        for label,url in links[:45]:
            low=(label+' '+url).lower()
            if not any(k in low for k in KEYWORDS): continue
            try:
                detail_raw=fetch(url, timeout=25); detail_text,_=text_and_links(detail_raw, url)
                if ANTIBOT_RE.search(detail_text): continue
                ok2, score2=relevant(label+' '+detail_text)
                if not ok2 or len(detail_text)<MIN_TEXT_CHARS: continue
                d=date_from_text(detail_text) or date_from_text(label)
                if d and d<MIN_DATE: continue
                out.append({'id':slugify(label),'title':clean(label)[:180],'summary':f'Dossier réglementaire CCAM détecté depuis {src["name"]}.','source':src['name'],'source_url':url,'category':src['category'],'text':detail_text[:MAX_TEXT_CHARS],'codes':sorted(set(CODE_RE.findall(detail_text))),'score':score2+1,'priority':src['priority'],'date': d.isoformat() if d else dt.date.today().isoformat()})
                time.sleep(.2)
            except Exception:
                continue
    except Exception as exc:
        return [], {'source':src['name'],'error':f'{type(exc).__name__}: {exc}'}
    return out, None
def fallback_items(app):
    records=app.get('records', []) if isinstance(app.get('records'), list) else []
    dental=[r.get('code') for r in records if isinstance(r,dict) and r.get('domaine')!='Médical CCAM' and r.get('code')]
    rac=[r.get('code') for r in records if isinstance(r,dict) and str(r.get('panier_100_sante','')).startswith(('RAC 0','RAC modéré')) and r.get('code')]
    items=[]
    for topic in FALLBACK_ARTICLE_TOPICS:
        codes=(rac if '100' in topic['title'] or 'Tarifs' in topic['title'] else dental)[:90]
        text=' '.join([
            topic['summary'],
            'Suivre les codes ajoutés, supprimés ou modifiés, les bases de remboursement, les honoraires limites, les avenants conventionnels et les règles de prise en charge.',
            'Vérifier l’impact sur le paramétrage métier, les paniers 100 % Santé, les actes dentaires, les actes prothétiques, les devis et la facturation.',
        ])
        items.append({**topic,'text':text,'codes':codes,'score':4,'priority':50,'date':dt.date.today().isoformat()})
    return items
def main():
    app=load_app(); collected=[]; errors=[]
    for src in OFFICIAL_INDEX_SOURCES:
        items, err=collect_from_source(src)
        collected.extend(items)
        if err: errors.append(err)
        time.sleep(.25)
    seen=set(); uniq=[]
    for item in sorted(collected, key=lambda x:(-x.get('score',0), x.get('priority',99), x.get('title',''))):
        key=item['source_url']
        if key in seen: continue
        seen.add(key); uniq.append(item)
        if len(uniq)>=MAX_ARTICLES: break
    if len(uniq)<3:
        uniq.extend(fallback_items(app))
    articles=[build_article(item, item.get('text',''), item.get('codes',[]), int(item.get('score',0))) for item in uniq[:MAX_ARTICLES]]
    articles.sort(key=lambda a:(a.get('date','0000-00-00'), a.get('confidence','')), reverse=True)
    app['articles']=articles
    app.setdefault('meta',{})['articles']=len(articles)
    app['meta']['article_generation']={'mode':'regulatory-ccam-official-sources-only','generated':now_fr(),'sources':[s['name'] for s in OFFICIAL_INDEX_SOURCES],'minimum_date':MIN_DATE.isoformat(),'articles_generated':len(articles),'errors':errors[:12],'description':'Dossiers ciblés CCAM, mises à jour de codes, tarifs, conventions, remboursement, dentaire et 100 % Santé uniquement.'}
    # link records
    link_map={}
    for a in articles:
        for c in a.get('codes',[]): link_map.setdefault(c,[]).append(a['id'])
    for r in app.get('records',[]):
        if isinstance(r,dict) and r.get('code') in link_map: r['articles_lies']=link_map[r['code']][:8]
    save_app(app)
    update_status('ok' if articles else 'empty', {'count':len(articles),'errors':errors[:12], 'message':'Articles recentrés sur CCAM/conventions/tarifs depuis sources officielles.'})
    print(f'Articles réglementaires CCAM générés : {len(articles)} ; erreurs sources : {len(errors)}')
if __name__=='__main__': main()
