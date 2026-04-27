document.addEventListener('DOMContentLoaded', () => {
  const app = appData();
  const sources = Array.isArray(app.public_api_sources) ? app.public_api_sources : [];
  const root = document.getElementById('sourcesList');
  if (!root) return;

  if (!sources.length) {
    root.innerHTML = '<div class="note">Aucune source API n’a encore été intégrée. Lancez le workflow de synchronisation.</div>';
    return;
  }

  root.innerHTML = sources.map(source => {
    const title = source.title || 'Source API';
    const tag = source.category || source.source_kind || 'Source';
    const provider = source.provider || 'Fournisseur non renseigné';
    const summary = source.summary || source.use_case || 'Source technique suivie par le site.';
    const status = source.live_status ? ` · état : ${source.live_status}` : '';
    const url = safeExternalUrl(source.doc_url || source.url || source.api_url);
    return `<article class="card newsitem">
      <span class="pill p-med">${escHTML(tag)}</span>
      <h3><a href="${escAttr(url)}" target="_blank" rel="noopener noreferrer">${escHTML(title)}</a></h3>
      <p>${escHTML(summary)}</p>
      <p class="small">${escHTML(provider)}${escHTML(status)}</p>
    </article>`;
  }).join('');
});
