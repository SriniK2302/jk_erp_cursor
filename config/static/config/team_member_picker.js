/**
 * Team member picker: dynamic search (server) + checkbox list, single selection.
 * Expects .tm-picker with data-search-url, optional data-for-user, data-initial-*.
 */
(function () {
  "use strict";

  var DEBOUNCE_MS = 300;

  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments;
      clearTimeout(t);
      t = setTimeout(function () {
        fn.apply(null, args);
      }, ms);
    };
  }

  function buildUrl(base, q, forUser) {
    var u = new URL(base, window.location.origin);
    u.searchParams.set("q", q);
    if (forUser) {
      u.searchParams.set("for_user", forUser);
    }
    return u.toString();
  }

  function renderResults(container, items, selected, multiple, emptyText, syncSelected) {
    container.innerHTML = "";
    if (!items.length) {
      container.innerHTML = '<p class="help">' + emptyText + "</p>";
      return;
    }
    items.forEach(function (row) {
      var id = String(row.id);
      var wrap = document.createElement("div");
      wrap.className = "tm-row";
      wrap.setAttribute("role", "listitem");
      var lab = document.createElement("label");
      lab.className = "tm-label";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.name = "_tm_pick";
      cb.value = id;
      cb.setAttribute("data-label", row.label);
      if (selected.has(id)) {
        cb.checked = true;
      }
      cb.addEventListener("change", function () {
        if (multiple) {
          if (cb.checked) {
            selected.add(id);
          } else {
            selected.delete(id);
          }
        } else if (cb.checked) {
          selected.clear();
          selected.add(id);
          container.querySelectorAll('input[type="checkbox"]').forEach(function (x) {
            if (x !== cb) {
              x.checked = false;
            }
          });
        } else {
          selected.delete(id);
        }
        syncSelected();
      });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + row.label));
      wrap.appendChild(lab);
      container.appendChild(wrap);
    });
  }

  function initPicker(root) {
    if (!root || root.dataset.tmInit) {
      return;
    }
    root.dataset.tmInit = "1";
    var url = root.getAttribute("data-search-url");
    if (!url) {
      return;
    }
    var forUser = root.getAttribute("data-for-user") || "";
    var fieldName = root.getAttribute("data-field-name") || "";
    var multiple = (root.getAttribute("data-multiple") || "0") === "1";
    var hidden = root.querySelector(".tm-hidden-single");
    var hiddenBucket = root.querySelector(".tm-hidden-bucket");
    var search = root.querySelector(".tm-search");
    var results = root.querySelector(".tm-results");
    var clearBtn = root.querySelector(".tm-clear");
    var emptyText = root.getAttribute("data-empty-text") || "No matches found.";
    var errorText = root.getAttribute("data-error-text") || "Could not load results.";
    if (!search || !results || (!multiple && !hidden) || (multiple && !hiddenBucket)) {
      return;
    }
    var selected = new Set();
    if (multiple) {
      var initialIds = (root.getAttribute("data-initial-ids") || "")
        .split(",")
        .map(function (x) {
          return x.trim();
        })
        .filter(Boolean);
      initialIds.forEach(function (id) {
        selected.add(id);
      });
    } else {
      var cur = (hidden && hidden.value ? String(hidden.value) : "").trim();
      if (!cur) {
        cur = (root.getAttribute("data-initial-id") || "").trim();
      }
      if (cur) {
        selected.add(cur);
      }
    }

    function syncSelected() {
      if (multiple) {
        hiddenBucket.innerHTML = "";
        Array.from(selected).forEach(function (id) {
          var input = document.createElement("input");
          input.type = "hidden";
          input.name = fieldName;
          input.value = id;
          hiddenBucket.appendChild(input);
        });
      } else if (hidden) {
        hidden.value = selected.size ? Array.from(selected)[0] : "";
      }
    }
    syncSelected();

    function fetchAndRender(q) {
      var reqUrl = buildUrl(url, q, forUser);
      fetch(reqUrl, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) {
          if (!r.ok) {
            throw new Error("search failed");
          }
          return r.json();
        })
        .then(function (data) {
          renderResults(results, data, selected, multiple, emptyText, syncSelected);
        })
        .catch(function () {
          results.innerHTML = '<p class="errornote">' + errorText + "</p>";
        });
    }

    var runSearch = debounce(function () {
      fetchAndRender(search.value.trim());
    }, DEBOUNCE_MS);

    search.addEventListener("input", runSearch);
    search.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        ev.preventDefault();
        fetchAndRender(search.value.trim());
      }
    });

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        selected.clear();
        syncSelected();
        search.value = "";
        results.querySelectorAll('input[type="checkbox"]').forEach(function (x) {
          x.checked = false;
        });
        fetchAndRender("");
      });
    }

    fetchAndRender("");
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".tm-picker").forEach(initPicker);
  });
})();
