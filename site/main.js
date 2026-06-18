/* Секретарь24 — лендинг. Интерактив без зависимостей. */
(function () {
  'use strict';

  var header = document.getElementById('header');
  var burger = document.getElementById('burger');

  /* --- Переключатель языков: запоминаем выбор пользователя, чтобы авто-редирект
         с корня по browser-language больше не срабатывал --- */
  document.querySelectorAll('.lang-switcher a').forEach(function (a) {
    a.addEventListener('click', function () {
      try { localStorage.setItem('s24_lang', a.getAttribute('hreflang') || ''); } catch (e) {}
    });
  });

  /* --- Шапка: фон при скролле --- */
  function onScroll() {
    header.classList.toggle('scrolled', window.scrollY > 8);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* --- Мобильное меню --- */
  var nav = document.getElementById('nav');

  function syncMobileNavHeight() {
    /* CSS использует --mobile-nav-h для позиционирования actions под пунктами nav,
       чтобы не зависеть от magic numbers и количества ссылок. */
    if (!nav) return;
    var h = nav.getBoundingClientRect().height || 0;
    if (h > 0) header.style.setProperty('--mobile-nav-h', h + 'px');
  }

  burger.addEventListener('click', function () {
    var open = header.classList.toggle('nav-open');
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      /* Меряем после применения класса, чтобы nav уже был развёрнут. */
      requestAnimationFrame(syncMobileNavHeight);
    }
  });
  window.addEventListener('resize', function () {
    if (header.classList.contains('nav-open')) syncMobileNavHeight();
  });
  document.querySelectorAll('#nav a, .header__actions a, .lang-switcher a').forEach(function (link) {
    link.addEventListener('click', function () {
      header.classList.remove('nav-open');
      burger.setAttribute('aria-expanded', 'false');
    });
  });

  /* --- Переключатель тарифов: помесячно / за год --- */
  var billingSwitch = document.getElementById('billingSwitch');
  var lblMonthly = document.getElementById('lblMonthly');
  var lblYearly = document.getElementById('lblYearly');

  function applyBilling(yearly) {
    var mode = yearly ? 'yearly' : 'monthly';
    document.querySelectorAll('[data-monthly]').forEach(function (el) {
      var val = el.getAttribute('data-' + mode);
      if (val !== null) el.textContent = val;
    });
    billingSwitch.setAttribute('aria-checked', yearly ? 'true' : 'false');
    lblMonthly.classList.toggle('is-active', !yearly);
    lblYearly.classList.toggle('is-active', yearly);
  }
  billingSwitch.addEventListener('click', function () {
    applyBilling(billingSwitch.getAttribute('aria-checked') !== 'true');
  });

  /* --- Лид-форма: уходит на backend (/widget/lead) → уведомление в Telegram владельца --- */
  var form = document.getElementById('leadForm');
  var success = document.getElementById('leadSuccess');

  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var name = form.name.value.trim();
      var contact = form.contact.value.trim();
      if (!name || !contact) {
        if (!name) form.name.focus();
        else form.contact.focus();
        return;
      }

      var honeypot = form.company ? form.company.value.trim() : '';
      var roleEl = form.role;
      var btn = form.querySelector('button[type="submit"]');

      var payload = {
        name: name,
        contact: contact,
        role: roleEl ? roleEl.value : '',
        company: honeypot, /* honeypot — должно остаться пустым у людей */
        locale: (document.documentElement.lang || '').toLowerCase(),
        page: location.href
      };

      if (btn) { btn.disabled = true; btn.dataset.label = btn.textContent; btn.textContent = 'Отправляем…'; }

      function showSuccess() {
        form.hidden = true;
        success.hidden = false;
        success.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      function restoreBtn() {
        if (btn) { btn.disabled = false; if (btn.dataset.label) btn.textContent = btn.dataset.label; }
      }

      fetch('/widget/lead', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(function (r) {
          if (r.ok) { showSuccess(); return; }
          throw new Error('bad status ' + r.status);
        })
        .catch(function () {
          /* Фолбэк: не теряем заявку — открываем Telegram владельца с заполненным текстом */
          restoreBtn();
          var msg =
            'Заявка с сайта%0AИмя: ' + encodeURIComponent(name) +
            '%0AКонтакт: ' + encodeURIComponent(contact) +
            (payload.role ? '%0AАссистент: ' + encodeURIComponent(payload.role) : '');
          window.open('https://t.me/ai_sekretar24bot?text=' + msg, '_blank', 'noopener');
          showSuccess();
        });
    });
  }
})();
