(() => {
  let checklistItems = [];
  let savedChecklistIds = new Set();
  let activeRow = null;
  let dialog = null;
  let listEl = null;
  let filterInput = null;

  function readChecklistData() {
    const el = document.getElementById("wa-checklist-items-data");
    if (!el || !el.textContent) {
      checklistItems = [];
      return;
    }
    try {
      checklistItems = JSON.parse(el.textContent);
      if (!Array.isArray(checklistItems)) {
        checklistItems = [];
      }
    } catch {
      checklistItems = [];
    }
  }

  function readSavedChecklistIds() {
    const el = document.getElementById("wa-saved-checklist-ids-data");
    savedChecklistIds = new Set();
    if (!el || !el.textContent) {
      return;
    }
    try {
      const parsed = JSON.parse(el.textContent);
      if (Array.isArray(parsed)) {
        parsed.forEach((id) => {
          if (id != null && id !== "") {
            savedChecklistIds.add(Number(id));
          }
        });
      }
    } catch {
      savedChecklistIds = new Set();
    }
  }

  function rowChecklistId(row) {
    const hidden = row.querySelector(".wa-batch-checklist-value");
    const raw = (hidden?.value || "").trim();
    if (!raw) {
      return null;
    }
    const id = Number(raw);
    return Number.isFinite(id) ? id : null;
  }

  function usedChecklistIdsInGrid(tbody) {
    const used = new Set(savedChecklistIds);
    tbody.querySelectorAll("tr.wa-batch-row").forEach((row) => {
      const id = rowChecklistId(row);
      if (id != null) {
        used.add(id);
      }
    });
    return used;
  }

  function rowIsEmptyDraft(row) {
    const text = (row.querySelector(".wa-batch-query-text")?.value || "").trim();
    const checklistLabel = (row.querySelector(".wa-batch-checklist-display")?.value || "").trim();
    const checklistId = rowChecklistId(row);
    const hasFiles = (row.querySelector("[data-batch-row-file]")?.files?.length || 0) > 0;
    return !text && !checklistLabel && checklistId == null && !hasFiles;
  }

  function fillRowWithChecklistItem(row, item, defaultDate) {
    const dateInput = row.querySelector('input[name="batch_row_date"]');
    if (dateInput) {
      dateInput.value = defaultDate;
    }
    const typeSelect = row.querySelector('select[name="batch_row_type"]');
    if (typeSelect) {
      typeSelect.value = "query";
    }
    setRowChecklist(row, item.id, item.text || "");
    const expected = row.querySelector('select[name="batch_row_expected"]');
    if (expected) {
      expected.value = "internal";
    }
    const remarks = row.querySelector(".wa-batch-query-text");
    if (remarks) {
      remarks.value = "";
    }
    const fileInput = row.querySelector("[data-batch-row-file]");
    if (fileInput) {
      fileInput.value = "";
      refreshFileListDisplay(fileInput);
    }
  }

  function addAllChecklistLinesToForm(tbody, addBtn) {
    if (!checklistItems.length) {
      return;
    }
    const defaultDate = tbody.getAttribute("data-default-date") || "";
    const used = usedChecklistIdsInGrid(tbody);
    const pending = checklistItems.filter((item) => !used.has(Number(item.id)));
    if (!pending.length) {
      const errEl = document.getElementById("wa-batch-inline-errors");
      showInlineErrors(errEl, ["All checklist lines are already in the form or notes log."]);
      return;
    }
    clearInlineErrors(document.getElementById("wa-batch-inline-errors"));

    let template = tbody.querySelector("tr.wa-batch-row");
    if (!template) {
      return;
    }

    pending.forEach((item, index) => {
      let row;
      if (index === 0) {
        const rows = tbody.querySelectorAll("tr.wa-batch-row");
        const last = rows[rows.length - 1];
        if (last && rowIsEmptyDraft(last)) {
          row = last;
        } else {
          row = template.cloneNode(true);
          clearRow(row, defaultDate);
          bindChecklistLabelInput(row);
          tbody.appendChild(row);
        }
      } else {
        row = template.cloneNode(true);
        clearRow(row, defaultDate);
        bindChecklistLabelInput(row);
        tbody.appendChild(row);
      }
      fillRowWithChecklistItem(row, item, defaultDate);
    });
    renumberBatchRows(tbody);
    tbody.querySelectorAll(".wa-batch-checklist-display").forEach(autoSizeDisplay);
  }

  function autoSizeDisplay(ta) {
    if (!ta || !ta.classList.contains("wa-batch-checklist-display")) {
      return;
    }
    ta.style.height = "auto";
    const h = Math.min(Math.max(ta.scrollHeight, 48), 360);
    ta.style.height = `${h}px`;
  }

  function setRowChecklist(row, id, text) {
    const hidden = row.querySelector(".wa-batch-checklist-value");
    const ta = row.querySelector(".wa-batch-checklist-display");
    if (hidden) {
      hidden.value = id != null && id !== "" ? String(id) : "";
    }
    if (!ta) {
      return;
    }
    if (id != null && id !== "" && text != null && String(text).trim() !== "") {
      ta.value = String(text);
    } else if (!hidden?.value) {
      ta.value = "";
    }
    autoSizeDisplay(ta);
  }

  function bindChecklistLabelInput(row) {
    const ta = row.querySelector(".wa-batch-checklist-display");
    const hidden = row.querySelector(".wa-batch-checklist-value");
    if (!ta || ta.dataset.checklistBound === "1") {
      return;
    }
    ta.dataset.checklistBound = "1";
    ta.addEventListener("input", () => {
      if (hidden && document.activeElement === ta) {
        hidden.value = "";
      }
      autoSizeDisplay(ta);
    });
  }

  function renderDialogList(filterText) {
    if (!listEl) {
      return;
    }
    const q = (filterText || "").trim().toLowerCase();
    listEl.innerHTML = "";
    checklistItems.forEach((item) => {
      const line = `${item.text || ""}`;
      if (q && !line.toLowerCase().includes(q)) {
        return;
      }
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "wa-batch-checklist-option";
      btn.dataset.id = String(item.id);
      btn.textContent = line;
      btn.addEventListener("click", () => {
        if (!activeRow) {
          return;
        }
        setRowChecklist(activeRow, item.id, line);
        if (dialog) {
          dialog.close();
        }
      });
      listEl.appendChild(btn);
    });
    if (!listEl.children.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.style.margin = "0.35rem 0 0 0";
      empty.textContent = "No lines match your search.";
      listEl.appendChild(empty);
    }
  }

  function openDialog(row) {
    if (!dialog || !checklistItems.length) {
      return;
    }
    activeRow = row;
    if (filterInput) {
      filterInput.value = "";
    }
    renderDialogList("");
    dialog.showModal();
    filterInput?.focus();
  }

  function refreshFileListDisplay(fileInput) {
    const cell = fileInput?.closest(".wa-batch-cell-query");
    const ul = cell?.querySelector("[data-batch-file-list]");
    if (!ul) {
      return;
    }
    ul.innerHTML = "";
    const files = fileInput?.files;
    if (!files?.length) {
      return;
    }
    for (let i = 0; i < files.length; i++) {
      const li = document.createElement("li");
      li.textContent = files[i].name;
      ul.appendChild(li);
    }
  }

  function clearRow(tr, defaultDate) {
    tr.querySelectorAll("input, select, textarea").forEach((el) => {
      if (el.classList.contains("wa-batch-checklist-value")) {
        return;
      }
      if (el.type === "file") {
        el.value = "";
        refreshFileListDisplay(el);
      } else if (el.name === "batch_row_date") {
        el.value = defaultDate;
      } else if (el.name === "batch_row_type") {
        el.value = "query";
      } else if (el.name === "batch_row_expected") {
        el.selectedIndex = 0;
      } else if (el.name === "batch_row_text" || el.name === "batch_row_checklist_label") {
        el.value = "";
      }
    });
    setRowChecklist(tr, "", "");
    const btn = tr.querySelector(".wa-batch-checklist-open");
    if (btn) {
      btn.disabled = checklistItems.length === 0;
    }
  }

  function renumberBatchRows(tbody) {
    tbody.querySelectorAll("tr.wa-batch-row").forEach((tr, i) => {
      const fileInput = tr.querySelector("[data-batch-row-file]");
      if (fileInput) {
        fileInput.name = `batch_row_files_${i}`;
      }
    });
  }

  function clearInlineErrors(errEl) {
    if (!errEl) {
      return;
    }
    errEl.textContent = "";
    errEl.hidden = true;
  }

  function showInlineErrors(errEl, messages) {
    if (!errEl) {
      return;
    }
    errEl.textContent = messages.join(" ");
    errEl.hidden = false;
  }

  function postUrlForForm(form) {
    const action = (form.getAttribute("action") || "").trim();
    if (action) {
      return action;
    }
    let path = window.location.pathname || "";
    if (path && !path.endsWith("/")) {
      path += "/";
    }
    return path + (window.location.search || "");
  }

  async function saveBatchRow(tbody, form, row, saveBtn) {
    const errEl = document.getElementById("wa-batch-inline-errors");
    const rows = Array.from(tbody.querySelectorAll("tr.wa-batch-row"));
    const rowIndex = rows.indexOf(row);
    if (rowIndex < 0) {
      return;
    }
    clearInlineErrors(errEl);
    saveBtn.disabled = true;
    try {
      const fd = new FormData(form);
      fd.delete("action");
      fd.append("action", "save_query_batch_row");
      fd.set("batch_row_save_index", String(rowIndex));
      const url = postUrlForForm(form);
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
        let msgs = [];
        if (Array.isArray(data.errors) && data.errors.length) {
          msgs = data.errors;
        } else if (typeof data.error === "string" && data.error.trim()) {
          msgs = [data.error.trim()];
        } else if (!resp.ok) {
          msgs = [`Could not save this line (${resp.status}).`];
        } else {
          msgs = ["Could not save this line."];
        }
        showInlineErrors(errEl, msgs);
        return;
      }
      window.location.reload();
    } finally {
      saveBtn.disabled = false;
    }
  }

  function init() {
    readChecklistData();
    readSavedChecklistIds();
    const tbody = document.getElementById("wa-batch-rows");
    const addBtn = document.getElementById("wa-batch-add-row");
    const addAllChecklistBtn = document.getElementById("wa-batch-add-all-checklist");
    const form = document.getElementById("wa-batch-form");
    dialog = document.getElementById("wa-batch-checklist-dialog");
    if (!tbody || !addBtn || !form) {
      return;
    }

    listEl = dialog?.querySelector(".wa-batch-checklist-dialog-list");
    filterInput = document.getElementById("wa-batch-checklist-filter");

    if (dialog) {
      dialog.querySelectorAll("[data-wa-checklist-close]").forEach((b) => {
        b.addEventListener("click", () => dialog.close());
      });
      dialog.addEventListener("click", (e) => {
        if (e.target === dialog) {
          dialog.close();
        }
      });
    }

    if (filterInput) {
      filterInput.addEventListener("input", () => {
        renderDialogList(filterInput.value);
      });
    }

    tbody.addEventListener("change", (e) => {
      const t = e.target;
      if (t && t.matches && t.matches("input[data-batch-row-file]")) {
        refreshFileListDisplay(t);
      }
    });

    tbody.addEventListener("click", (e) => {
      const saveBtn = e.target.closest(".wa-batch-save-row");
      if (saveBtn) {
        const row = saveBtn.closest("tr.wa-batch-row");
        if (row && tbody.contains(row)) {
          void saveBatchRow(tbody, form, row, saveBtn);
        }
        return;
      }

      const removeBtn = e.target.closest(".wa-batch-remove-row");
      if (removeBtn) {
        const row = removeBtn.closest("tr.wa-batch-row");
        if (!row || !tbody.contains(row)) {
          return;
        }
        const defaultDate = tbody.getAttribute("data-default-date") || "";
        const rows = tbody.querySelectorAll("tr.wa-batch-row");
        if (rows.length > 1) {
          if (dialog && dialog.open && activeRow === row) {
            dialog.close();
            activeRow = null;
          }
          row.remove();
        } else {
          clearRow(row, defaultDate);
        }
        renumberBatchRows(tbody);
        return;
      }

      const opener = e.target.closest(".wa-batch-checklist-open");
      if (!opener || opener.disabled) {
        return;
      }
      const row = opener.closest("tr.wa-batch-row");
      if (row) {
        openDialog(row);
      }
    });

    addBtn.addEventListener("click", () => {
      const template = tbody.querySelector("tr.wa-batch-row");
      if (!template) {
        return;
      }
      const tr = template.cloneNode(true);
      clearRow(tr, tbody.getAttribute("data-default-date") || "");
      bindChecklistLabelInput(tr);
      tbody.appendChild(tr);
      renumberBatchRows(tbody);
    });

    if (addAllChecklistBtn) {
      addAllChecklistBtn.addEventListener("click", () => {
        addAllChecklistLinesToForm(tbody, addBtn);
      });
    }

    tbody.querySelectorAll("tr.wa-batch-row").forEach(bindChecklistLabelInput);
    tbody.querySelectorAll(".wa-batch-checklist-display").forEach(autoSizeDisplay);
    tbody.querySelectorAll("[data-batch-row-file]").forEach(refreshFileListDisplay);
    renumberBatchRows(tbody);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
