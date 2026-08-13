(function () {
  var dialog = document.getElementById("timer-start-dialog");
  var form = document.getElementById("timer-start-dialog-form");
  if (!dialog || !form) return;

  var taskTa = document.getElementById("timer-start-dialog-task");
  var recentSel = document.getElementById("timer-start-dialog-recent");
  var nextInput = document.getElementById("timer-start-dialog-next");
  var cancelBtn = document.getElementById("timer-start-dialog-cancel");
  var baseUrl = window.TIMER_RECENT_TASKS_URL || "";

  function buildRecentUrl(ds) {
    var p = new URLSearchParams();
    if (ds.engagement) p.set("engagement", ds.engagement);
    if (ds.division) p.set("division", ds.division);
    if (ds.engagementWorkArea) p.set("engagement_work_area", ds.engagementWorkArea);
    if (ds.divisionWorkArea) p.set("division_work_area", ds.divisionWorkArea);
    var q = p.toString();
    return q ? baseUrl + "?" + q : baseUrl;
  }

  function resetRecentSelect() {
    recentSel.innerHTML = "";
    var opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = "Choose a previous task…";
    recentSel.appendChild(opt0);
    recentSel.selectedIndex = 0;
  }

  document.querySelectorAll(".timer-start-opener").forEach(function (btn) {
    btn.addEventListener("click", function () {
      form.action = btn.getAttribute("data-start-url") || "";
      nextInput.value = btn.getAttribute("data-next") || "";
      taskTa.value = "";
      resetRecentSelect();
      dialog.showModal();
      var url = buildRecentUrl(btn.dataset);
      if (!baseUrl || !url || url.indexOf("?") === -1) return;
      fetch(url, { credentials: "same-origin" })
        .then(function (r) {
          return r.ok ? r.json() : Promise.reject();
        })
        .then(function (data) {
          (data.tasks || []).forEach(function (t) {
            var o = document.createElement("option");
            o.value = t;
            o.textContent = t.length > 80 ? t.slice(0, 77) + "…" : t;
            recentSel.appendChild(o);
          });
        })
        .catch(function () {});
    });
  });

  recentSel.addEventListener("change", function () {
    if (this.value) taskTa.value = this.value;
    this.selectedIndex = 0;
  });

  cancelBtn.addEventListener("click", function () {
    dialog.close();
  });
  dialog.addEventListener("click", function (e) {
    if (e.target === dialog) dialog.close();
  });
})();
