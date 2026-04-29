document.addEventListener('DOMContentLoaded', () => {
  const items = Array.isArray(appData().news) ? appData().news : [];
  const container = document.getElementById('news');
  if (!container) return;

  function parseDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function formatDate(value) {
    const date = parseDate(value);
    return date ? date.toLocaleDateString('fr-FR', { timeZone: 'Europe/Paris', dateStyle: 'medium' }) : 'date non reconnue';
  }

  function confidenceClass(value) {
    const raw = String(value || '').toLowerCase();
    if (raw.includes('haute')) return 'p-rac';
    if (raw.includes('moyenne')) return 'p-mod';
    return 'p-free';
  }

  if (!items.length) {
    container.innerHTML = `<div class="note">
      Aucune actualité réglementaire CCAM / Assurance maladie n’est actuellement embarquée.
      Le site garde volontairement la veille vide plutôt que de publier des articles médicaux trop généraux ou non datés.
    </div>`;
    return;
  }

  const sorted = [...items].sort((a, b) => String(b.publication_date || b.date || '').localeCompare(String(a.publication_date || a.date || '')));
  container.innerHTML = sorted.map(item => {
    const tag = item.regulatory_scope || item.tag || item.source || 'Veille réglementaire';
    const summary = item.summary ? `<p>${escHTML(item.summary)}</p>` : '';
    const href = safeExternalUrl(item.url);
    const dateValue = item.publication_date || item.date;
    const dateSource = item.publication_date_source || 'source non précisée';
    const confidence = item.publication_date_confidence || 'Basse';
    const score = Number(item.regulatory_relevance_score || 0);
    return `<article class="card newsitem live-card">
      <div class="newsmeta">
        <span class="pill p-med">${escHTML(tag)}</span>
        <span class="pill ${confidenceClass(confidence)}">Date ${escHTML(confidence)}</span>
      </div>
      <h3><a href="${escAttr(href)}" target="_blank" rel="noopener noreferrer">${escHTML(item.title)}</a></h3>
      <p class="small">${escHTML(item.source || 'Source officielle')} · publication : <strong>${escHTML(formatDate(dateValue))}</strong> · reconnue via ${escHTML(dateSource)}</p>
      ${summary}
      <p class="small">${escHTML(item.actionability || 'À vérifier')} · pertinence réglementaire : ${escHTML(score.toLocaleString('fr-FR'))}/16</p>
    </article>`;
  }).join('');
});
