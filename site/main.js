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

  /* --- Лид-форма --- */
  var form = document.getElementById('leadForm');
  var success = document.getElementById('leadSuccess');

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var name = form.name.value.trim();
    var contact = form.contact.value.trim();
    if (!name || !contact) {
      if (!name) form.name.focus();
      else form.contact.focus();
      return;
    }

    /* TODO (Фаза 2): отправить заявку на backend.
       Пример: fetch('/admin/leads', { method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({ name: name, contact: contact, role: form.role.value }) })
       Лид уйдёт в amoCRM через существующее событие WidgetContactSubmitted. */

    form.hidden = true;
    success.hidden = false;
    success.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
})();
