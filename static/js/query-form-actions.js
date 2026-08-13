(() => {
  function clearQueryForm(form) {
    const subject = form.querySelector("#query-subject");
    const amount = form.querySelector("#query-amount");
    const amountUnit = form.querySelector("#query-amount-unit");
    const expectedFrom = form.querySelector("#query-expected-from");
    const details = form.querySelector("#query-text");
    const attachments = form.querySelector("#query-attachments");
    const spinnerIndex = form.querySelector("#prev-query-index");
    const currentPk = form.querySelector("#query-current-pk");
    const actionInput = form.querySelector("#query-form-action");

    if (subject) subject.value = "";
    if (amount) amount.value = "";
    if (amountUnit) amountUnit.value = "lakhs";
    if (expectedFrom) expectedFrom.value = "internal";
    if (details) details.value = "";
    if (attachments) attachments.value = "";
    if (spinnerIndex) spinnerIndex.value = "";
    if (currentPk) currentPk.value = "";
    if (actionInput) actionInput.value = "save_query";
    if (subject) subject.focus();
  }

  function init() {
    const form = document.querySelector("[data-query-form]");
    const addBtn = document.querySelector("[data-query-add-clear]");
    if (!form || !addBtn) return;
    addBtn.addEventListener("click", () => clearQueryForm(form));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
