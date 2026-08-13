"""Helpers for setup-level Word template uploads on EngagementDocumentation."""

WORD_TEMPLATE_EXTENSIONS = (".doc", ".docx")


def word_template_extension_ok(filename: str) -> bool:
    name = (filename or "").strip().lower()
    return name.endswith(WORD_TEMPLATE_EXTENSIONS)


def word_template_content_type(filename: str) -> str:
    lower = (filename or "").strip().lower()
    if lower.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if lower.endswith(".doc"):
        return "application/msword"
    return "application/octet-stream"
