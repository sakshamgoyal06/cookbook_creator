// R7 Pay: open Razorpay Checkout from the pay step, then confirm the signed result with the server.
(function () {
  var marker = document.querySelector("[data-pay]");
  if (!marker) return;
  var form = marker.closest("form");
  var button = form.querySelector("button[type=submit]");
  var errorEl = document.querySelector("[data-pay-error]");
  var token = form.querySelector("input[name=csrf_token]").value;
  var label = button.textContent;

  function post(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": token },
      body: JSON.stringify(body || {})
    }).then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); });
  }
  function fail(message) {
    errorEl.textContent = message || "Payment didn't go through. Please try again.";
    errorEl.hidden = false;
    button.disabled = false; button.textContent = label;
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!window.Razorpay) return fail("Couldn't load the payment window. Please check your connection.");
    errorEl.hidden = true;
    button.disabled = true; button.textContent = "Opening payment…";
    post(marker.dataset.orderUrl).then(function (res) {
      if (!res.ok) {
        if (res.data.redirect) { window.location.href = res.data.redirect; return; }
        return fail(res.data.error);
      }
      var o = res.data;
      var checkout = new window.Razorpay({
        key: o.key, order_id: o.order_id, amount: o.amount, currency: o.currency,
        name: o.name, description: o.description, prefill: o.prefill,
        theme: { color: "#2E5B45" },
        config: { display: { preferences: { show_default_blocks: true }, sequence: ["block.upi"],
                             blocks: { upi: { name: "Pay with UPI", instruments: [{ method: "upi" }] } } } },
        handler: function (result) {
          button.textContent = "Confirming…";
          post(marker.dataset.verifyUrl, result).then(function (v) {
            if (v.ok && v.data.redirect) window.location.href = v.data.redirect;
            else fail(v.data.error);
          }).catch(function () { window.location.reload(); });
        },
        modal: { ondismiss: function () { button.disabled = false; button.textContent = label; } }
      });
      checkout.on("payment.failed", function (r) { fail(r && r.error && r.error.description); });
      checkout.open();
    }).catch(function () { fail("Couldn't reach us. Please check your connection and try again."); });
  });
})();
