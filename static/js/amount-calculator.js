(() => {
  function setMessage(messageEl, text) {
    if (messageEl) {
      messageEl.textContent = text || "";
    }
  }

  function evaluateExpression(text) {
    if (!text) {
      throw new Error("Enter a formula.");
    }
    if (!/^[0-9+\-*/().\s]+$/.test(text)) {
      throw new Error("Only numbers and + - * / ( ) are allowed.");
    }
    const value = Function('"use strict"; return (' + text + ');')();
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new Error("Invalid result.");
    }
    return Math.round(value * 100) / 100;
  }

  function bindCalculator(container) {
    const amountInput = container.querySelector("[data-amount-target]");
    const exprInput = container.querySelector("[data-amount-calc-input]");
    const applyBtn = container.querySelector("[data-amount-calc-apply]");
    const clearBtn = container.querySelector("[data-amount-calc-clear]");
    const messageEl = container.querySelector("[data-amount-calc-message]");
    const detailsEl = container.querySelector("details");
    if (!amountInput || !exprInput || !applyBtn || !clearBtn) {
      return;
    }

    applyBtn.addEventListener("click", () => {
      try {
        const result = evaluateExpression(exprInput.value.trim());
        amountInput.value = result.toFixed(2);
        setMessage(messageEl, `Applied: ${amountInput.value}`);
        amountInput.dispatchEvent(new Event("change", { bubbles: true }));
        amountInput.focus();
        if (detailsEl) {
          detailsEl.open = false;
        }
      } catch (err) {
        setMessage(messageEl, err.message || "Invalid formula.");
      }
    });

    clearBtn.addEventListener("click", () => {
      exprInput.value = "";
      setMessage(messageEl, "");
      exprInput.focus();
    });

    if (detailsEl) {
      // Close calculator when user clicks anywhere outside its container.
      document.addEventListener("click", (event) => {
        if (!detailsEl.open) {
          return;
        }
        if (!container.contains(event.target)) {
          detailsEl.open = false;
        }
      });

      // Close on Escape for keyboard-friendly dismiss.
      detailsEl.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          detailsEl.open = false;
        }
      });
    }
  }

  function initAmountCalculators() {
    document
      .querySelectorAll("[data-amount-calc]")
      .forEach((container) => bindCalculator(container));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAmountCalculators);
  } else {
    initAmountCalculators();
  }
})();
