(function () {
    'use strict';

    const STORAGE_KEY = 'aegis-theme';

    function getPreferred() {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored === 'light' || stored === 'dark') return stored;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function syncIcons(theme) {
        document.querySelectorAll('[data-theme-toggle]').forEach(el => {
            const icon = el.querySelector('i');
            if (icon) icon.className = theme === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
            el.setAttribute('title', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
        });
    }

    function apply(theme, persist) {
        document.documentElement.setAttribute('data-bs-theme', theme);
        if (persist) localStorage.setItem(STORAGE_KEY, theme);
        syncIcons(theme);
    }

    window.AegisTheme = {
        toggle: function () {
            const current = document.documentElement.getAttribute('data-bs-theme') || 'light';
            apply(current === 'dark' ? 'light' : 'dark', true);
        },
        init: function () {
            apply(getPreferred(), false);
            document.querySelectorAll('[data-theme-toggle]').forEach(el => {
                el.addEventListener('click', function (e) {
                    e.preventDefault();
                    window.AegisTheme.toggle();
                });
            });
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', window.AegisTheme.init);
    } else {
        window.AegisTheme.init();
    }
})();