(function () {
    'use strict';

    function openPalette() {
        const overlay = document.getElementById('commandPalette');
        if (!overlay) return;
        overlay.classList.add('open');
        const input = overlay.querySelector('.palette-input');
        if (input) {
            input.value = '';
            input.focus();
            // Trigger initial HTMX load
            if (window.htmx) {
                window.htmx.trigger(input, 'input');
            }
        }
        document.body.style.overflow = 'hidden';
    }

    function closePalette() {
        const overlay = document.getElementById('commandPalette');
        if (!overlay) return;
        overlay.classList.remove('open');
        document.body.style.overflow = '';
    }

    function togglePalette() {
        const overlay = document.getElementById('commandPalette');
        if (!overlay) return;
        overlay.classList.contains('open') ? closePalette() : openPalette();
    }

    // Keyboard shortcuts
    document.addEventListener('keydown', function (e) {
        // Ctrl+K or Cmd+K
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            togglePalette();
            return;
        }
        // Escape closes
        if (e.key === 'Escape') {
            closePalette();
            return;
        }
        // Enter on a palette item — navigate
        if (document.getElementById('commandPalette')?.classList.contains('open')) {
            if (e.key === 'Enter') {
                const first = document.querySelector('#commandPalette .palette-item');
                if (first && document.activeElement?.classList.contains('palette-input')) {
                    e.preventDefault();
                    window.location.href = first.getAttribute('href');
                }
            }
        }
    });

    // Click on overlay background closes
    document.addEventListener('click', function (e) {
        const overlay = document.getElementById('commandPalette');
        if (overlay && e.target === overlay) closePalette();
    });

    // Expose for topbar search input
    window.AegisPalette = { open: openPalette, close: closePalette, toggle: togglePalette };
})();