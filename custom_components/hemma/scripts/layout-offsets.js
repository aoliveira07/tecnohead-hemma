// layout-offsets.js
(function () {
  if (window._hemmaLayoutOffsets) return;
  window._hemmaLayoutOffsets = true;

  var html = document.documentElement;

  function walkFind(root, selector, out, depth) {
    if (!root || depth > 20) return;
    if (root.querySelectorAll) {
      root.querySelectorAll(selector).forEach(function (el) { out.push(el); });
      root.querySelectorAll('*').forEach(function (el) {
        if (el.shadowRoot) walkFind(el.shadowRoot, selector, out, depth + 1);
      });
    }
  }

  function isVisible(el) {
    var r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    var cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  }

  // ── Sidebar width ─────────────────────────────────────────────────────────
  var lastSidebarW = -1;
  var sidebarDebounce = null;
  var sidebarObserversReady = false;

  function findSidebar() {
    try {
      var ha = document.querySelector('home-assistant');
      if (!ha || !ha.shadowRoot) return null;
      var ham = ha.shadowRoot.querySelector('home-assistant-main');
      if (!ham || !ham.shadowRoot) return null;
      var sb = ham.shadowRoot.querySelector('ha-sidebar');
      if (sb) return sb;
      var dr = ham.shadowRoot.querySelector('ha-drawer');
      if (!dr) return null;
      return dr.shadowRoot ? dr.shadowRoot.querySelector('ha-sidebar') : dr.querySelector('ha-sidebar');
    } catch (e) {
      return null;
    }
  }

  function setSidebarWidth(w) {
    if (w !== lastSidebarW) {
      lastSidebarW = w;
      html.style.setProperty('--hemma-sidebar-w', w + 'px');
    }
  }

  var lastContentL = -1;
  function findPanel() {
    try {
      var ham = document.querySelector('home-assistant').shadowRoot.querySelector('home-assistant-main');
      return ham.shadowRoot.querySelector('partial-panel-resolver, ha-drawer partial-panel-resolver');
    } catch (e) {
      return null;
    }
  }

  function applyContentLeft() {
    var p = findPanel();
    var l = p ? Math.max(0, Math.round(p.getBoundingClientRect().left)) : 0;
    if (l === lastContentL) return;
    lastContentL = l;
    html.style.setProperty('--hemma-content-left', l + 'px');
    window.dispatchEvent(new Event('hemma-content-left'));
  }

  function applySidebar() {
    applyContentLeft();
    var sb = findSidebar();
    if (!sb) return false;

    var r = sb.getBoundingClientRect();
    var w = (r.width > 0 && r.right > 0) ? Math.round(r.width) : 0;

    if (w > 0) {
      if (sidebarDebounce) { clearTimeout(sidebarDebounce); sidebarDebounce = null; }
      setSidebarWidth(w);
    } else if (!sidebarDebounce) {
      sidebarDebounce = setTimeout(function () {
        sidebarDebounce = null;
        var sb2 = findSidebar();
        if (sb2) {
          var r2 = sb2.getBoundingClientRect();
          setSidebarWidth((r2.width > 0 && r2.right > 0) ? Math.round(r2.width) : 0);
        }
      }, 300);
    }
    return true;
  }

  function setupSidebarObservers() {
    if (sidebarObserversReady) return;
    var sb = findSidebar();
    if (!sb) return;
    sidebarObserversReady = true;

    try { new ResizeObserver(applySidebar).observe(sb); } catch (e) {}
    try { var pn = findPanel(); if (pn) new ResizeObserver(applyContentLeft).observe(pn); } catch (e) {}
    try {
      var mo = new MutationObserver(applySidebar);
      mo.observe(sb, { attributes: true });
      if (sb.parentNode) mo.observe(sb.parentNode, { attributes: true, childList: true });
    } catch (e) {}
  }

  function initSidebar() {
    if (applySidebar()) { setupSidebarObservers(); return; }
    var attempts = 0;
    var iv = setInterval(function () {
      if (++attempts > 60) { clearInterval(iv); return; }
      if (applySidebar()) { clearInterval(iv); setupSidebarObservers(); }
    }, 250);
  }

  // ── Header stack centering ────────────────────────────────────────────────
  var headerRO = null;
  var headerObservedEls = [];
  var lastHeaderTop = -1;
  var recomputeQueued = false;

  function isDesktopOrTablet() {
    try {
      return !(window.matchMedia('(max-width: 767px)').matches &&
               window.matchMedia('(orientation: portrait)').matches);
    } catch (e) {
      return true;
    }
  }

  // A full walk of every shadow root forces layout; on a room change it landed mid-slide, so each find is kept.
  var cached = {};
  function keep(key, find) {
    var el = cached[key];
    if (el && el.isConnected && isVisible(el)) return el;
    return (cached[key] = find());
  }

  function findRoomHeaderStack() { return keep('stack', walkHeaderStack); }
  function findActiveEntityRow() { return keep('row', walkEntityRow); }
  function findNavbar() { return keep('nav', walkNavbar); }

  // button-card renders the room hero inside a shadow root.  The element that
  // owns the hero styles is therefore not always root.host itself; depending
  // on the Home Assistant/card-mod version there can be one or more custom
  // element hosts between the header stack and the room card.  Resolve that
  // chain explicitly so extra cards can never end up underneath a fixed hero.
  function configTemplates(el) {
    var cfg = el && (el._config || el.config);
    var value = cfg && cfg.template;
    return Array.isArray(value) ? value : [value];
  }

  function isRoomHost(el) {
    if (!el) return false;
    if (el.classList && el.classList.contains('hemma-room')) return true;
    return configTemplates(el).some(function (template) {
      return String(template || '').indexOf('hemma_room') !== -1;
    });
  }

  function hostChain(el) {
    var chain = [];
    var node = el;
    var guard = 0;
    while (node && guard++ < 24) {
      if (chain.indexOf(node) === -1) chain.push(node);
      var root = node.getRootNode ? node.getRootNode() : null;
      var host = root && root.host;
      if (host && host !== node) {
        node = host;
      } else {
        node = node.parentElement;
      }
    }
    return chain;
  }

  function findRoomCardHost(stack) {
    if (!stack) return null;
    var chain = hostChain(stack);
    for (var i = 0; i < chain.length; i++) {
      if (isRoomHost(chain[i])) return chain[i];
    }
    var root = stack.getRootNode ? stack.getRootNode() : null;
    return root && root.host ? root.host : null;
  }

  function isVehicleCard(el) {
    if (!el) return false;
    var templates = configTemplates(el);
    if (templates.some(function (template) {
      return String(template || '').indexOf('hemma_vehicle') !== -1;
    })) return true;
    var cfg = el._config || el.config || {};
    var variables = cfg.variables || {};
    return !!(variables.vehicle_make || variables.vehicle_model || variables.entity_battery);
  }

  function findVehicleCards() {
    var found = [];
    walkFind(document, 'button-card', found, 0);
    return found.filter(function (el, index, list) {
      return list.indexOf(el) === index && isVehicleCard(el) && isVisible(el);
    });
  }

  function vehicleExtrasHeight() {
    var cards = findVehicleCards();
    var total = 0;
    for (var i = 0; i < cards.length; i++) {
      var card = cards[i];
      var rect = card.getBoundingClientRect();
      var height = rect.height;
      try {
        var cs = getComputedStyle(card);
        if (height <= 0) height = parseFloat(cs.height) || 0;
        height += (parseFloat(cs.marginTop) || 0) + (parseFloat(cs.marginBottom) || 0);
      } catch (e) {}
      // hemma_vehicle has a 360px design height.  Keep that minimum while
      // the custom element is still settling its shadow DOM.
      total += Math.max(320, height || 0);
    }
    return total;
  }

  function setHeroExtrasAttribute(hasExtras) {
    var stack = findRoomHeaderStack();
    if (!stack) return;
    var host = findRoomCardHost(stack);
    if (!host || !host.toggleAttribute) return;
    host.toggleAttribute('data-hemma-has-extras', !!hasExtras);
  }

  function walkHeaderStack() {
    var found = [];
    walkFind(document, '#badges_media', found, 0);
    for (var i = 0; i < found.length; i++) {
      var container = found[i].closest('#container');
      if (container && isVisible(container)) return container;
    }
    return null;
  }

  function walkEntityRow() {
    var found = [];
    var fallback = null;
    walkFind(document, 'hemma-smart-row', found, 0);
    for (var i = 0; i < found.length; i++) {
      var el = found[i];
      if (!isVisible(el)) continue;
      if (el._scrollMode === false) return el;
      // Some Hemma builds expose the desktop row with the default scroll
      // mode unset. It is still the active room row when it is visible; keep
      // it as a fallback so standalone cards below it are measured too.
      if (!fallback) fallback = el;
    }
    return fallback;
  }

  // The hemma-nav-bar host is a zero-height fixed anchor; .bar is the real box.
  function walkNavbar() {
    var found = [];
    walkFind(document, 'hemma-nav-bar', found, 0);
    for (var i = 0; i < found.length; i++) {
      var nb = found[i];
      var inner = nb.shadowRoot ? nb.shadowRoot.querySelector('.bar') : null;
      if (inner && isVisible(inner)) return inner;
    }
    return null;
  }

  function fallbackNavbarBottom() {
    var v = getComputedStyle(html).getPropertyValue('--hemma-nav-top-current').trim();
    var px = parseFloat(v);
    return isNaN(px) ? 60 : px + 40; // plus an approximate navbar height
  }

  // A card placed under the tile row is the one thing in this view still in
  // normal flow, so its height has to come off the hero or the view grows past
  // the viewport and the whole dashboard scrolls.
  var lastExtras = -1;
  function extrasHeight() {
    // The vehicle card is a standalone card after the room hero.  It lives
    // outside the hero's shadow root, so sibling walking cannot see it.  Use
    // its measured height directly; this is also stable when the row changes
    // state and prevents the card from being painted behind the hero.
    var vehicleHeight = vehicleExtrasHeight();
    if (vehicleHeight > 0) return vehicleHeight;

    var row = findActiveEntityRow();
    if (!row) return 0;
    var node = row;
    while (node.parentElement && node.parentElement.children.length < 2) {
      node = node.parentElement;
    }
    if (!node.parentElement) return 0;
    var kids = node.parentElement.children;
    var total = 0, seen = false, extraCount = 0;
    for (var i = 0; i < kids.length; i++) {
      if (kids[i] === node) { seen = true; continue; }
      if (!seen) continue;
      extraCount++;
      var r = kids[i].getBoundingClientRect();
      var height = r.height;
      // The gap a card sits in counts too, or the view is short by it.
      try {
        var cs = getComputedStyle(kids[i]);
        if (height <= 0) height = parseFloat(cs.height) || 0;
        total += height + (parseFloat(cs.marginTop) || 0) + (parseFloat(cs.marginBottom) || 0);
      } catch (e) {}
    }
    // Home Assistant can report a zero wrapper height for a custom card while
    // its shadow card is still being built. Keep the hero from covering the
    // extra card during that first layout pass; the next ResizeObserver pass
    // replaces this conservative estimate with the measured height.
    return total > 0 ? total : (extraCount ? extraCount * 380 : 0);
  }

  function applyExtras() {
    if (!isDesktopOrTablet()) return;
    var px = Math.round(extrasHeight());
    var hasExtras = px > 0;
    if (px !== lastExtras) {
      lastExtras = px;
      html.style.setProperty('--hemma-extras-h', px + 'px');
    }
    setHeroExtrasAttribute(hasExtras);
    // Touch displays keep the room hero fixed when there is no content below
    // it. Once a standalone card is placed after the smart row, however, a
    // fixed 100vh hero paints over that card. Switch the hero back into normal
    // flow and give it the exact remaining viewport height so the extra card
    // stays visible without making the dashboard scroll.
    html.style.setProperty('--hemma-room-card-position', hasExtras ? 'relative' : 'fixed');
    html.style.setProperty('--hemma-room-card-height', hasExtras ? 'calc(100svh - ' + px + 'px)' : '100dvh');
    html.style.setProperty('--hemma-room-card-min-height', hasExtras ? '0px' : '100dvh');
    html.style.setProperty('--hemma-room-card-max-height', hasExtras ? 'none' : '100dvh');
  }

  function setHeaderTop(px) {
    var rounded = Math.round(px);
    if (rounded !== lastHeaderTop) {
      lastHeaderTop = rounded;
      html.style.setProperty('--hero-top', rounded + 'px');
    }
  }

  // Overview hides the room card's header and rows, so there is nothing to place, and a search would never find them.
  function computeAndApplyHeader() {
    if (!isDesktopOrTablet() || window._hemmaOverview) return;
    applyExtras();

    var headerStack = findRoomHeaderStack();
    if (!headerStack) return;

    var entityRow = findActiveEntityRow();
    var navbar = findNavbar();
    var navbarBottom = navbar ? navbar.getBoundingClientRect().bottom : fallbackNavbarBottom();

    var viewportH = window.innerHeight;
    var headerH = headerStack.getBoundingClientRect().height;
    var entityRowH = entityRow ? entityRow.getBoundingClientRect().height : 0;

    var available = viewportH - navbarBottom - entityRowH;
    var centeredTop = navbarBottom + Math.max(0, (available - headerH) / 2);

    setHeaderTop(centeredTop);
  }

  function queueRecompute() {
    if (recomputeQueued) return;
    recomputeQueued = true;
    requestAnimationFrame(function () {
      recomputeQueued = false;
      computeAndApplyHeader();
    });
  }

  function observeEl(el) {
    if (!el || headerObservedEls.indexOf(el) !== -1) return;
    headerObservedEls.push(el);
    try { headerRO.observe(el); } catch (e) {}
  }

  function setupHeaderObservers() {
    if (!headerRO) {
      try { headerRO = new ResizeObserver(queueRecompute); } catch (e) { return; }
    }

    var headerStack = findRoomHeaderStack();
    if (headerStack) observeEl(headerStack);
    var entityRow = findActiveEntityRow();
    if (entityRow) observeEl(entityRow);

    // Catches zoom and devtools changes that don't fire a resize event.
    observeEl(html);
  }

  function initHeader() {
    if (window._hemmaOverview) return;
    computeAndApplyHeader();
    setupHeaderObservers();
    var attempts = 0;
    var iv = setInterval(function () {
      if (++attempts > 20 || headerObservedEls.length >= 2 || window._hemmaOverview) { clearInterval(iv); return; }
      computeAndApplyHeader();
      setupHeaderObservers();
    }, 250);
  }

  window.addEventListener('resize', queueRecompute);
  window.addEventListener('location-changed', function () {
    // Drop stale observations and re-discover once the new view has rendered.
    headerObservedEls = [];
    cached = {};
    lastExtras = -1;
    if (headerRO) { try { headerRO.disconnect(); } catch (e) {} }
    setTimeout(initHeader, 600);
  });

  setTimeout(initSidebar, 200);
  setTimeout(initSidebar, 1500);
  setTimeout(initSidebar, 5000);

  setTimeout(initHeader, 200);
  setTimeout(initHeader, 1500);
})();
