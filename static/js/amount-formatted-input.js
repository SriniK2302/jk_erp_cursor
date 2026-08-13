/**
 * Thousand-separated amount input with amount in words (Indian rupees, whole rupees).
 * Markup: input[data-amount-formatted] and optional [data-amount-words] sibling.
 */
(function () {
  "use strict";

  const ONES = [
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
  ];
  const TENS = [
    "",
    "",
    "Twenty",
    "Thirty",
    "Forty",
    "Fifty",
    "Sixty",
    "Seventy",
    "Eighty",
    "Ninety",
  ];

  function belowThousand(n) {
    if (n <= 0) {
      return "";
    }
    if (n < 20) {
      return ONES[n];
    }
    if (n < 100) {
      const t = Math.floor(n / 10);
      const r = n % 10;
      const base = TENS[t];
      return r ? `${base} ${ONES[r]}`.trim() : base;
    }
    const h = Math.floor(n / 100);
    const r = n % 100;
    const head = `${ONES[h]} Hundred`;
    if (r === 0) {
      return head;
    }
    return `${head} ${belowThousand(r)}`;
  }

  function joinParts(parts) {
    return parts.filter(Boolean).join(" ").trim();
  }

  function rupeesInWords(amount) {
    let n = Math.round(Number(amount));
    if (!Number.isFinite(n)) {
      return "";
    }
    let neg = false;
    if (n < 0) {
      neg = true;
      n = -n;
    }
    if (n === 0) {
      return "Rupees Zero only";
    }
    const parts = [];
    let crore = Math.floor(n / 10000000);
    n %= 10000000;
    if (crore) {
      parts.push(`${belowThousand(crore)} Crore`);
    }
    let lakh = Math.floor(n / 100000);
    n %= 100000;
    if (lakh) {
      parts.push(`${belowThousand(lakh)} Lakh`);
    }
    let thousand = Math.floor(n / 1000);
    n %= 1000;
    if (thousand) {
      parts.push(`${belowThousand(thousand)} Thousand`);
    }
    if (n) {
      parts.push(belowThousand(n));
    }
    let core = joinParts(parts);
    if (neg) {
      core = `Negative ${core}`;
    }
    return `Rupees ${core} only`;
  }

  function parseRaw(text) {
    const cleaned = String(text || "")
      .replace(/,/g, "")
      .trim();
    if (!cleaned) {
      return null;
    }
    if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) {
      return null;
    }
    const value = Number(cleaned);
    if (!Number.isFinite(value) || value < 0) {
      return null;
    }
    return Math.round(value * 100) / 100;
  }

  function formatDisplay(value) {
    if (value == null) {
      return "";
    }
    const fixed = value.toFixed(2);
    const dot = fixed.indexOf(".");
    const intPart = Number(fixed.slice(0, dot)).toLocaleString("en-IN");
    const dec = fixed.slice(dot + 1);
    if (dec === "00") {
      return intPart;
    }
    return `${intPart}.${dec}`;
  }

  function updateWords(wordsEl, value) {
    if (!wordsEl) {
      return;
    }
    if (value == null) {
      wordsEl.textContent = "";
      wordsEl.hidden = true;
      return;
    }
    wordsEl.textContent = rupeesInWords(value);
    wordsEl.hidden = false;
  }

  function bindInput(input) {
    const wrap = input.closest("[data-amount-formatted-wrap]") || input.parentElement;
    const wordsEl = wrap ? wrap.querySelector("[data-amount-words]") : null;
    const form = input.closest("form");

    function applyFromInput() {
      const parsed = parseRaw(input.value);
      if (parsed == null) {
        if (!input.value.trim()) {
          input.value = "";
          updateWords(wordsEl, null);
        } else {
          updateWords(wordsEl, null);
        }
        return;
      }
      input.value = formatDisplay(parsed);
      updateWords(wordsEl, parsed);
    }

    if (input.value.trim()) {
      applyFromInput();
    }

    input.addEventListener("input", applyFromInput);

    if (form) {
      form.addEventListener("submit", () => {
        const parsed = parseRaw(input.value);
        if (parsed == null) {
          input.value = "";
        } else {
          input.value = parsed.toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1");
          if (/^\d+\.\d$/.test(input.value)) {
            input.value = `${input.value}0`;
          }
          if (!input.value.includes(".")) {
            input.value = String(Math.round(parsed));
          }
        }
      });
    }
  }

  function init() {
    document.querySelectorAll("input[data-amount-formatted]").forEach(bindInput);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
