// Shared behaviour for the app shell: busy buttons and the clip player.
(function () {
  // Forms: show a busy state and block double submits on slow networks.
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form.dataset.submitted) { e.preventDefault(); return; }
    form.dataset.submitted = "1";
    form.querySelectorAll("button[type=submit], button:not([type])").forEach(function (b) { b.classList.add("is-busy"); });
  });

  // Coming back (e.g. from WhatsApp) restores the page from cache; let its forms submit again.
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    document.querySelectorAll("form[data-submitted]").forEach(function (f) {
      delete f.dataset.submitted;
      f.querySelectorAll(".is-busy").forEach(function (b) { b.classList.remove("is-busy"); });
    });
  });

  // Copy buttons: data-copy="#selector" copies that element's text; data-copy-text copies the value.
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-copy], [data-copy-text]");
    if (!b) return;
    var text = b.dataset.copyText || (document.querySelector(b.dataset.copy) || {}).innerText || "";
    var done = function () { var old = b.textContent; b.textContent = "Copied"; setTimeout(function () { b.textContent = old; }, 1600); };
    if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () { window.prompt("Copy this:", text); });
    else window.prompt("Copy this:", text);
  });

  // Dish suggestions add a line to the wishlist.
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-add-dish]");
    var list = document.querySelector("[data-dish-list]");
    if (!b || !list) return;
    var lines = list.value.split("\n").map(function (l) { return l.trim(); }).filter(Boolean);
    if (lines.map(function (l) { return l.toLowerCase(); }).indexOf(b.dataset.addDish.toLowerCase()) < 0) lines.push(b.dataset.addDish);
    list.value = lines.join("\n");
    b.hidden = true;
  });

  // Reveal date: "N days away".
  document.querySelectorAll("[data-days-away]").forEach(function (input) {
    var label = document.querySelector("[data-days-away-label]");
    function show() {
      if (!label || !input.value) { if (label) label.textContent = ""; return; }
      var days = Math.round((new Date(input.value + "T00:00:00") - new Date(new Date().toDateString())) / 864e5);
      label.textContent = days > 0 ? days + " day" + (days === 1 ? "" : "s") + " away" + (days < 21 ? ". That's soon; start with the dishes that matter most." : ". Plenty of time.") : "";
    }
    input.addEventListener("input", show); show();
  });

  // Recipe / What they said toggle.
  document.querySelectorAll(".toggle [data-toggle]").forEach(function (tab) {
    tab.addEventListener("click", function (e) {
      e.preventDefault();
      document.querySelectorAll(".toggle [data-toggle]").forEach(function (t) { t.classList.toggle("on", t === tab); });
      document.querySelectorAll("[data-pane]").forEach(function (p) { p.hidden = p.dataset.pane !== tab.dataset.toggle; });
    });
  });

  // Text boxes grow with what's typed, so long ingredients and steps are never cut off.
  function grow(el) { el.style.height = "auto"; el.style.height = el.scrollHeight + 2 + "px"; }
  function autogrow(scope) {
    scope.querySelectorAll("textarea[data-autogrow]").forEach(function (el) {
      grow(el);
      el.addEventListener("input", function () { grow(el); });
    });
  }
  autogrow(document);
  window.addEventListener("resize", function () { document.querySelectorAll("textarea[data-autogrow]").forEach(grow); });

  // Design your book: each style has its own colours; picking a style shows them.
  document.querySelectorAll("input[name=theme]").forEach(function (radio) {
    radio.addEventListener("change", function () {
      document.querySelectorAll("[data-accents-for]").forEach(function (group) {
        group.hidden = group.dataset.accentsFor !== radio.value;
        if (!group.hidden) group.querySelector("input").checked = true;
      });
    });
  });

  // Typing a new dish name picks the "A new dish" option.
  document.querySelectorAll("input[data-picks]").forEach(function (input) {
    input.addEventListener("input", function () {
      var radio = input.form.querySelector("input[type=radio][value='" + input.dataset.picks + "']");
      if (radio && input.value.trim()) radio.checked = true;
    });
  });

  // Photo pickers send their form as soon as a photo is chosen.
  document.querySelectorAll("input[type=file][data-autosubmit]").forEach(function (input) {
    input.addEventListener("change", function () {
      if (!input.files.length) return;
      if (input.form.requestSubmit) input.form.requestSubmit(); else input.form.submit();
    });
  });

  // Fit a photo to its spot in the book: drag to move, slider or pinch to zoom. Every frame shows
  // the same crop cut to its own shape, worked out as photo_service.crop_box does for the PDF.
  document.querySelectorAll("form[data-photo-fit]").forEach(function (form) {
    var x = form.elements.x, y = form.elements.y, zoom = form.elements.zoom;
    var maxZoom = parseFloat(form.dataset.maxZoom) || 4;
    var frames = Array.prototype.slice.call(form.querySelectorAll(".fit-frame"));
    var probe = new Image(), iw = 0, ih = 0;

    function clamp(v, lo, hi) { return Math.min(Math.max(v, lo), hi); }
    function box(frame) {  // the crop for this frame, in photo pixels
      var aspect = parseFloat(frame.dataset.aspect), z = parseFloat(zoom.value);
      var w = iw / ih > aspect ? ih * aspect : iw, h = iw / ih > aspect ? ih : iw / aspect;
      w /= z; h /= z;
      return { w: w, h: h,
               left: clamp(parseFloat(x.value) * iw - w / 2, 0, iw - w),
               top: clamp(parseFloat(y.value) * ih - h / 2, 0, ih - h) };
    }
    function draw() {
      if (!iw) return;
      frames.forEach(function (frame) {
        var b = box(frame), scale = frame.clientWidth / b.w, img = frame.querySelector("img");
        img.style.width = iw * scale + "px";
        img.style.height = ih * scale + "px";
        img.style.left = -b.left * scale + "px";
        img.style.top = -b.top * scale + "px";
      });
    }
    function keepInside() {  // store the centre the main frame actually shows, so dragging back responds at once
      var b = box(frames[0]);
      x.value = ((b.left + b.w / 2) / iw).toFixed(4);
      y.value = ((b.top + b.h / 2) / ih).toFixed(4);
    }

    var pointers = {}, startGap = 0, startZoom = 1;
    frames.forEach(function (frame) {
      frame.addEventListener("pointerdown", function (e) {
        frame.setPointerCapture(e.pointerId);
        pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
        var ids = Object.keys(pointers);
        if (ids.length === 2) {
          startGap = Math.hypot(pointers[ids[0]].x - pointers[ids[1]].x, pointers[ids[0]].y - pointers[ids[1]].y);
          startZoom = parseFloat(zoom.value);
        }
      });
      frame.addEventListener("pointermove", function (e) {
        var last = pointers[e.pointerId];
        if (!last || !iw) return;
        pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
        var ids = Object.keys(pointers);
        if (ids.length === 2) {
          var gap = Math.hypot(pointers[ids[0]].x - pointers[ids[1]].x, pointers[ids[0]].y - pointers[ids[1]].y);
          if (startGap) zoom.value = clamp(startZoom * gap / startGap, 1, maxZoom);
        } else {
          var scale = frame.clientWidth / box(frame).w;
          x.value = parseFloat(x.value) - (e.clientX - last.x) / scale / iw;
          y.value = parseFloat(y.value) - (e.clientY - last.y) / scale / ih;
        }
        keepInside();
        draw();
      });
      ["pointerup", "pointercancel"].forEach(function (type) {
        frame.addEventListener(type, function (e) { delete pointers[e.pointerId]; startGap = 0; });
      });
      frame.addEventListener("wheel", function (e) {
        e.preventDefault();
        zoom.value = clamp(parseFloat(zoom.value) * (e.deltaY < 0 ? 1.06 : 1 / 1.06), 1, maxZoom);
        keepInside();
        draw();
      }, { passive: false });
    });
    zoom.addEventListener("input", function () { keepInside(); draw(); });
    form.querySelector("[data-fit-reset]").addEventListener("click", function () {
      x.value = 0.5; y.value = 0.5; zoom.value = 1; draw();
    });
    window.addEventListener("resize", draw);
    probe.onload = function () {
      iw = probe.naturalWidth; ih = probe.naturalHeight;
      form.classList.add("ready");
      draw();
    };
    probe.src = form.dataset.src;
  });

  // "Add an ingredient": copy the last row, empty.
  document.querySelectorAll("[data-add-row]").forEach(function (button) {
    var rows = button.previousElementSibling;
    button.addEventListener("click", function () {
      var last = rows.lastElementChild, row = last.cloneNode(true);
      row.querySelectorAll("input, textarea").forEach(function (f) { f.value = ""; });
      rows.appendChild(row); autogrow(row);
      row.querySelector("textarea, input").focus();
    });
  });

  // Ask before anything that can't be undone.
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) { if (!window.confirm(form.dataset.confirm)) e.preventDefault(); });
  });

  // Pages that are waiting on the pipeline refresh themselves.
  var waiting = document.querySelector("[data-autorefresh]");
  if (waiting) setTimeout(function () { window.location.reload(); }, 1000 * Number(waiting.dataset.autorefresh));

  // Players: a play button that plays a list of clip URLs in order.
  var PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4.5v15l12-7.5z" fill="currentColor"/></svg>';
  var PAUSE = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor"/><rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor"/></svg>';
  document.querySelectorAll("[data-player]").forEach(function (el) {
    var urls = JSON.parse(el.dataset.urls || "[]"), current = 0, audio = new Audio(), retried = false;
    var button = el.querySelector("[data-play]"), status = el.querySelector("[data-status]");
    audio.preload = "none";
    if (!urls.length) { button.disabled = true; return; }
    function load(n) { current = n; audio.src = urls[n]; }
    button.addEventListener("click", function () {
      if (!audio.src) load(0);
      if (audio.paused) audio.play(); else audio.pause();
    });
    audio.addEventListener("play", function () {
      button.innerHTML = PAUSE; button.setAttribute("aria-label", "Pause");
      if (status) status.textContent = urls.length > 1 ? "Part " + (current + 1) + " of " + urls.length : "";
      el.dispatchEvent(new CustomEvent("player:play"));
    });
    audio.addEventListener("pause", function () { button.innerHTML = PLAY; button.setAttribute("aria-label", "Play"); });
    audio.addEventListener("ended", function () {
      if (current + 1 < urls.length) { load(current + 1); audio.play(); } else { load(0); if (status) status.textContent = ""; }
    });
    audio.addEventListener("error", function () {
      // Signed URLs expire; ask the server for a fresh one once, then give up politely.
      if (!retried) { retried = true; var t = audio.currentTime; load(current); audio.currentTime = t; audio.play(); return; }
      if (status) status.textContent = "Couldn't load the recording. Try again.";
    });
  });
})();
