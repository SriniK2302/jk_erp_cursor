/**
 * Open / close the preparatory "standard work areas" picker block.
 *
 * Markup: [data-service-wa-pick-disclosure]
 *   [data-service-wa-pick-open]  [data-service-wa-pick-close] (optional; hidden when closed)
 *   [data-service-wa-pick-body] (hidden until opened)
 */
(function () {
  "use strict";

  function wire(wrap) {
    if (wrap.dataset.serviceWaPickDisclosureWired === "1") {
      return;
    }
    wrap.dataset.serviceWaPickDisclosureWired = "1";
    const body = wrap.querySelector("[data-service-wa-pick-body]");
    const openBtn = wrap.querySelector("[data-service-wa-pick-open]");
    const closeBtn = wrap.querySelector("[data-service-wa-pick-close]");
    if (!body || !openBtn || !closeBtn) {
      return;
    }

    function setOpen(open) {
      body.hidden = !open;
      openBtn.hidden = open;
      closeBtn.hidden = !open;
      openBtn.setAttribute("aria-expanded", open ? "true" : "false");
      closeBtn.setAttribute("aria-expanded", open ? "true" : "false");
    }

    openBtn.addEventListener("click", function () {
      setOpen(true);
    });
    closeBtn.addEventListener("click", function () {
      setOpen(false);
    });
  }

  function init() {
    document.querySelectorAll("[data-service-wa-pick-disclosure]").forEach(wire);
  }

  init();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
