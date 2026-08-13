/**
 * Excel-style column resize for [data-grid-root] panels with a table.data-grid.
 * Persists widths in localStorage (per browser). Does not change server data.
 *
 * Storage: one JSON object under jkErp.gridColWidths.v1 — keys from data-grid-id
 * (recommended for pages with a variable number of grids) or "p:pathname|index"
 * for the nth [data-grid-root] on the page.
 *
 * Opt out: data-grid-no-resize on [data-grid-root]
 */
(function () {
  "use strict";

  var STORAGE_KEY = "jkErp.gridColWidths.v1";
  var MIN_W = 56;

  function loadAll() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return {};
      }
      var o = JSON.parse(raw);
      return o && typeof o === "object" ? o : {};
    } catch (e) {
      return {};
    }
  }

  function saveAll(obj) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(obj));
    } catch (e) {}
  }

  function storageKeyFor(root) {
    var id = (root.getAttribute("data-grid-id") || "").trim();
    var layoutVer = (root.getAttribute("data-grid-layout-version") || "").trim();
    if (id) {
      var key = "id:" + id.replace(/[^a-zA-Z0-9_.-]/g, "_");
      if (layoutVer) {
        key += "|lv:" + layoutVer.replace(/[^a-zA-Z0-9_.-]/g, "_");
      }
      return key;
    }
    var roots = Array.from(document.querySelectorAll("[data-grid-root]"));
    var idx = roots.indexOf(root);
    if (idx < 0) {
      idx = 0;
    }
    return "p:" + location.pathname + "|" + idx;
  }

  function firstHeaderRow(thead) {
    if (!thead) {
      return null;
    }
    var ch = thead.children;
    for (var i = 0; i < ch.length; i++) {
      if (ch[i].tagName === "TR") {
        return ch[i];
      }
    }
    return thead.querySelector("tr");
  }

  function skipResizeTh(th) {
    if (!th || th.tagName !== "TH") {
      return true;
    }
    var cs = Number(th.getAttribute("colspan") || "1");
    if (cs !== 1) {
      return true;
    }
    return false;
  }

  function measureThWidths(ths) {
    return ths.map(function (th) {
      return Math.round(th.getBoundingClientRect().width);
    });
  }

  function ensureColgroup(table, n) {
    var cg = table.querySelector("colgroup");
    var cols;
    if (!cg) {
      cg = document.createElement("colgroup");
      for (var i = 0; i < n; i++) {
        cg.appendChild(document.createElement("col"));
      }
      table.insertBefore(cg, table.firstChild);
    }
    cols = Array.from(cg.querySelectorAll("col"));
    while (cols.length < n) {
      cg.appendChild(document.createElement("col"));
      cols.push(cg.lastChild);
    }
    while (cols.length > n) {
      cg.removeChild(cg.lastChild);
      cols.pop();
    }
    return cols;
  }

  function minWidthForTh(th) {
    if (!th) {
      return MIN_W;
    }
    var custom = parseInt(th.getAttribute("data-col-min-px") || "", 10);
    if (Number.isFinite(custom) && custom >= MIN_W) {
      return custom;
    }
    return MIN_W;
  }

  function applyWidths(table, cols, widthsPx, ths) {
    table.style.tableLayout = "fixed";
    for (var i = 0; i < cols.length; i++) {
      var w = widthsPx[i];
      var minW = ths && ths[i] ? minWidthForTh(ths[i]) : MIN_W;
      if (typeof w === "number" && w >= MIN_W) {
        cols[i].style.width = Math.max(minW, w) + "px";
      }
    }
  }

  function snapshotWidths(cols, ths) {
    var out = [];
    for (var i = 0; i < cols.length; i++) {
      var fromCol = cols[i].style.width;
      if (fromCol) {
        var px = parseInt(fromCol, 10);
        if (Number.isFinite(px) && px >= MIN_W) {
          out.push(px);
          continue;
        }
      }
      out.push(Math.round(ths[i].getBoundingClientRect().width));
    }
    return out;
  }

  function initGrid(root) {
    if (root.getAttribute("data-grid-no-resize") === "1") {
      return;
    }
    if (root._jkColResize) {
      return;
    }
    var table = root.querySelector("table.data-grid");
    if (!table) {
      return;
    }
    var thead = table.querySelector("thead");
    var headerTr = firstHeaderRow(thead);
    if (!headerTr) {
      return;
    }
    var ths = Array.from(headerTr.children).filter(function (el) {
      return el.tagName === "TH" && Number(el.getAttribute("colspan") || "1") === 1;
    });
    if (ths.length === 0) {
      return;
    }

    root._jkColResize = true;

    var storeKey = storageKeyFor(root);
    var all = loadAll();
    var saved = all[storeKey];
    var cols = ensureColgroup(table, ths.length);

    function syncFromDom() {
      var measured = measureThWidths(ths);
      applyWidths(table, cols, measured, ths);
    }

    function persistCurrent() {
      var snap = snapshotWidths(cols, ths);
      all = loadAll();
      all[storeKey] = snap;
      saveAll(all);
    }

    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        if (Array.isArray(saved) && saved.length === cols.length) {
          var ok = saved.every(function (x) {
            return typeof x === "number" && x >= MIN_W;
          });
          if (ok) {
            applyWidths(table, cols, saved, ths);
            return;
          }
        }
        syncFromDom();
      });
    });

    ths.forEach(function (th, colIndex) {
      if (skipResizeTh(th)) {
        return;
      }
      th.style.position = "relative";
      var handle = document.createElement("button");
      handle.type = "button";
      handle.className = "dg-col-resize";
      handle.title = "Drag to resize column";
      handle.setAttribute("aria-label", "Resize column");
      handle.tabIndex = -1;
      th.appendChild(handle);

      handle.addEventListener("pointerdown", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        try {
          handle.setPointerCapture(ev.pointerId);
        } catch (e) {}

        var startX = ev.clientX;
        var startW = th.getBoundingClientRect().width;

        function onMove(e2) {
          var dw = e2.clientX - startX;
          var nw = Math.max(minWidthForTh(th), Math.round(startW + dw));
          cols[colIndex].style.width = nw + "px";
          table.style.tableLayout = "fixed";
        }

        function onUp(e2) {
          handle.removeEventListener("pointermove", onMove);
          handle.removeEventListener("pointerup", onUp);
          handle.removeEventListener("pointercancel", onUp);
          try {
            handle.releasePointerCapture(e2.pointerId);
          } catch (err) {}

          persistCurrent();
        }

        handle.addEventListener("pointermove", onMove);
        handle.addEventListener("pointerup", onUp);
        handle.addEventListener("pointercancel", onUp);
      });

      handle.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
      });
    });
  }

  function initAll() {
    document.querySelectorAll("[data-grid-root]").forEach(initGrid);
  }

  /**
   * If the first init ran before layout was ready, handles may be missing. Re-run once
   * after window load (idempotent: initGrid skips roots that already have handles).
   */
  function repairMissingResizeHandles() {
    document.querySelectorAll("[data-grid-root]").forEach(function (root) {
      if (root.getAttribute("data-grid-no-resize") === "1") {
        return;
      }
      var table = root.querySelector("table.data-grid");
      if (!table) {
        return;
      }
      var thead = table.querySelector("thead");
      var headerTr = firstHeaderRow(thead);
      if (!headerTr || !headerTr.querySelector(".dg-col-resize")) {
        root._jkColResize = false;
        initGrid(root);
      }
    });
  }

  initAll();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  }
  window.addEventListener("load", repairMissingResizeHandles);
  window.initGridColumnResize = initAll;
})();
