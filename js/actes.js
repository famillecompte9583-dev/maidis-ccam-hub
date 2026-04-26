let data = appRecords();
let view = [];
let page = 1;
const per = 50;
const els = { q: null, domain: null, panier: null, rate: null, sort: null, tbody: null, count: null, pageinfo: null };

function init() {
  ['q', 'domain', 'panier', 'rate', 'sort', 'tbody', 'count', 'pageinfo'].forEach(key => {
    els[key] = document.getElementById(key);
  });

  if (!data.length) {
    if (els.tbody) els.tbody.innerHTML = '<tr><td colspan="6" class="small">Base indisponible : relancez la synchronisation ou vérifiez data/app-data.js.</td></tr>';
    if (els.count) els.count.textContent = '0 acte affiché';
    return;
  }

  ['q', 'domain', 'panier', 'rate', 'sort'].forEach(key => {
    if (els[key]) els[key].addEventListener(key === 'q' ? 'input' : 'change', () => { page = 1; render(); });
  });
  const prev = document.getElementById('prev');
  const next = document.getElementById('next');
  const exportBtn = document.getElementById('exportCsv');
  if (prev) prev.onclick = () => { page--; render(); };
  if (next) next.onclick = () => { page++; render(); };
  if (exportBtn) exportBtn.onclick = exportCsv;
  render();
}

function rateOf(record) {
  const selected = els.rate?.value || 'medical70_dental60';
  if (selected === 'medical70_dental60') return Number(record.taux_amo_standard || 0);
  if (selected === 'all70') return 70;
  if (selected === 'all60') return 60;
  return Number(record.taux_amo_standard || 0);
}

function searchable(record) {
  return [record.code, record.libelle, record.panier_100_sante, record.domaine, record.justification_panier]
    .map(value => String(value || '').toLowerCase())
    .join(' ');
}

function render() {
  const q = String(els.q?.value || '').trim().toLowerCase();
  view = data.filter(record => {
    if (q && !searchable(record).includes(q)) return false;
    if (els.domain?.value !== 'all' && record.domaine !== els.domain.value) return false;
    const panier = String(record.panier_100_sante || '').toLowerCase();
    if (els.panier?.value !== 'all' && !panier.includes(els.panier.value)) return false;
    return true;
  });

  const sort = els.sort?.value || 'code';
  view.sort((a, b) => {
    if (sort === 'tarif_desc') return (Number(b.brss) || 0) - (Number(a.brss) || 0);
    if (sort === 'tarif_asc') return (Number(a.brss) || 0) - (Number(b.brss) || 0);
    return String(a.code || '').localeCompare(String(b.code || ''));
  });

  const pages = Math.max(1, Math.ceil(view.length / per));
  if (page > pages) page = pages;
  if (page < 1) page = 1;
  const rows = view.slice((page - 1) * per, page * per);

  if (els.count) els.count.textContent = `${fmtInt(view.length)} acte(s) affiché(s)`;
  if (els.pageinfo) els.pageinfo.textContent = `Page ${page} / ${pages}`;
  const prev = document.getElementById('prev');
  const next = document.getElementById('next');
  if (prev) prev.disabled = page <= 1;
  if (next) next.disabled = page >= pages;

  els.tbody.innerHTML = rows.map(record => {
    const taux = rateOf(record);
    const amo = (Number(record.brss) || 0) * taux / 100;
    const url = `acte.html?code=${encodeURIComponent(record.code || '')}&a=${encodeURIComponent(record.activite || '')}&p=${encodeURIComponent(record.phase || '')}`;
    return `<tr>
      <td><a class="code" href="${url}">${escHTML(record.code)}</a><div class="small">A${escHTML(record.activite)} · P${escHTML(record.phase)}</div></td>
      <td>${escHTML(record.libelle)}<div class="small">${escHTML(record.justification_panier)}</div></td>
      <td class="money">${fmtEuro(record.brss)}</td>
      <td>${fmtPercent(taux)}</td>
      <td class="money">${fmtEuro(amo)}</td>
      <td><span class="pill ${clsPanier(record.panier_100_sante)}">${escHTML(record.panier_100_sante)}</span><br><span class="pill ${record.domaine === 'Médical CCAM' ? 'p-med' : 'p-dent'}" style="margin-top:6px">${escHTML(record.domaine)}</span></td>
    </tr>`;
  }).join('') || '<tr><td colspan="6" class="small">Aucun résultat.</td></tr>';
}

function exportCsv() {
  const head = ['code', 'activite', 'phase', 'libelle', 'brss', 'taux_amo', 'montant_amo', 'panier_100_sante', 'domaine', 'accord_prealable', 'code_maidis_suggere', 'notes_parametrage'];
  const csv = [head.join(';')].concat(view.map(record => {
    const taux = rateOf(record);
    const amo = (Number(record.brss) || 0) * taux / 100;
    const row = [record.code, record.activite, record.phase, record.libelle, record.brss, taux, amo.toFixed(2), record.panier_100_sante, record.domaine, record.accord_prealable, record.code_maidis_suggere, record.notes_parametrage];
    return row.map(csvCell).join(';');
  })).join('\n');
  downloadText('export_maidis_ccam.csv', csv);
}

document.addEventListener('DOMContentLoaded', init);
