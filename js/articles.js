document.addEventListener('DOMContentLoaded', () => {
  const app = appData();
  const rawArticles = Array.isArray(app.articles) ? app.articles : [];
  const articles = rawArticles
    .filter(article => article && article.category !== 'Sources & API' && article.tag !== 'Sources & API')
    .sort((a, b) => {
      const da = Date.parse(a.date || '1900-01-01') || 0;
      const db = Date.parse(b.date || '1900-01-01') || 0;
      return db - da;
    });
  const list = document.getElementById('articles');
  const body = document.getElementById('articleBody');

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? 'date non renseignée' : date.toLocaleDateString('fr-FR');
  }

  if (list) {
    if (!articles.length) {
      list.innerHTML = '<div class="note">Aucun dossier récent n’a encore été extrait. Les contenus anciens et les fiches techniques API sont exclus de cette page ; les sources techniques sont disponibles dans Sources & API.</div>';
      return;
    }

    list.innerHTML = articles.map(article => {
      const id = encodeURIComponent(article.id || '');
      const tag = article.category || article.tag || 'Dossier';
      const count = Array.isArray(article.codes) ? article.codes.length : 0;
      const mode = article.generation?.mode || article.ai_review?.mode || 'source suivie';
      return `<article class="card newsitem">
        <span class="pill p-med">${escHTML(tag)}</span>
        <h3><a href="article.html?id=${id}">${escHTML(article.title)}</a></h3>
        <p>${escHTML(article.summary)}</p>
        <p class="small">${escHTML(article.source || 'Source')} · ${escHTML(formatDate(article.date))} · ${fmtInt(count)} code(s) explicitement détecté(s) · ${escHTML(mode)}</p>
      </article>`;
    }).join('');
  }

  if (body) {
    const id = new URLSearchParams(location.search).get('id');
    const article = articles.find(item => item.id === id) || articles[0];
    if (!article) {
      body.innerHTML = '<div class="note">Dossier introuvable. Aucun article récent n’est actuellement publié.</div>';
      return;
    }

    document.title = `${article.title || 'Dossier'} — Annuaire CCAM Santé`;
    const tag = document.getElementById('articleTag');
    const title = document.getElementById('articleTitle');
    const summary = document.getElementById('articleSummary');
    if (tag) tag.textContent = article.category || article.tag || 'Dossier';
    if (title) title.textContent = article.title || 'Dossier';
    if (summary) summary.textContent = article.summary || '';

    body.innerHTML = sanitizeArticleHTML(article.content_html || '<p>Aucun contenu disponible.</p>');

    const allCodes = Array.isArray(article.codes) ? article.codes : [];
    const visibleCodes = allCodes.slice(0, 30);
    const codesBox = document.getElementById('articleCodes');
    if (codesBox) {
      if (!visibleCodes.length) {
        codesBox.innerHTML = 'Aucun code CCAM explicitement détecté dans le texte source.';
      } else {
        const extra = allCodes.length > visibleCodes.length
          ? `<p class="small" style="margin-top:10px">${fmtInt(allCodes.length - visibleCodes.length)} autre(s) code(s) explicitement détecté(s), masqué(s) pour éviter une page illisible.</p>`
          : '';
        codesBox.innerHTML = visibleCodes.map(code => `<a class="pill p-out" style="margin:4px" href="acte.html?code=${encodeURIComponent(code)}">${escHTML(code)}</a>`).join('') + extra;
      }
    }
  }
});
