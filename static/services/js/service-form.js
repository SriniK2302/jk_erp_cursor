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

  function deriveServiceCode(serviceDescription) {
    const words = serviceDescription
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
    const descriptionInput = document.getElementById("id_service_desc");
    const codeInput = document.getElementById("id_service_code");

    if (!descriptionInput || !codeInput) {
      return;
    }

    let lastAutoCode = deriveServiceCode(descriptionInput.value || "");

    if (!codeInput.value.trim()) {
      codeInput.value = lastAutoCode;
    }

    descriptionInput.addEventListener("input", function () {
      const nextAutoCode = deriveServiceCode(descriptionInput.value || "");
      const codeCurrent = codeInput.value;

      // Keep auto-updating unless user manually changed the service code.
      if (!codeCurrent.trim() || codeCurrent.toUpperCase() === lastAutoCode) {
        codeInput.value = nextAutoCode;
      }

      lastAutoCode = nextAutoCode;
    });
  });
})();
