// In-app recorder (UX S2): MediaRecorder -> 5 s chunks -> IndexedDB copy -> resumable upload.
(function () {
  var root = document.querySelector("[data-recorder]");
  if (!root) return;
  var CHUNK_MS = 5000;
  var csrf = (document.querySelector("meta[name=csrf-token]") || {}).content || "";
  var $ = function (sel) { return root.querySelector(sel); };
  var startBtn = $("[data-rec-start]"), controls = $("[data-rec-controls]"), pauseBtn = $("[data-rec-pause]"),
      doneBtn = $("[data-rec-done]"), statusEl = $("[data-rec-status]"), timerEl = $("[data-timer]");
  var recorder, stream, upload, seconds = 0, tick, chunkNo = 0, analyser, rafId, promptTimer;

  // ── IndexedDB: every chunk is kept on the phone until the server has the whole recording.
  var dbp = new Promise(function (resolve) {
    if (!window.indexedDB) return resolve(null);
    var req = indexedDB.open("andaaz-recordings", 1);
    req.onupgradeneeded = function () {
      req.result.createObjectStore("chunks");
      req.result.createObjectStore("uploads", { keyPath: "id" });
    };
    req.onsuccess = function () { resolve(req.result); };
    req.onerror = function () { resolve(null); };
  });
  function idb(store, mode, fn) {
    return dbp.then(function (db) {
      if (!db) return null;
      return new Promise(function (resolve) {
        var tx = db.transaction(store, mode), result;
        Promise.resolve(fn(tx.objectStore(store))).then(function (r) { result = r; });
        tx.oncomplete = function () { resolve(result); };
        tx.onerror = function () { resolve(null); };
      });
    });
  }
  function reqP(r) { return new Promise(function (res) { r.onsuccess = function () { res(r.result); }; r.onerror = function () { res(null); }; }); }
  function saveUpload(u) { return idb("uploads", "readwrite", function (s) { s.put(u); }); }
  function saveChunk(id, n, blob) { return idb("chunks", "readwrite", function (s) { s.put(blob, id + ":" + n); }); }
  function getChunk(id, n) { return idb("chunks", "readonly", function (s) { return reqP(s.get(id + ":" + n)); }); }
  function forget(u) {
    return idb("chunks", "readwrite", function (s) { for (var n = 0; n < u.chunks; n++) s.delete(u.id + ":" + n); })
      .then(function () { return idb("uploads", "readwrite", function (s) { s.delete(u.id); }); });
  }
  function pendingUploads() {
    return idb("uploads", "readonly", function (s) { return reqP(s.getAll()); }).then(function (all) {
      return (all || []).filter(function (u) { return u.project === root.dataset.project && u.chunks > 0 && (!upload || u.id !== upload.id); });
    });
  }

  // ── Server calls, retried with backoff so a flaky network only slows things down.
  function post(url, body, isJson) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: isJson ? { "Content-Type": "application/json", "X-CSRFToken": csrf } : { "X-CSRFToken": csrf, "Content-Type": "application/octet-stream" },
      body: isJson ? JSON.stringify(body) : body
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (!r.ok) { var e = new Error(data.error || "HTTP " + r.status); e.status = r.status; e.data = data; throw e; }
        return data;
      });
    });
  }
  function retry(fn, tries) {
    return fn().catch(function (e) {
      if (tries <= 1 || (e.status && e.status < 500 && e.status !== 409 && e.status !== 429)) throw e;
      return new Promise(function (r) { setTimeout(r, Math.min(16000, 1000 * Math.pow(2, 6 - tries))); })
        .then(function () { return retry(fn, tries - 1); });
    });
  }
  function base(u) { return root.dataset.openUrl + "/" + u.id; }
  function sendChunk(u, n, blob) { return retry(function () { return post(base(u) + "/chunk/" + n, blob, false); }, 6); }
  function finish(u) {
    statusEl.textContent = "Saving your recording…";
    return retry(function () {
      return post(base(u) + "/complete", { chunks: u.chunks, seconds: u.seconds }, true).catch(function (e) {
        if (e.status === 409 && e.data && e.data.missing) {
          // Re-send whatever didn't arrive, from the copy on the phone, then try again.
          return Promise.all(e.data.missing.map(function (n) {
            return getChunk(u.id, n).then(function (b) { if (b) return sendChunk(u, n, b); });
          })).then(function () { throw e; });
        }
        throw e;
      });
    }, 6).then(function (data) {
      return forget(u).then(function () { if (data.redirect) window.location.href = data.redirect; });
    });
  }

  // ── Recording
  function pickType() {
    var types = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"];
    for (var i = 0; i < types.length; i++) if (window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(types[i])) return types[i];
    return "";
  }
  function showError(text) {
    var box = $("[data-rec-error]"); box.hidden = false; $("[data-rec-error-text]").textContent = text;
  }
  function newId() {
    var a = new Uint8Array(16); (window.crypto || window.msCrypto).getRandomValues(a);
    return Array.prototype.map.call(a, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }
  function fmt(s) { return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2); }
  function drawWave() {
    var canvas = $("[data-wave]"), ctx = canvas.getContext("2d"), data = new Uint8Array(analyser.frequencyBinCount);
    (function frame() {
      analyser.getByteTimeDomainData(data);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = "#C2412D"; ctx.lineWidth = 2; ctx.beginPath();
      for (var i = 0; i < data.length; i++) {
        var x = i / data.length * canvas.width, y = data[i] / 255 * canvas.height;
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      }
      ctx.stroke(); rafId = requestAnimationFrame(frame);
    })();
  }
  function rotatePrompts() {
    var prompts = JSON.parse(root.querySelector("[data-prompts]").dataset.prompts), i = 0, el = root.querySelector("[data-prompt]");
    promptTimer = setInterval(function () { i = (i + 1) % prompts.length; el.textContent = prompts[i]; }, 20000);
  }

  startBtn.addEventListener("click", function () {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      return showError("This browser can't record. Record a voice note in WhatsApp or your phone's recorder and add the file instead.");
    }
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }).then(function (s) {
      stream = s;
      var type = pickType();
      recorder = type ? new MediaRecorder(stream, { mimeType: type }) : new MediaRecorder(stream);
      var dish = root.querySelector("[data-dish]");
      upload = { id: newId(), project: root.dataset.project, kind: root.dataset.kind, chunks: 0, seconds: 0, finished: false,
                 type: recorder.mimeType || type || "audio/webm", dish: dish ? dish.value : null,
                 recipe: root.dataset.recipeId || null };
      var opened = retry(function () {
        return post(root.dataset.openUrl, { client_upload_id: upload.id, kind: upload.kind, content_type: upload.type,
          dish_id: upload.dish, recipe_id: upload.recipe }, true);
      }, 6);
      upload.opened = opened;
      saveUpload(stripPromise(upload));
      chunkNo = 0;
      recorder.ondataavailable = function (e) {
        if (!e.data || !e.data.size) return;
        var n = chunkNo++; upload.chunks = chunkNo;
        saveChunk(upload.id, n, e.data).then(function () { saveUpload(stripPromise(upload)); });
        opened.then(function () { return sendChunk(upload, n, e.data); }).catch(function () { /* kept on the phone; sent on Done */ });
      };
      recorder.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        cancelAnimationFrame(rafId); clearInterval(tick); clearInterval(promptTimer);
        upload.finished = true; upload.seconds = seconds;
        // ondataavailable fires before onstop; give the last chunk a moment to land in IndexedDB.
        setTimeout(function () {
          saveUpload(stripPromise(upload)).then(function () {
            return opened.then(function () { return finish(upload); });
          }).catch(function () {
            statusEl.textContent = "";
            showError("The network dropped. Your recording is safe on this phone; try uploading again when you're online.");
            showPending();
          });
        }, 300);
      };
      recorder.start(CHUNK_MS);
      try {
        var ac = new (window.AudioContext || window.webkitAudioContext)();
        analyser = ac.createAnalyser(); analyser.fftSize = 1024;
        ac.createMediaStreamSource(stream).connect(analyser); drawWave();
      } catch (e) { /* the waveform is decoration */ }
      seconds = 0; tick = setInterval(function () {
        if (recorder.state !== "recording") return;
        seconds++; timerEl.textContent = fmt(seconds);
        if (seconds === 25 * 60) statusEl.textContent = "Five minutes left in this part. You can record a second part after.";
        if (seconds >= 30 * 60) doneBtn.click();  // long recordings are saved in 30-minute parts
      }, 1000);
      rotatePrompts();
      startBtn.classList.add("is-recording"); startBtn.disabled = true;
      controls.hidden = false; statusEl.textContent = "Listening. Talk the way you would in the kitchen.";
      window.addEventListener("beforeunload", warn);
    }).catch(function (err) {
      showError(err && err.name === "NotAllowedError"
        ? "The microphone is blocked. Allow it in your browser's site settings (the lock icon by the address), then try again."
        : "We couldn't use the microphone. Close other apps that might be using it, or add a voice note file instead.");
    });
  });
  function stripPromise(u) { var c = {}; for (var k in u) if (k !== "opened") c[k] = u[k]; return c; }
  function warn(e) { if (recorder && recorder.state !== "inactive") { e.preventDefault(); e.returnValue = ""; } }

  pauseBtn.addEventListener("click", function () {
    if (recorder.state === "recording") { recorder.pause(); pauseBtn.textContent = "Carry on"; startBtn.classList.remove("is-recording"); statusEl.textContent = "Paused."; }
    else if (recorder.state === "paused") { recorder.resume(); pauseBtn.textContent = "Pause"; startBtn.classList.add("is-recording"); statusEl.textContent = "Listening."; }
  });
  doneBtn.addEventListener("click", function () {
    if (seconds < 3) { statusEl.textContent = "That was very short. Keep talking, then tap Done."; return; }
    doneBtn.classList.add("is-busy"); pauseBtn.disabled = true; startBtn.classList.remove("is-recording");
    window.removeEventListener("beforeunload", warn);
    recorder.stop();
  });

  // ── A recording left over from a dropped connection.
  function showPending() {
    pendingUploads().then(function (list) {
      var box = $("[data-pending]"); if (!list.length) { box.hidden = true; return; }
      box.hidden = false;
      $("[data-pending-retry]").onclick = function () {
        var u = list[0];
        $("[data-pending-retry]").classList.add("is-busy");
        retry(function () {
          return post(root.dataset.openUrl, { client_upload_id: u.id, kind: u.kind, content_type: u.type, dish_id: u.dish, recipe_id: u.recipe }, true);
        }, 4).then(function () {
          var sends = []; u.seconds = u.seconds || 0;
          for (var n = 0; n < u.chunks; n++) (function (n) { sends.push(getChunk(u.id, n).then(function (b) { if (b) return sendChunk(u, n, b); })); })(n);
          return Promise.all(sends);
        }).then(function () { return finish(u); }).catch(function () {
          $("[data-pending-retry]").classList.remove("is-busy");
          statusEl.textContent = "Still offline. We'll keep it safe; try again in a bit.";
        });
      };
      $("[data-pending-discard]").onclick = function () { forget(list[0]).then(showPending); };
    });
  }
  showPending();
})();
