"""
services/pdf_parser.py — PDF text extraction + clause segmentation.

Pipeline:
  1. Extract raw text from PDF using pdfplumber (preserves layout)
  2. Split into clauses using heading/numbering heuristics
  3. Return list of ClauseChunk objects ready for embedding

Why pdfplumber over PyMuPDF?
  pdfplumber preserves column layout and handles multi-column legal PDFs
  better. For scanned PDFs (images), we fall back to basic text extraction.
"""
import re
import pdfplumber
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ClauseChunk:
    """One segmented clause from a contract."""
    clause_number: str          # "8.2", "(a)", "IV", etc. — empty if no number
    title: str                  # Detected heading or first line
    text: str                   # Full clause text
    page: int                   # Page number (1-indexed)
    char_count: int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.text)


# ── Regex patterns for clause detection ────────────────────────────────

# Matches:  1.   1.2   2.3.1   (a)   (i)   ARTICLE I   Section 4
CLAUSE_HEADING = re.compile(
    r"""^
    (?:
        (?:ARTICLE|SECTION|SCHEDULE|EXHIBIT|ANNEX)\s+[\dIVXLCivxlc]+  # ARTICLE IV
        | \d{1,2}(?:\.\d{1,2}){0,3}\.?                                 # 1.2.3
        | \([a-z]{1,3}\)                                                # (a)(iii)
        | [IVXLCivxlc]{1,5}\.                                          # IV.
    )
    \s+[A-Z]                                                            # followed by capital
    """,
    re.VERBOSE | re.MULTILINE
)

# All-caps lines ≥ 3 words = likely a section heading
ALL_CAPS_HEADING = re.compile(r'^[A-Z][A-Z\s\-]{10,}$')


def extract_text_by_page(pdf_path: str) -> dict[int, str]:
    """
    Extract text from each page of a PDF.
    Returns {page_number: text_content}.
    """
    pages: dict[int, str] = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text(x_tolerance=2, y_tolerance=2)
                if text and text.strip():
                    pages[i] = text.strip()
                else:
                    # Fallback for pages with no extractable text
                    pages[i] = ""
                    logger.warning(f"Page {i}: no text extracted (may be scanned image)")
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed: {e}")

    return pages


def segment_clauses(pages: dict[int, str]) -> list[ClauseChunk]:
    """
    Split contract text into clause-level chunks using numbering heuristics.

    Strategy:
      - Join all page text into one document (preserving page markers)
      - Detect clause boundary lines using regex
      - Accumulate text until next boundary
      - Return one ClauseChunk per detected clause
    """
    # Build list of (page, line) tuples
    page_lines: list[tuple[int, str]] = []
    for page_num, text in pages.items():
        for line in text.split('\n'):
            page_lines.append((page_num, line.rstrip()))

    chunks: list[ClauseChunk] = []
    current_number = ""
    current_title = ""
    current_lines: list[str] = []
    current_page = 1

    def flush():
        nonlocal current_number, current_title, current_lines, current_page
        text = ' '.join(current_lines).strip()
        # Only keep chunks with meaningful content (>30 chars)
        if text and len(text) > 30:
            chunks.append(ClauseChunk(
                clause_number=current_number,
                title=current_title or text[:60],
                text=text,
                page=current_page
            ))
        current_number = ""
        current_title = ""
        current_lines = []

    for page_num, line in page_lines:
        stripped = line.strip()
        if not stripped:
            continue

        is_boundary = (
            CLAUSE_HEADING.match(stripped) or
            ALL_CAPS_HEADING.match(stripped)
        )

        if is_boundary:
            flush()
            current_page = page_num
            # Try to parse clause number from the start of line
            num_match = re.match(r'^(\d{1,2}(?:\.\d{1,2}){0,3}|\([a-z]{1,3}\))', stripped)
            current_number = num_match.group(1) if num_match else ""
            current_title = stripped
            current_lines = [stripped]
        else:
            current_lines.append(stripped)

    flush()  # Don't forget the last clause

    # If segmentation found fewer than 3 clauses, fall back to paragraph chunking
    if len(chunks) < 3:
        logger.warning("Clause segmentation found few clauses — falling back to paragraph chunking")
        chunks = paragraph_fallback(pages)

    logger.info(f"Segmented into {len(chunks)} clauses")
    return chunks


def paragraph_fallback(pages: dict[int, str]) -> list[ClauseChunk]:
    """
    Fallback: split by double newlines (paragraphs) when heading
    detection doesn't find enough clauses.
    """
    chunks = []
    for page_num, text in pages.items():
        paragraphs = re.split(r'\n{2,}', text)
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if len(para) > 50:
                chunks.append(ClauseChunk(
                    clause_number=str(i + 1),
                    title=para[:60] + "…",
                    text=para,
                    page=page_num
                ))
    return chunks


def parse_pdf(pdf_path: str) -> tuple[list[ClauseChunk], int]:
    """
    Main entry point.
    Returns (list_of_clauses, total_page_count).
    """
    pages = extract_text_by_page(pdf_path)
    if not pages:
        raise ValueError("Could not extract any text from this PDF. It may be a scanned image.")

    page_count = len(pages)
    clauses = segment_clauses(pages)

    # Guard: max 200 clauses (very long contracts)
    if len(clauses) > 200:
        clauses = clauses[:200]
        logger.warning("Contract truncated to 200 clauses")

    return clauses, page_count
