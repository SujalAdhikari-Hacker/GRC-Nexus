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
        if (overlay.classList.contains('open')) {
            closePalette();
        } else {
            openPalette();
        }
    }

    document.addEventListener('keydown', function (e) {
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            togglePalette();
            return;
        }

        const overlay = document.getElementById('commandPalette');
        const isOpen = overlay && overlay.classList.contains('open');

        if (e.key === 'Escape') {
            if (isOpen) closePalette();
            return;
        }

        if (!isOpen) return;

        const items = Array.from(document.querySelectorAll('#commandPalette .palette-item'));
        if (!items.length) return;

        const current = document.activeElement;
        let idx = items.indexOf(current);

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            idx = idx === -1 ? 0 : (idx + 1) % items.length;
            items[idx].focus();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            idx = idx <= 0 ? items.length - 1 : idx - 1;
            items[idx].focus();
        } else if (e.key === 'Enter') {
            const target = items.indexOf(current) >= 0 ? current : items[0];
            if (target) {
                e.preventDefault();
                window.location.href = target.getAttribute('href');
            }
        }
    });

    document.addEventListener('click', function (e) {
        const overlay = document.getElementById('commandPalette');
        if (overlay && e.target === overlay) closePalette();
    });

    window.AegisPalette = { open: openPalette, close: closePalette, toggle: togglePalette };
})();