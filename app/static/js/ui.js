/* Small delegated UI behaviours & subtle progressive-enhancement motion.
   Keeping these in a static file means the Content-Security-Policy can
   forbid inline event handlers entirely. */
(function () {
    'use strict';

    var prefersReduced = window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    document.addEventListener('click', function (event) {
        var palette = event.target.closest('[data-palette-open]');
        if (palette) {
            event.preventDefault();
            if (window.GRCNexusPalette && window.GRCNexusPalette.open) {
                window.GRCNexusPalette.open();
            }
            return;
        }
        if (event.target.closest('[data-stop-propagation]')) {
            event.stopPropagation();
            return;
        }
        var matrixCell = event.target.closest('[data-matrix-href]');
        if (matrixCell) {
            window.location.assign(matrixCell.getAttribute('data-matrix-href'));
            return;
        }

        // Top route progress bar on internal navigation clicks.
        var link = event.target.closest('a[href]');
        if (link && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
            var href = link.getAttribute('href') || '';
            var target = link.getAttribute('target');
            if (
                href &&
                href.charAt(0) !== '#' &&
                href.indexOf('javascript:') !== 0 &&
                target !== '_blank' &&
                !link.hasAttribute('download') &&
                href.indexOf('export=') === -1 &&
                href.indexOf('format=') === -1
            ) {
                startProgress();
            }
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        var matrixCell = event.target.closest('[data-matrix-href]');
        if (matrixCell) {
            event.preventDefault();
            window.location.assign(matrixCell.getAttribute('data-matrix-href'));
        }
    });

    document.addEventListener('change', function (event) {
        if (event.target.matches('[data-auto-submit]') && event.target.form) {
            event.target.form.submit();
        }
    });

    function startProgress() {
        var bar = document.getElementById('grcNavProgress');
        if (!bar || prefersReduced) return;
        bar.classList.remove('done');
        bar.classList.add('active');
    }

    function finishProgress() {
        var bar = document.getElementById('grcNavProgress');
        if (!bar) return;
        bar.classList.remove('active');
        bar.classList.add('done');
        setTimeout(function () {
            bar.classList.remove('done');
        }, 280);
    }

    document.addEventListener('htmx:beforeRequest', startProgress);
    document.addEventListener('htmx:afterSettle', finishProgress);
    window.addEventListener('pageshow', finishProgress);

    function animateCountUps() {
        if (prefersReduced) return;
        var nodes = document.querySelectorAll('[data-count-up]');
        nodes.forEach(function (el) {
            var raw = el.getAttribute('data-count-up');
            var target = parseInt(raw, 10);
            if (isNaN(target) || target <= 0) return;
            var duration = 380;
            var start = null;
            el.textContent = '0';
            function step(ts) {
                if (!start) start = ts;
                var progress = Math.min((ts - start) / duration, 1);
                var eased = 1 - Math.pow(1 - progress, 3);
                el.textContent = String(Math.round(target * eased));
                if (progress < 1) {
                    window.requestAnimationFrame(step);
                } else {
                    el.textContent = String(target);
                }
            }
            window.requestAnimationFrame(step);
        });
    }

    function scrollActiveModuleTab() {
        var activeTab = document.querySelector('.module-tabs .module-tab.active');
        if (activeTab && typeof activeTab.scrollIntoView === 'function') {
            activeTab.scrollIntoView({ block: 'nearest', inline: 'center' });
        }
    }

    function init() {
        animateCountUps();
        scrollActiveModuleTab();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
