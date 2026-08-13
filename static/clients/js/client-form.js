(function () {
  const COMMON_WORD_CODES = new Set([
    "THIS",
    "THAT",
    "THEN",
    "THEM",
    "THEY",
    "WITH",
    "WERE",
    "FROM",
    "YOUR",
    "HAVE",
    "WILL",
    "INTO",
    "ONTO",
    "HERE",
    "THUS",
    "WHEN",
    "WHAT",
  ]);

  function cleanWord(word) {
    return word.replace(/^[^A-Za-z0-9]+|[^A-Za-z0-9]+$/g, "");
  }

  function guardCommonWordCode(code) {
    if (!code) {
      return code;
    }

    if (COMMON_WORD_CODES.has(code)) {
      return `${code.slice(0, -1)}X`;
    }

    return code;
  }

  function deriveShortName(clientName) {
    const words = clientName
      .trim()
      .split(/\s+/)
      .map(cleanWord)
      .filter(Boolean);

    if (words.length === 0) {
      return "";
    }

    const firstWord = words[0].toLowerCase();
    const takeCount = ["the", "sri", "sree"].includes(firstWord) ? 3 : 2;

    return words.slice(0, takeCount).join(" ");
  }

  function deriveClientCode(clientName) {
    const words = clientName
      .trim()
      .split(/\s+/)
      .map(cleanWord)
      .filter(Boolean);

    if (words.length === 0) {
      return "";
    }

    let code = "";
    if (words.length >= 4) {
      code = words
        .slice(0, 4)
        .map((word) => word.slice(0, 1))
        .join("");
    } else if (words.length === 3) {
      code = words[0].slice(0, 1) + words[1].slice(0, 1) + words[2].slice(0, 2);
    } else if (words.length === 2) {
      code = words[0].slice(0, 2) + words[1].slice(0, 2);
    } else {
      code = words[0].slice(0, 4);
    }

    return guardCommonWordCode(code.toUpperCase().slice(0, 4));
  }

  document.addEventListener("DOMContentLoaded", function () {
    const nameInput = document.getElementById("id_client_name");
    const shortNameInput = document.getElementById("id_client_short_name");
    const codeInput = document.getElementById("id_client_code");

    if (!nameInput || !shortNameInput || !codeInput) {
      return;
    }

    let lastAutoShortName = deriveShortName(nameInput.value || "");
    let lastAutoCode = deriveClientCode(nameInput.value || "");

    if (!shortNameInput.value.trim()) {
      shortNameInput.value = lastAutoShortName;
    }

    if (!codeInput.value.trim()) {
      codeInput.value = lastAutoCode;
    }

    nameInput.addEventListener("input", function () {
      const nextAutoShortName = deriveShortName(nameInput.value || "");
      const nextAutoCode = deriveClientCode(nameInput.value || "");
      const shortNameCurrent = shortNameInput.value;
      const codeCurrent = codeInput.value;

      // Keep auto-updating unless the user manually changed the short name.
      if (!shortNameCurrent.trim() || shortNameCurrent === lastAutoShortName) {
        shortNameInput.value = nextAutoShortName;
      }

      // Keep auto-updating unless the user manually changed the code.
      if (!codeCurrent.trim() || codeCurrent.toUpperCase() === lastAutoCode) {
        codeInput.value = nextAutoCode;
      }

      lastAutoShortName = nextAutoShortName;
      lastAutoCode = nextAutoCode;
    });
  });
})();
