/* Small delegated UI behaviours. Keeping these in a static file means the
   Content-Security-Policy can forbid inline event handlers entirely. */
(function () {
    'use strict';

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
})();
