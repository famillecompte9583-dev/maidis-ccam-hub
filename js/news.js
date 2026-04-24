document.addEventListener('DOMContentLoaded', () => {
    const items = window.CCAM_APP_DATA.news || [];
    const container = document.getElementById('news');
    if (!items.length) {
        container.innerHTML = '<div class="note">Aucune actualité embarquée. Lancez le workflow de veille pour reconstruire cette page.</div>';
        return;
    }
    container.innerHTML = items.map(item => {
        const date = new Date(item.date).toLocaleDateString('fr-FR');
        const tag = item.tag || item.source;
        // Si un résumé est disponible, on l’affiche dans un paragraphe.
        const summary = item.summary ? `<p>${item.summary}</p>` : '';
        return `<article class="card newsitem">
            <span class="pill p-med">${tag}</span>
            <h3><a href="${item.url}" target="_blank" rel="noopener">${item.title}</a></h3>
            <p class="small">${item.source} · ${date}</p>
            ${summary}
        </article>`;
    }).join('');
});
