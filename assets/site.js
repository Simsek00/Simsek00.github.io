/* Meok Apps — shared behaviour.
   The language and theme choices are already applied by the inline snippet in
   each page's <head>, before first paint; this file only wires the controls,
   the per-page metadata and the scroll reveal. */
(function () {
    'use strict';

    var LANG_KEY = 'meok-lang';
    var THEME_KEY = 'meok-theme';
    var root = document.documentElement;

    function store(key, value) {
        try {
            localStorage.setItem(key, value);
        } catch (e) {
            /* private mode: the choice simply does not outlive the page */
        }
    }

    /* --- language -------------------------------------------------------
       `window.PAGE_META` is set by each page: the title and description in
       both languages, so switching language also switches what a share
       preview or a bookmark records. */

    var meta = window.PAGE_META || {};
    var description = document.querySelector('meta[name="description"]');
    var ogTitle = document.querySelector('meta[property="og:title"]');
    var ogDesc = document.querySelector('meta[property="og:description"]');

    function setLang(lang, remember) {
        if (lang !== 'tr') lang = 'en';
        root.setAttribute('data-lang', lang);
        root.setAttribute('lang', lang);

        var m = meta[lang];
        if (m) {
            if (m.title) document.title = m.title;
            if (m.desc && description) description.setAttribute('content', m.desc);
            if (m.title && ogTitle) ogTitle.setAttribute('content', m.title);
            if (m.desc && ogDesc) ogDesc.setAttribute('content', m.desc);
        }

        var buttons = document.querySelectorAll('[data-set-lang]');
        for (var i = 0; i < buttons.length; i++) {
            buttons[i].setAttribute(
                'aria-pressed',
                buttons[i].getAttribute('data-set-lang') === lang ? 'true' : 'false'
            );
        }

        if (remember) store(LANG_KEY, lang);
    }

    document.addEventListener('click', function (event) {
        var target = event.target.closest('[data-set-lang]');
        if (target) setLang(target.getAttribute('data-set-lang'), true);
    });

    setLang(root.getAttribute('data-lang') || 'en', false);

    /* --- theme ----------------------------------------------------------
       Three states: no attribute means "follow the system". The first click
       moves to whatever the system is *not*, so the button always visibly
       does something. */

    function systemIsDark() {
        return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    var toggle = document.querySelector('[data-toggle-theme]');
    if (toggle) {
        toggle.addEventListener('click', function () {
            var current = root.getAttribute('data-theme');
            var isDark = current ? current === 'dark' : systemIsDark();
            var next = isDark ? 'light' : 'dark';
            root.setAttribute('data-theme', next);
            store(THEME_KEY, next);
            toggle.setAttribute('aria-label', next === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
        });
    }

    /* --- header shadow on scroll ---------------------------------------- */

    var header = document.querySelector('.site-header');
    if (header) {
        var onScroll = function () {
            header.setAttribute('data-stuck', window.scrollY > 8 ? 'true' : 'false');
        };
        onScroll();
        window.addEventListener('scroll', onScroll, { passive: true });
    }

    /* --- scroll reveal --------------------------------------------------- */

    var revealables = document.querySelectorAll('.reveal');
    var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (!revealables.length) {
        /* nothing to do */
    } else if (reduced || !('IntersectionObserver' in window)) {
        for (var j = 0; j < revealables.length; j++) revealables[j].classList.add('in');
    } else {
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                entry.target.classList.add('in');
                observer.unobserve(entry.target);
            });
        }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });

        for (var k = 0; k < revealables.length; k++) observer.observe(revealables[k]);
    }

    /* --- year ------------------------------------------------------------ */

    var years = document.querySelectorAll('[data-year]');
    for (var n = 0; n < years.length; n++) {
        years[n].textContent = String(new Date().getFullYear());
    }
})();
