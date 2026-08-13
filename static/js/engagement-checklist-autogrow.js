(function () {
  function grow(el) {
    if (!el || el.tagName !== "TEXTAREA") return;
    el.style.height = "auto";
    var maxPx = parseFloat(getComputedStyle(el).maxHeight);
    if (Number.isNaN(maxPx) || maxPx <= 0) {
      maxPx = 384;
    }
    var h = el.scrollHeight;
    if (h > maxPx) {
      el.style.height = maxPx + "px";
      el.style.overflowY = "auto";
    } else {
      el.style.height = h + "px";
      el.style.overflowY = "hidden";
    }
  }

  function init(root) {
    (root || document).querySelectorAll("textarea[data-autogrow]").forEach(function (el) {
      grow(el);
      el.addEventListener("input", function () {
        grow(el);
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      init();
    });
  } else {
    init();
  }
})();

(function () {
  function navRoot() {
    return document.querySelector("[data-checklist-wa-nav]");
  }

  function openRename() {
    var panel = document.querySelector("[data-wa-rename-panel]");
    var root = navRoot();
    if (!panel || !root) return;
    panel.hidden = false;
    root.classList.add("engagement-checklist-wa-nav--editing");
    var inp = panel.querySelector("[data-wa-rename-input]");
    if (inp) inp.focus();
  }

  function closeRename() {
    var panel = document.querySelector("[data-wa-rename-panel]");
    var root = navRoot();
    if (!panel || !root) return;
    panel.hidden = true;
    root.classList.remove("engagement-checklist-wa-nav--editing");
    var inp = panel.querySelector("[data-wa-rename-input]");
    if (inp) {
      var orig = inp.getAttribute("data-original-value");
      if (orig !== null) inp.value = orig;
    }
  }

  document.addEventListener("click", function (e) {
    var t = e.target;
    if (!(t instanceof HTMLElement)) return;
    if (t.closest("[data-wa-rename-open]")) {
      openRename();
      e.preventDefault();
    }
    if (t.closest("[data-wa-rename-cancel]")) {
      closeRename();
      e.preventDefault();
    }
  });
})();
