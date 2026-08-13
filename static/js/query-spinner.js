(() => {
  function initQuerySpinner(container) {
    const indexInput = container.querySelector("[data-prev-query-index]");
    const totalLabel = container.querySelector("[data-prev-query-total]");
    const applyBtn = container.querySelector("[data-prev-query-apply]");
    const upBtn = container.querySelector("[data-prev-query-up]");
    const downBtn = container.querySelector("[data-prev-query-down]");
    const jsonId = container.getAttribute("data-prev-query-json-id");
    const dataEl = jsonId ? document.getElementById(jsonId) : null;
    const subjectInput = document.getElementById("query-subject");
    const amountInput = document.getElementById("query-amount");
    const amountUnitInput = document.getElementById("query-amount-unit");
    const expectedInput = document.getElementById("query-expected-from");
    const textInput = document.getElementById("query-text");
    const queryPkInput = document.getElementById("query-current-pk");
    const filesList = document.getElementById("current-query-files");
    const filesEmpty = document.getElementById("current-query-files-empty");
    const formCsrf = document.querySelector(
      "[data-query-form] input[name='csrfmiddlewaretoken']"
    );
    const rootForm = document.querySelector("[data-query-form]");
    if (
      !indexInput ||
      !totalLabel ||
      !applyBtn ||
      !dataEl ||
      !subjectInput ||
      !amountInput ||
      !amountUnitInput ||
      !expectedInput ||
      !textInput ||
      !queryPkInput
    ) {
      return;
    }
    let rows = [];
    try {
      rows = JSON.parse(dataEl.textContent || "[]");
    } catch (_err) {
      rows = [];
    }
    if (!Array.isArray(rows) || !rows.length) {
      return;
    }

    indexInput.min = "1";
    indexInput.max = String(rows.length);
    indexInput.value = "1";
    totalLabel.textContent = String(rows.length);

    function clampIndex(rawValue) {
      const value = Number(rawValue);
      if (!Number.isFinite(value)) {
        return 1;
      }
      return Math.min(rows.length, Math.max(1, Math.floor(value)));
    }

    function applyAt(index) {
      const row = rows[index - 1];
      if (!row) {
        return;
      }
      subjectInput.value = row.subject || "";
      amountInput.value = row.amount || "";
      amountUnitInput.value = row.amount_unit || "lakhs";
      expectedInput.value = row.response_expected_from || "internal";
      textInput.value = row.query_text || "";
      queryPkInput.value = row.id ? String(row.id) : "";
      if (filesList && filesEmpty) {
        filesList.innerHTML = "";
        const attachments = Array.isArray(row.attachments) ? row.attachments : [];
        if (!attachments.length) {
          filesEmpty.textContent = "None";
        } else {
          filesEmpty.textContent = "";
          attachments.forEach((att) => {
            const li = document.createElement("li");
            li.className = "doc-attachment-line doc-attachment-line-page";
            const main = document.createElement("div");
            main.className = "doc-attachment-line-main";
            const a = document.createElement("a");
            a.href = att.url || "#";
            a.textContent = att.name || "file";
            main.appendChild(a);
            if (att.id && queryPkInput.value && formCsrf && rootForm) {
              const delBtn = document.createElement("button");
              delBtn.type = "button";
              delBtn.className = "button button-secondary button-compact";
              delBtn.style.marginLeft = "0.5rem";
              delBtn.textContent = "Del";
              delBtn.addEventListener("click", () => {
                if (!window.confirm("Delete this file?")) return;
                const postForm = document.createElement("form");
                postForm.method = "post";
                postForm.action = window.location.href;
                const csrfInput = document.createElement("input");
                csrfInput.type = "hidden";
                csrfInput.name = "csrfmiddlewaretoken";
                csrfInput.value = formCsrf.value;
                const actionInput = document.createElement("input");
                actionInput.type = "hidden";
                actionInput.name = "action";
                actionInput.value = "delete_query_attachment";
                const qInput = document.createElement("input");
                qInput.type = "hidden";
                qInput.name = "query_pk";
                qInput.value = queryPkInput.value;
                const attInput = document.createElement("input");
                attInput.type = "hidden";
                attInput.name = "attachment_pk";
                attInput.value = String(att.id);
                postForm.appendChild(csrfInput);
                postForm.appendChild(actionInput);
                postForm.appendChild(qInput);
                postForm.appendChild(attInput);
                document.body.appendChild(postForm);
                postForm.submit();
              });
              main.appendChild(delBtn);
            }
            li.appendChild(main);
            filesList.appendChild(li);
          });
        }
      }
      textInput.focus();
    }

    applyBtn.addEventListener("click", () => {
      const idx = clampIndex(indexInput.value);
      indexInput.value = String(idx);
      applyAt(idx);
    });

    if (upBtn) {
      upBtn.addEventListener("click", () => {
        const idx = clampIndex(indexInput.value) - 1;
        const next = idx < 1 ? rows.length : idx;
        indexInput.value = String(next);
        applyAt(next);
      });
    }

    if (downBtn) {
      downBtn.addEventListener("click", () => {
        const idx = clampIndex(indexInput.value) + 1;
        const next = idx > rows.length ? 1 : idx;
        indexInput.value = String(next);
        applyAt(next);
      });
    }

    indexInput.addEventListener("change", () => {
      const idx = clampIndex(indexInput.value);
      indexInput.value = String(idx);
      applyAt(idx);
    });

    // On open, preload the latest previous query into the form.
    applyAt(1);
  }

  function initAll() {
    document
      .querySelectorAll("[data-previous-query-spinner]")
      .forEach((container) => initQuerySpinner(container));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
