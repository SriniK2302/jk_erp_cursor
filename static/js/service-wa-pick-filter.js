/**
 * Client-side filter and bulk selection for standard work-area pick lists.
 *
 * Markup:
 *   [data-service-wa-pick]
 *     input[data-service-wa-pick-search]  (optional)
 *     button[data-service-wa-pick-select-all]  (optional)
 *     button[data-service-wa-pick-clear-all]  (optional)
 *     li[data-service-wa-pick-row][data-search-text="..."]
 *     [data-service-wa-pick-no-results] (optional, hidden when no query or matches)
 */
(function () {
  "use strict";

  function normalize(raw) {
    return String(raw || "").trim().toLowerCase();
  }

  function enabledCheckboxes(rowNodes) {
    const boxes = [];
    rowNodes.forEach((li) => {
      const cb = li.querySelector(
        'input[type="checkbox"][name="service_work_area_ids"]:not(:disabled)'
      );
      if (cb) {
        boxes.push(cb);
      }
    });
    return boxes;
  }

  function wire(root) {
    const rows = root.querySelectorAll("[data-service-wa-pick-row]");
    if (!rows.length) {
      return;
    }

    const input = root.querySelector("[data-service-wa-pick-search]");
    const noResults = root.querySelector("[data-service-wa-pick-no-results]");
    const selectAllBtn = root.querySelector("[data-service-wa-pick-select-all]");
    const clearAllBtn = root.querySelector("[data-service-wa-pick-clear-all]");

    function visibleRows() {
      return Array.from(rows).filter((li) => !li.hidden);
    }

    function applyFilter() {
      if (!input) {
        return;
      }
      const q = normalize(input.value);
      let visible = 0;
      rows.forEach((li) => {
        const hay = normalize(li.getAttribute("data-search-text") || "");
        const show = !q || hay.includes(q);
        li.hidden = !show;
        if (show) {
          visible += 1;
        }
      });
      if (noResults) {
        noResults.hidden = !(q && visible === 0);
      }
    }

    if (input) {
      input.addEventListener("input", applyFilter);
      input.addEventListener("search", applyFilter);
    }

    if (selectAllBtn) {
      selectAllBtn.addEventListener("click", () => {
        enabledCheckboxes(visibleRows()).forEach((cb) => {
          cb.checked = true;
        });
      });
    }

    if (clearAllBtn) {
      clearAllBtn.addEventListener("click", () => {
        enabledCheckboxes(Array.from(rows)).forEach((cb) => {
          cb.checked = false;
        });
      });
    }
  }

  function init() {
    document.querySelectorAll("[data-service-wa-pick]").forEach(wire);
  }

  init();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  }
})();
