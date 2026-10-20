import logging
from pypdf import PdfReader

logger = logging.getLogger(__name__)

MAX_CHARS = 30_000
MAX_PDF_PAGES = 50
_SNIFF_BYTES = 8192


def extract_text(path: str, filename: str, mime_type: str) -> str:
    """Best-effort plain text of a file for search indexing ("" for binary or unreadable files)."""
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return _extract_pdf(path)
    if mime_type.startswith(("image/", "video/", "audio/")):
        return ""

    with open(path, "rb") as fh:
        data = fh.read(MAX_CHARS * 4)
    # NUL bytes in the first few KB are the classic tell for binary content
    if b"\x00" in data[:_SNIFF_BYTES]:
        return ""
    return data.decode("utf-8", errors="ignore")[:MAX_CHARS]


def _extract_pdf(path: str) -> str:
    parts: list[str] = []
    length = 0
    try:
        # A file handle (not a path) stops pypdf from reading the whole PDF into RAM
        with open(path, "rb") as fh:
            for page_number, page in enumerate(PdfReader(fh).pages):
                if page_number >= MAX_PDF_PAGES or length >= MAX_CHARS:
                    break
                text = page.extract_text() or ""
                parts.append(text)
                length += len(text)
    except Exception as exc:
        # Malformed or encrypted PDFs stay searchable by name
        logger.warning("Could not extract text from PDF %s: %s", path, exc)
    return "\n".join(parts)[:MAX_CHARS]
