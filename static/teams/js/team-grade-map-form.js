(function () {
  async function fetchDefaults(defaultsUrl, teamMemberId, periodId) {
    const url = new URL(defaultsUrl, window.location.origin);
    url.searchParams.set("team_member", teamMemberId);
    if (periodId) {
      url.searchParams.set("period_id", periodId);
    }

    const response = await fetch(url.toString(), {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    if (!response.ok) {
      throw new Error("Failed to fetch defaults");
    }
    return response.json();
  }

  function setToDateLocked(toDateInput, locked, value) {
    if (locked) {
      if (value) {
        toDateInput.value = value;
      }
      toDateInput.readOnly = true;
      toDateInput.setAttribute("aria-readonly", "true");
      return;
    }
    toDateInput.readOnly = false;
    toDateInput.disabled = false;
    toDateInput.removeAttribute("readonly");
    toDateInput.removeAttribute("aria-readonly");
  }

  document.addEventListener("DOMContentLoaded", function () {
    const form = document.querySelector("[data-grade-map-form]");
    const memberSelect = document.getElementById("id_team_member");
    const fromDateInput = document.getElementById("id_from_date");
    const toDateInput = document.getElementById("id_to_date");

    if (!form || !memberSelect || !fromDateInput || !toDateInput) {
      return;
    }

    const defaultsUrl = form.dataset.defaultsUrl;
    const isEdit = form.dataset.isEdit === "true";
    const periodId = form.dataset.periodId || "";
    let lastRequestId = 0;
    let toDateTouched = Boolean(toDateInput.value);

    function markToDateTouched() {
      toDateTouched = true;
    }

    toDateInput.addEventListener("input", markToDateTouched);
    toDateInput.addEventListener("change", markToDateTouched);

    async function applyDefaults(resetToDate) {
      const teamMemberId = memberSelect.value;
      if (!teamMemberId) {
        return;
      }

      const requestId = ++lastRequestId;
      try {
        const payload = await fetchDefaults(
          defaultsUrl,
          teamMemberId,
          isEdit ? periodId : ""
        );
        if (requestId !== lastRequestId) {
          return;
        }

        if (!isEdit && payload.from_date) {
          fromDateInput.value = payload.from_date;
        }

        if (payload.is_to_date_locked) {
          setToDateLocked(toDateInput, true, payload.to_date);
          return;
        }

        setToDateLocked(toDateInput, false);
        if (!isEdit && (resetToDate || !toDateTouched)) {
          toDateInput.value = payload.to_date || "";
        }
      } catch (_error) {
        setToDateLocked(toDateInput, false);
      }
    }

    memberSelect.addEventListener("change", function () {
      toDateTouched = false;
      applyDefaults(true);
    });
    applyDefaults(false);
  });
})();
