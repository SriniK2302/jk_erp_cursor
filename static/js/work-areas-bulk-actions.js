/**
 * Bulk Add all / Delete all on engagement and division work area list pages.
 */
(function () {
  "use strict";

  let progressTimer = null;

  function csrfToken() {
    return document.querySelector("#wa-bulk-csrf-form input[name=csrfmiddlewaretoken]")?.value || "";
  }

  function overlayEls() {
    return {
      overlay: document.getElementById("wa-bulk-progress-overlay"),
      bar: document.getElementById("wa-bulk-progress-bar"),
      label: document.getElementById("wa-bulk-progress-label"),
      status: document.getElementById("wa-bulk-progress-status"),
    };
  }

  function showProgress(title, label) {
    const { overlay, bar, label: labelEl, status } = overlayEls();
    if (!overlay || !bar) {
      return;
    }
    const titleEl = document.getElementById("wa-bulk-progress-title");
    if (titleEl && title) {
      titleEl.textContent = title;
    }
    if (labelEl) {
      labelEl.textContent = label || "Working…";
    }
    if (status) {
      status.textContent = "Starting…";
    }
    bar.style.width = "8%";
    overlay.hidden = false;
    clearInterval(progressTimer);
    let pct = 8;
    progressTimer = window.setInterval(() => {
      pct = Math.min(pct + 4, 88);
      bar.style.width = `${pct}%`;
    }, 280);
  }

  function finishProgress(message, ok) {
    const { overlay, bar, status } = overlayEls();
    clearInterval(progressTimer);
    progressTimer = null;
    if (bar) {
      bar.style.width = ok ? "100%" : "0%";
    }
    if (status) {
      status.textContent = message || (ok ? "Done." : "Failed.");
    }
    window.setTimeout(() => {
      if (overlay) {
        overlay.hidden = true;
      }
      if (ok) {
        window.location.reload();
      }
    }, ok ? 900 : 2200);
  }

  async function postBulkAction(action, label) {
    showProgress("Please wait", label);
    const fd = new FormData();
    fd.set("csrfmiddlewaretoken", csrfToken());
    fd.set("action", action);
    const url = window.location.pathname + window.location.search;
    try {
      const resp = await fetch(url, {
        method: "POST",
        body: fd,
        headers: {
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      let data = {};
      try {
        data = await resp.json();
      } catch {
        data = {};
      }
      if (!resp.ok || data.ok !== true) {
        const msg =
          (typeof data.message === "string" && data.message.trim()) ||
          (Array.isArray(data.errors) && data.errors.join(" ")) ||
          `Request failed (${resp.status}).`;
        finishProgress(msg, false);
        return;
      }
      finishProgress(data.message || "Done.", true);
    } catch {
      finishProgress("Network error. Try again.", false);
    }
  }

  function wire() {
    const addBtn = document.querySelector("[data-wa-bulk-add-all]");
    const delBtn = document.querySelector("[data-wa-bulk-delete-all]");
    if (!addBtn && !delBtn) {
      return;
    }
    if (addBtn) {
      addBtn.addEventListener("click", () => {
        const msg = addBtn.getAttribute("data-confirm") || "Add all standard work areas?";
        if (!window.confirm(msg)) {
          return;
        }
        void postBulkAction("bulk_add_all_standard", "Adding work areas and checklist lines…");
      });
    }
    if (delBtn) {
      delBtn.addEventListener("click", () => {
        const msg =
          delBtn.getAttribute("data-confirm") ||
          "Delete all work areas without notes?";
        if (!window.confirm(msg)) {
          return;
        }
        void postBulkAction(
          "bulk_delete_all_without_queries",
          "Deleting work areas without notes…"
        );
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }
})();
