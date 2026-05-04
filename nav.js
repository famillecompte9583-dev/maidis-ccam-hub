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

  function injectGlobalThemeOverrides() {
    if (document.getElementById('ccam-theme-global-overrides')) return;

    const style = document.createElement('style');
    style.id = 'ccam-theme-global-overrides';
    style.textContent = `
      :root {
        --page-grad-start: #f8fbff;
        --page-grad-end: #edf3fb;
        --nav-bg-override: rgba(255, 255, 255, .94);
        --nav-border-override: rgba(15, 23, 42, .08);
        --brand-text-override: #0f172a;
        --nav-link-override: #475467;
        --nav-link-hover-bg-override: rgba(79, 70, 229, .08);
        --nav-link-hover-text-override: #111827;
        --hero-bg-override:
          radial-gradient(circle at 10% 0%, rgba(6, 182, 212, .14), transparent 35%),
          radial-gradient(circle at 90% 10%, rgba(79, 70, 229, .18), transparent 42%),
          linear-gradient(135deg, #f8fbff, #edf3fb);
        --hero-text-override: #0f172a;
        --hero-sub-override: #475467;
        --eyebrow-bg-override: rgba(79, 70, 229, .08);
        --eyebrow-border-override: rgba(79, 70, 229, .16);
        --eyebrow-text-override: #3730a3;
        --glass-bg-override: rgba(255, 255, 255, .78);
        --glass-border-override: rgba(148, 163, 184, .22);
        --stat-bg-override: rgba(255, 255, 255, .72);
        --stat-border-override: rgba(148, 163, 184, .22);
        --stat-text-override: #475467;
        --footer-bg-override: #eaf0f8;
        --footer-text-override: #334155;
        --footer-link-override: #0f172a;
        --toggle-bg-override: var(--surface);
        --toggle-border-override: var(--border-main);
        --toggle-text-override: var(--text-main);
        --toggle-shadow-override: 0 10px 30px rgba(15, 23, 42, .18);
      }

      .theme-dark {
        --page-grad-start: #08101d;
        --page-grad-end: #0b1423;
        --nav-bg-override: rgba(8, 16, 29, .94);
        --nav-border-override: rgba(148, 163, 184, .14);
        --brand-text-override: #f8fbff;
        --nav-link-override: #cbd5e1;
        --nav-link-hover-bg-override: rgba(255, 255, 255, .12);
        --nav-link-hover-text-override: #ffffff;
        --hero-bg-override:
          radial-gradient(circle at 10% 0%, rgba(6, 182, 212, .22), transparent 35%),
          radial-gradient(circle at 90% 10%, rgba(79, 70, 229, .34), transparent 42%),
          linear-gradient(135deg, #06111f, #0d1f3a);
        --hero-text-override: #f8fbff;
        --hero-sub-override: #dbeafe;
        --eyebrow-bg-override: rgba(255, 255, 255, .10);
        --eyebrow-border-override: rgba(255, 255, 255, .16);
        --eyebrow-text-override: #dff7ff;
        --glass-bg-override: rgba(255, 255, 255, .10);
        --glass-border-override: rgba(255, 255, 255, .16);
        --stat-bg-override: rgba(255, 255, 255, .10);
        --stat-border-override: rgba(255, 255, 255, .12);
        --stat-text-override: #dbeafe;
        --footer-bg-override: #06111f;
        --footer-text-override: #cbd5e1;
        --footer-link-override: #ffffff;
        --toggle-bg-override: rgba(255, 255, 255, .08);
        --toggle-border-override: rgba(255, 255, 255, .14);
        --toggle-text-override: #ffffff;
        --toggle-shadow-override: 0 10px 30px rgba(2, 6, 23, .45);
      }

      body {
        background: linear-gradient(180deg, var(--page-grad-start), var(--page-grad-end)) !important;
        color: var(--text-main) !important;
        min-height: 100vh;
      }

      .nav {
        background: var(--nav-bg-override) !important;
        border-bottom: 1px solid var(--nav-border-override) !important;
      }

      .brand,
      .menu {
        color: var(--brand-text-override) !important;
      }

      .links a {
        color: var(--nav-link-override) !important;
      }

      .links a.active,
      .links a:hover {
        background: var(--nav-link-hover-bg-override) !important;
        color: var(--nav-link-hover-text-override) !important;
      }

      .hero {
        background: var(--hero-bg-override) !important;
        color: var(--hero-text-override) !important;
      }

      .hero p {
        color: var(--hero-sub-override) !important;
      }

      .eyebrow {
        background: var(--eyebrow-bg-override) !important;
        border-color: var(--eyebrow-border-override) !important;
        color: var(--eyebrow-text-override) !important;
      }

      .glass {
        background: var(--glass-bg-override) !important;
        border-color: var(--glass-border-override) !important;
      }

      .stat {
        background: var(--stat-bg-override) !important;
        border-color: var(--stat-border-override) !important;
      }

      .stat span {
        color: var(--stat-text-override) !important;
      }

      .footer {
        background: var(--footer-bg-override) !important;
        color: var(--footer-text-override) !important;
      }

      .footer a {
        color: var(--footer-link-override) !important;
      }

      .theme-toggle {
        position: fixed !important;
        top: 16px;
        right: 16px;
        z-index: 220;
        width: 46px;
        height: 46px;
        border-radius: 14px;
        background: var(--toggle-bg-override) !important;
        color: var(--toggle-text-override) !important;
        border: 1px solid var(--toggle-border-override) !important;
        box-shadow: var(--toggle-shadow-override);
      }

      .nav-actions {
        padding-right: 58px;
      }

      @media (max-width: 1000px) {
        .links {
          background: var(--surface) !important;
          border: 1px solid var(--border-main) !important;
        }
      }

      @media (max-width: 620px) {
        .theme-toggle {
          top: 12px;
          right: 12px;
        }

        .nav-actions {
          padding-right: 54px;
        }
      }
    `;

    document.head.appendChild(style);
  }

  function renderNavbar() {
    const root = document.querySelector('[data-nav-root]');
    if (!root) return;

    injectGlobalThemeOverrides();

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
