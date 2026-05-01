// Navbar centralisée du site Annuaire CCAM Santé.
// Ce fichier injecte la navigation sur toutes les pages statiques GitHub Pages.
(function () {
  'use strict';

  const LINKS = [
    { page: 'index', href: 'index.html', label: 'Accueil' },
    { page: 'actes', href: 'actes.html', label: 'Actes' },
    { page: 'dossiers', href: 'dossiers.html', label: 'Dossiers' },
    { page: 'sources', href: 'sources.html', label: 'Sources & API' },
    { page: 'changements', href: 'changements.html', label: 'Changements' },
    { page: 'guides', href: 'guides.html', label: 'Guides' },
    { page: 'exports', href: 'exports.html', label: 'Exports' },
    { page: 'actualites', href: 'actualites.html', label: 'Veille' }
  ];

  function renderNavbar() {
    const root = document.querySelector('[data-nav-root]');
    if (!root) return;

    const currentPage = document.body?.dataset.page || '';
    const nav = document.createElement('nav');
    nav.className = 'nav';
    nav.setAttribute('aria-label', 'Navigation principale');

    nav.innerHTML = `
      <div class="navin">
        <a class="brand" href="index.html">
          <span class="logo" aria-hidden="true">⚕</span>
          <span>Annuaire CCAM Santé</span>
        </a>

        <div class="nav-actions">
          <button
            class="theme-toggle"
            type="button"
            data-theme-toggle
            aria-label="Basculer le thème"
            title="Basculer le thème"
          >
            <span data-theme-toggle-icon aria-hidden="true">◐</span>
          </button>

          <button
            class="menu"
            type="button"
            aria-label="Ouvrir le menu de navigation"
            aria-expanded="false"
            aria-controls="site-links"
            data-nav-toggle
          >
            ☰
          </button>
        </div>

        <div class="links" id="site-links">
          ${LINKS.map((link) => {
            const isActive = currentPage === link.page;
            return `
              <a
                href="${link.href}"
                data-page="${link.page}"
                class="${isActive ? 'active' : ''}"
                ${isActive ? 'aria-current="page"' : ''}
              >
                ${link.label}
              </a>
            `;
          }).join('')}
        </div>
      </div>
    `;

    root.replaceWith(nav);

    const toggle = nav.querySelector('[data-nav-toggle]');
    const links = nav.querySelector('.links');

    if (toggle && links) {
      toggle.addEventListener('click', () => {
        const isOpen = links.classList.toggle('open');
        toggle.setAttribute('aria-expanded', String(isOpen));
        toggle.setAttribute(
          'aria-label',
          isOpen ? 'Fermer le menu de navigation' : 'Ouvrir le menu de navigation'
        );
      });

      nav.querySelectorAll('.links a').forEach((link) => {
        link.addEventListener('click', () => {
          links.classList.remove('open');
          toggle.setAttribute('aria-expanded', 'false');
          toggle.setAttribute('aria-label', 'Ouvrir le menu de navigation');
        });
      });

      window.addEventListener('resize', () => {
        if (window.innerWidth > 1000) {
          links.classList.remove('open');
          toggle.setAttribute('aria-expanded', 'false');
          toggle.setAttribute('aria-label', 'Ouvrir le menu de navigation');
        }
      });
    }

    document.dispatchEvent(new CustomEvent('ccam:nav-ready'));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', renderNavbar);
  } else {
    renderNavbar();
  }
})();
