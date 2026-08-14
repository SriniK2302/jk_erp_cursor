/**
 * Close <details> dropdown menus automatically.
 *
 * These menus stay open by default until the summary is clicked again.
 * This closes them when:
 *   - a link/button inside the menu is chosen
 *   - the user clicks anywhere outside the menu
 *   - the user presses Escape
 *   - another dropdown on the page is opened
 */
(function () {
  "use strict";

  var SELECTOR = "details.eng-dropdown";

  function closeAll(except) {
    document.querySelectorAll(SELECTOR + "[open]").forEach(function (d) {
      if (d !== except) {
        d.open = false;
      }
    });
  }

  // Choosing an item closes the menu.
  document.addEventListener("click", function (event) {
    var link = event.target.closest(SELECTOR + " .eng-dropdown__panel a, " +
                                    SELECTOR + " .eng-dropdown__panel button");
    if (link) {
      var owner = link.closest(SELECTOR);
      if (owner) {
        owner.open = false;
      }
      return;
    }

    // Clicking outside any dropdown closes them all.
    if (!event.target.closest(SELECTOR)) {
      closeAll(null);
    }
  });

  // Opening one dropdown closes the others.
  document.addEventListener("toggle", function (event) {
    var d = event.target;
    if (d.matches && d.matches(SELECTOR) && d.open) {
      closeAll(d);
    }
  }, true);

  // Escape closes any open dropdown.
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      closeAll(null);
    }
  });
})();
