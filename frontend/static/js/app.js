/* The two bits of behaviour every page shares. Both were inline <script> blocks
   copied into the templates that needed them — the theme toggle in _nav.html and
   again in learn.html, copySql in index.html, dataset.html and connect_table.html
   — so a fix had to be made in up to three places to take effect everywhere. */

(function () {
    var STORED = 'theme';

    /* Runs before the body paints, so a light-theme reader doesn't see a dark flash. */
    if (localStorage.getItem(STORED) === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }

    function isLight() {
        return document.documentElement.getAttribute('data-theme') === 'light';
    }

    function paintIcon() {
        var icon = document.getElementById('theme-toggle-icon');
        if (icon) icon.innerHTML = isLight() ? '&#9789;' : '&#9788;';
    }

    window.toggleTheme = function () {
        var root = document.documentElement;
        if (isLight()) {
            root.removeAttribute('data-theme');
            localStorage.setItem(STORED, 'dark');
        } else {
            root.setAttribute('data-theme', 'light');
            localStorage.setItem(STORED, 'light');
        }
        paintIcon();
    };

    window.copySql = function (btn) {
        var code = document.querySelector('.sql-box code');
        if (!code) return;
        navigator.clipboard.writeText(code.innerText).then(function () {
            var original = btn.textContent;
            btn.textContent = 'Copied';
            btn.classList.add('is-done');
            setTimeout(function () {
                btn.textContent = original;
                btn.classList.remove('is-done');
            }, 1500);
        });
    };

    document.addEventListener('DOMContentLoaded', paintIcon);
})();
