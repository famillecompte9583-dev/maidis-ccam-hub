document.addEventListener('DOMContentLoaded', () => {
  const items = Array.isArray(appData().news) ? appData().news : [];
  const container = document.getElementById('news');
  if (!container) return;

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'date non renseignée' : date.toLocaleDateString('fr-FR');
  }

  if (!items.length) {
    container.innerHTML = '<div class="note">Aucune actualité embarquée. Lancez le workflow de veille pour reconstruire cette page.</div>';
    return;
  }

  container.innerHTML = items.map(item => {
    const tag = item.tag || item.source || 'Veille';
    const summary = item.summary ? `<p>${escHTML(item.summary)}</p>` : '';
    const href = safeExternalUrl(item.url);
    return `<article class="card newsitem">
      <span class="pill p-med">${escHTML(tag)}</span>
      <h3><a href="${escAttr(href)}" target="_blank" rel="noopener noreferrer">${escHTML(item.title)}</a></h3>
      <p class="small">${escHTML(item.source || 'Source')} · ${escHTML(formatDate(item.date))}</p>
      ${summary}
    </article>`;
  }).join('');
});
