// Fonctions communes publiques : sécurité d'affichage, navigation, exports et formats.
(function () {
  try {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = 'custom.css';
    document.head.appendChild(link);
  } catch (e) {
    // Optionnel : le site doit rester fonctionnel sans custom.css.
  }
})();

function escHTML(value) {
  return String(value ?? '').replace(/[&<>"']/g, match => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  }[match]));
}

function escAttr(value) {
  return escHTML(value).replace(/`/g, '&#096;');
}

function safeExternalUrl(value) {
  try {
    const url = new URL(String(value || ''), window.location.href);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '#';
  } catch (error) {
    return '#';
  }
}

function fmtEuro(value) {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
}

function fmtInt(value) {
  return Number(value || 0).toLocaleString('fr-FR');
}

function fmtPercent(value) {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toLocaleString('fr-FR')} %`;
}

function clsPanier(value) {
  const p = String(value || '').toLowerCase();
  if (p.startsWith('rac 0')) return 'p-rac';
  if (p.startsWith('rac mod')) return 'p-mod';
  if (p.includes('libre') || p.includes('vérifier') || p.includes('verifier')) return 'p-free';
  return 'p-out';
}

function qs(key) {
  return new URLSearchParams(location.search).get(key);
}

function appData() {
  return window.CCAM_APP_DATA && typeof window.CCAM_APP_DATA === 'object' ? window.CCAM_APP_DATA : {};
}

function appRecords() {
  const records = appData().records;
  return Array.isArray(records) ? records : [];
}

function setActive() {
  const page = document.body.dataset.page;
  document.querySelectorAll('.links a').forEach(link => {
    if (link.dataset.page === page) link.classList.add('active');
  });
  const btn = document.querySelector('.menu');
  const links = document.querySelector('.links');
  if (btn && links) btn.onclick = () => links.classList.toggle('open');
}

document.addEventListener('DOMContentLoaded', setActive);

function csvCell(value) {
  return `"${String(value ?? '').replaceAll('"', '""')}"`;
}

function downloadText(filename, text, type = 'text/csv;charset=utf-8') {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 500);
}
