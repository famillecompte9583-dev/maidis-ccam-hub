// Gestion du mode clair / sombre.
// Le thème est appliqué via une classe CSS sur <body> et mémorisé en localStorage.
(function () {
  'use strict';

  const STORAGE_KEY = 'ccam-theme';

  function getPreferredTheme() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'light' || saved === 'dark') return saved;
    } catch (error) {
      // Accès localStorage indisponible : on continue sans persistance.
    }

    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
  }

  function currentTheme() {
    return document.body?.classList.contains('theme-dark') ? 'dark' : 'light';
  }

  function updateToggleLabels(theme) {
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      const nextTheme = theme === 'dark' ? 'clair' : 'sombre';
      button.setAttribute('aria-label', `Activer le mode ${nextTheme}`);
      button.setAttribute('title', `Activer le mode ${nextTheme}`);
    });

    document.querySelectorAll('[data-theme-toggle-icon]').forEach((icon) => {
      icon.textContent = theme === 'dark' ? '☀' : '☾';
    });
  }

  function applyTheme(theme, persist) {
    if (!document.body) return;

    const safeTheme = theme === 'dark' ? 'dark' : 'light';
    document.body.classList.toggle('theme-dark', safeTheme === 'dark');
    document.body.dataset.theme = safeTheme;
    updateToggleLabels(safeTheme);

    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, safeTheme);
      } catch (error) {
        // Persistance indisponible : le thème reste appliqué pour la session courante.
      }
    }
  }

  function initTheme() {
    applyTheme(getPreferredTheme(), false);
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-theme-toggle]');
    if (!button) return;
    applyTheme(currentTheme() === 'dark' ? 'light' : 'dark', true);
  });

  document.addEventListener('ccam:nav-ready', () => {
    updateToggleLabels(currentTheme());
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTheme);
  } else {
    initTheme();
  }
})();
