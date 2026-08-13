(function () {
  function debounce(fn, ms) {
    let t;
    return function () {
      const args = arguments;
      clearTimeout(t);
      t = setTimeout(function () {
        fn.apply(null, args);
      }, ms);
    };
  }

  document.addEventListener("DOMContentLoaded", function () {
    const root = document.querySelector("[data-client-nav]");
    if (!root) {
      return;
    }

    const searchUrl = root.getAttribute("data-search-url");
    const searchMode = root.getAttribute("data-search-mode") || "edit";
    const input = document.getElementById("client_nav_search_input");
    const list = document.getElementById("client_nav_results");
    if (!searchUrl || !input || !list) {
      return;
    }

    function closeResults() {
      list.innerHTML = "";
      list.hidden = true;
      input.setAttribute("aria-expanded", "false");
    }

    function renderResults(items) {
      list.innerHTML = "";
      if (!items.length) {
        list.hidden = true;
        input.setAttribute("aria-expanded", "false");
        return;
      }
      items.forEach(function (row) {
        const li = document.createElement("li");
        li.setAttribute("role", "option");
        const a = document.createElement("a");
        a.href = row.href;
        a.textContent = row.text;
        a.className = "client-nav-results__link";
        li.appendChild(a);
        list.appendChild(li);
      });
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }

    const runSearch = debounce(function () {
      const q = (input.value || "").trim();
      if (q.length < 1) {
        closeResults();
        return;
      }
      const url =
        searchUrl +
        "?q=" +
        encodeURIComponent(q) +
        "&mode=" +
        encodeURIComponent(searchMode);
      fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          renderResults(data.results || []);
        })
        .catch(function () {
          closeResults();
        });
    }, 280);

    input.addEventListener("input", runSearch);
    input.addEventListener("focus", function () {
      if ((input.value || "").trim().length >= 1) {
        runSearch();
      }
    });

    document.addEventListener("click", function (ev) {
      if (!root.contains(ev.target)) {
        closeResults();
      }
    });

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") {
        closeResults();
      }
    });
  });
})();
