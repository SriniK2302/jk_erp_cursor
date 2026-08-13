(function () {
  function deriveFyDates(fyNoRaw) {
    const fyNo = (fyNoRaw || "").trim().toUpperCase().slice(0, 4);
    if (!/^FY\d{2}$/.test(fyNo)) {
      return null;
    }

    const endYear = 2000 + Number.parseInt(fyNo.slice(2), 10);
    const startYear = endYear - 1;
    return {
      fyNo,
      startDate: `${startYear}-04-01`,
      endDate: `${endYear}-03-31`,
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    const fyNoInput = document.getElementById("id_fy_no");
    const startDateInput = document.getElementById("id_start_date");
    const endDateInput = document.getElementById("id_end_date");

    if (!fyNoInput || !startDateInput || !endDateInput) {
      return;
    }

    function syncDates() {
      const derived = deriveFyDates(fyNoInput.value);
      if (!derived) {
        return;
      }
      fyNoInput.value = derived.fyNo;
      startDateInput.value = derived.startDate;
      endDateInput.value = derived.endDate;
    }

    fyNoInput.addEventListener("input", syncDates);
    fyNoInput.addEventListener("blur", syncDates);
    syncDates();
  });
})();
