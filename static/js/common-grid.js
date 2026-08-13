/**
 * Data grids: column sort + optional client-side row filter for [data-grid-root] panels.
 *
 * Markup:
 *   - [data-grid-root] wraps the first <table> inside it.
 *   - Body: tr[data-grid-row]; optional tr[data-grid-empty], [data-grid-no-results], [data-grid-count]
 *   - Header: thead > first tr (element children only) > th
 *
 * Sort: click the <th>. Skipped for .col-actions, .col-select, .col-attachments, .col-team-mail.
 * Search: optional input [data-grid-search] filters rows by case-insensitive substring match
 * across all cell text for that grid.
 */
(function () {
  "use strict";

  function sortStorageKey(root) {
    const id = (root.getAttribute("data-grid-id") || "").trim();
    if (!id) {
      return null;
    }
    return `jkErp.gridSort.v1:${id}`;
  }

  function firstTrInThead(thead) {
    if (!thead) {
      return null;
    }
    for (let i = 0; i < thead.children.length; i++) {
      const el = thead.children[i];
      if (el.tagName === "TR") {
        return el;
      }
    }
    return thead.querySelector("tr");
  }

  function skipSortHeader(th) {
    return (
      th.classList.contains("col-actions") ||
      th.classList.contains("col-engagement-reports") ||
      th.classList.contains("col-select") ||
      th.classList.contains("col-attachments") ||
      th.classList.contains("col-team-mail")
    );
  }

  function interactiveTarget(event) {
    const t = event.target;
    if (!t || typeof t.closest !== "function") {
      return null;
    }
    return t.closest("a, button, input, select, textarea, label");
  }

  function cellText(row, colIndex) {
    const cell = row.children[colIndex];
    if (!cell) {
      return "";
    }
    const sortVal = cell.getAttribute("data-sort-value");
    if (sortVal != null && String(sortVal).trim() !== "") {
      return String(sortVal).trim();
    }
    return cell.textContent.trim();
  }

  function parseSortableValue(raw) {
    const s = (raw || "").trim();
    if (!s) {
      return { kind: "empty", v: "" };
    }
    const low = s.toLowerCase();
    if (low === "yes" || low === "no") {
      return { kind: "bool", v: low === "yes" ? 1 : 0 };
    }
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
      return { kind: "date", v: s };
    }
    if (/^\d{2}-\d{2}-\d{4}$/.test(s)) {
      const [d, m, y] = s.split("-");
      return { kind: "date", v: `${y}-${m}-${d}` };
    }
    if (/^\d+(\.\d+)?$/.test(s)) {
      return { kind: "num", v: Number(s) };
    }
    return { kind: "text", v: s };
  }

  class DataGridPanel {
    constructor(root) {
      this.root = root;
      this.table = root.querySelector("table");
      this.tbody = this.table ? this.table.querySelector("tbody") : null;
      this.countEl = root.querySelector("[data-grid-count]");
      this.emptyRow = root.querySelector("[data-grid-empty]");
      this.noResultsEl = root.querySelector("[data-grid-no-results]");
      this.searchInput = root.querySelector("[data-grid-search]");

      const thead = this.table ? this.table.querySelector("thead") : null;
      const headerTr = firstTrInThead(thead);
      this.thCells = headerTr ? Array.from(headerTr.querySelectorAll("th")) : [];
      this.dataRows = this.tbody
        ? Array.from(this.tbody.querySelectorAll("tr[data-grid-row]"))
        : [];

      this.sortCol = -1;
      this.sortDir = "asc";

      this._ok = false;
      if (!this.table || !this.tbody) {
        return;
      }

      this._wireSort();
      this._wireSearch();
      this._applyInitialSortFromRoot();
      this._loadSavedSort();
      this._render();
      this._ok = true;
    }

    get ready() {
      return this._ok;
    }

    _normalizeSearchQuery(raw) {
      return String(raw || "").trim().toLowerCase();
    }

    _rowHaystack(row) {
      const cells = row.children;
      const parts = [];
      for (let i = 0; i < cells.length; i++) {
        parts.push((cells[i].textContent || "").trim());
      }
      return parts.join(" ").trim().toLowerCase();
    }

    _rowsMatchingSearch(queryNorm) {
      if (!queryNorm) {
        return this.dataRows.slice();
      }
      return this.dataRows.filter((row) =>
        this._rowHaystack(row).includes(queryNorm)
      );
    }

    _wireSearch() {
      if (!this.searchInput || typeof this.searchInput.addEventListener !== "function") {
        return;
      }
      this.searchInput.addEventListener("input", () => {
        this._render();
      });
    }

    _wireSort() {
      this.thCells.forEach((th, colIndex) => {
        if (skipSortHeader(th)) {
          return;
        }
        th.classList.add("dg-sortable");
        th.tabIndex = 0;

        th.addEventListener("click", (ev) => {
          if (interactiveTarget(ev)) {
            return;
          }
          this._applySortClick(colIndex);
        });
        th.addEventListener("keydown", (ev) => {
          if (ev.key !== "Enter" && ev.key !== " ") {
            return;
          }
          ev.preventDefault();
          this._applySortClick(colIndex);
        });
      });
    }

    _applySortClick(colIndex) {
      if (this.sortCol === colIndex) {
        this.sortDir = this.sortDir === "asc" ? "desc" : "asc";
      } else {
        this.sortCol = colIndex;
        this.sortDir = "asc";
      }
      this._saveSort();
      this._render();
    }

    _applyInitialSortFromRoot() {
      if (this.root.getAttribute("data-grid-persist-sort") === "0") {
        return;
      }
      const colRaw = this.root.getAttribute("data-default-sort-col");
      if (colRaw == null || colRaw === "") {
        return;
      }
      const idx = Number(colRaw);
      if (!Number.isInteger(idx) || idx < 0 || idx >= this.thCells.length) {
        return;
      }
      if (skipSortHeader(this.thCells[idx])) {
        return;
      }
      const dirRaw = (this.root.getAttribute("data-default-sort-dir") || "asc").toLowerCase();
      this.sortCol = idx;
      this.sortDir = dirRaw === "desc" ? "desc" : "asc";
    }

    _loadSavedSort() {
      if (this.root.getAttribute("data-grid-persist-sort") === "0") {
        return;
      }
      const key = sortStorageKey(this.root);
      if (!key) {
        return;
      }
      try {
        const raw = localStorage.getItem(key);
        if (!raw) {
          return;
        }
        const parsed = JSON.parse(raw);
        const idx = Number(parsed.col);
        const dir = parsed.dir;
        if (!Number.isInteger(idx) || idx < 0 || idx >= this.thCells.length) {
          return;
        }
        if (skipSortHeader(this.thCells[idx])) {
          return;
        }
        this.sortCol = idx;
        this.sortDir = dir === "desc" ? "desc" : "asc";
      } catch (_err) {
        /* ignore corrupt storage */
      }
    }

    _saveSort() {
      if (this.root.getAttribute("data-grid-persist-sort") === "0") {
        return;
      }
      const key = sortStorageKey(this.root);
      if (!key || this.sortCol < 0) {
        return;
      }
      try {
        localStorage.setItem(
          key,
          JSON.stringify({ col: this.sortCol, dir: this.sortDir })
        );
      } catch (_err) {
        /* ignore quota / private mode */
      }
    }

    _sortRows(rows) {
      if (this.sortCol < 0 || this.sortCol >= this.thCells.length) {
        return rows;
      }
      const mult = this.sortDir === "asc" ? 1 : -1;
      const c = this.sortCol;
      return rows.slice().sort((r1, r2) => {
        const a = parseSortableValue(cellText(r1, c));
        const b = parseSortableValue(cellText(r2, c));
        if (a.kind !== b.kind) {
          return (
            String(a.v).localeCompare(String(b.v), undefined, {
              numeric: true,
              sensitivity: "base",
            }) * mult
          );
        }
        if (a.kind === "num" || a.kind === "bool") {
          return (a.v - b.v) * mult;
        }
        return (
          String(a.v).localeCompare(String(b.v), undefined, {
            numeric: true,
            sensitivity: "base",
          }) * mult
        );
      });
    }

    _updateSortIndicators() {
      this.thCells.forEach((th, i) => {
        if (!th.classList.contains("dg-sortable")) {
          return;
        }
        th.classList.remove("dg-sorted-asc", "dg-sorted-desc");
        th.setAttribute("aria-sort", "none");
        if (i === this.sortCol) {
          th.classList.add(this.sortDir === "asc" ? "dg-sorted-asc" : "dg-sorted-desc");
          th.setAttribute(
            "aria-sort",
            this.sortDir === "asc" ? "ascending" : "descending"
          );
        }
      });
    }

    _render() {
      const queryNorm =
        this.searchInput && this.searchInput.value != null
          ? this._normalizeSearchQuery(this.searchInput.value)
          : "";
      const matched = this._rowsMatchingSearch(queryNorm);
      const ordered = this._sortRows(matched);

      this.dataRows.forEach((tr) => {
        tr.hidden = true;
      });
      ordered.forEach((tr) => {
        tr.hidden = false;
        this.tbody.appendChild(tr);
      });

      const hasRows = this.dataRows.length > 0;
      const visible = ordered.length;

      if (this.emptyRow) {
        this.emptyRow.hidden = hasRows || visible > 0;
      }
      if (this.noResultsEl) {
        this.noResultsEl.hidden = !(hasRows && queryNorm && visible === 0);
      }
      if (this.countEl) {
        this.countEl.textContent = hasRows
          ? `${visible} of ${this.dataRows.length} record(s)`
          : "0 records";
      }

      this._updateSortIndicators();
    }
  }

  function initCommonDataGrids() {
    document.querySelectorAll("[data-grid-root]").forEach((root) => {
      if (root._commonDataGrid) {
        return;
      }
      try {
        const grid = new DataGridPanel(root);
        if (grid.ready) {
          root._commonDataGrid = grid;
        }
      } catch (err) {
        console.error("[jk-erp] data-grid init failed", root, err);
      }
    });
  }

  initCommonDataGrids();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initCommonDataGrids);
  }
  window.initCommonDataGrids = initCommonDataGrids;
})();
