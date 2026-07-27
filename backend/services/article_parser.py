"""
Article parsing for style uploads.

Turns an uploaded file (PDF / TXT / CSV / JSON) into a clean list of whole
LinkedIn articles.

Design notes
------------
* PDFs are extracted as ONE continuous document. The previous implementation
  split page-by-page first, which chopped every article that crossed a page
  boundary into two or more fragments.
* Article headers are matched typo-tolerantly ("Artcle 11 :", "Artcile 13 :",
  "Arctle 21 :" all appear in real exports) but with strict guards so that
  in-body lines like "Option 1: @Order" are never treated as boundaries.
* Chunking granularity is one article = one chunk. LinkedIn posts are short
  (100-400 words) and style is a whole-document property, so splitting them
  further would hand the generator half-examples to imitate.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

# An article shorter than this is almost certainly a parsing artifact
# (stray footer, page number, dangling URL fragment).
MIN_ARTICLE_CHARS = 60

# Header token variants are matched by similarity rather than a fixed list.
_HEADER_WORD = "article"
_HEADER_SIMILARITY = 0.72
_MAX_HEADER_LINE = 80
_MAX_ARTICLE_NUMBER = 999

# Line that is only a ligature artifact left behind by some PDF extractors.
_LIGATURE_JUNK = re.compile(r"^(f[filjt]{0,2}|ﬀ|ﬁ|ﬂ|ﬃ|ﬄ)$", re.IGNORECASE)

_HEADER_LINE = re.compile(
    r"^\s*([A-Za-z]{4,10})\s*[-–—]?\s*(\d{1,3})\s*[:.)-]\s*(.*)$"
)

_URL_CONTINUATION = re.compile(r"^[\w\-./?&=%#~+:;,@]+$")


# ─── Text extraction ──────────────────────────────────────────────


_SENTENCE_END = re.compile(r"[.!?:;,—–\-\"')\]}]$")


def _rebuild_paragraphs(lines: list[tuple[str, float, float, int]]) -> str:
    """Reconstruct paragraphs from line geometry.

    PDF extractors emit one line per visual line, so a soft-wrapped sentence
    and a genuine paragraph break look identical in the plain text output.
    That flattens the writer's paragraph rhythm, which is one of the strongest
    signals in a LinkedIn style profile.

    Lines carry (text, top, bottom, page). A vertical gap noticeably larger
    than the wrap gap marks a real paragraph break; anything smaller is a soft
    wrap and gets joined back into one line.
    """
    lines = [ln for ln in lines if ln[0].strip()]
    if not lines:
        return ""

    heights = sorted(bottom - top for _, top, bottom, _ in lines)
    median_height = heights[len(heights) // 2] or 12.0
    # Wrapped lines sit ~2pt apart; paragraph breaks are a full line or more.
    threshold = median_height * 0.5

    paragraphs: list[str] = []
    current: list[str] = [lines[0][0].strip()]

    for idx in range(1, len(lines)):
        text, top, _bottom, page = lines[idx]
        prev_text, _prev_top, prev_bottom, prev_page = lines[idx - 1]

        if is_header_line(text) or is_header_line(prev_text):
            # An article header always stands alone, whatever the spacing says.
            new_paragraph = True
        elif page != prev_page:
            # Y coordinates reset between pages, so fall back to punctuation:
            # an unfinished sentence is treated as a continuation.
            new_paragraph = bool(_SENTENCE_END.search(prev_text.strip()))
        else:
            new_paragraph = (top - prev_bottom) > threshold

        if new_paragraph:
            paragraphs.append(_join_fragments(current))
            current = [text.strip()]
        else:
            current.append(text.strip())

    paragraphs.append(_join_fragments(current))
    return "\n\n".join(p for p in paragraphs if p)


def _join_fragments(fragments: list[str]) -> str:
    """Join soft-wrapped fragments back into one line.

    Wrapped prose is rejoined with a space, but a URL broken across lines is
    stitched back with no separator — otherwise the post link is destroyed.
    """
    fragments = [f.strip() for f in fragments if f.strip()]
    if not fragments:
        return ""
    out = fragments[0]
    for fragment in fragments[1:]:
        if (
            re.search(r"https?://\S*$", out)
            and " " not in fragment
            and not fragment.startswith("#")
            and _URL_CONTINUATION.fullmatch(fragment)
        ):
            out += fragment
        else:
            out += " " + fragment
    return out.strip()


def _pymupdf_lines(data: bytes) -> list[tuple[str, float, float, int]]:
    import fitz  # PyMuPDF

    doc = fitz.open(stream=data, filetype="pdf")
    lines: list[tuple[str, float, float, int]] = []
    try:
        for page_no, page in enumerate(doc):
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:  # 0 = text, 1 = image
                    continue
                for line in block.get("lines", []):
                    text = "".join(span.get("text", "") for span in line.get("spans", []))
                    if not text.strip():
                        continue
                    _x0, y0, _x1, y1 = line.get("bbox", (0, 0, 0, 0))
                    lines.append((text, y0, y1, page_no))
    finally:
        doc.close()
    return lines


def _pdfplumber_lines(data: bytes) -> list[tuple[str, float, float, int]]:
    import io

    import pdfplumber

    lines: list[tuple[str, float, float, int]] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages):
            for line in page.extract_text_lines():
                text = line.get("text", "")
                if not text.strip():
                    continue
                lines.append((text, line["top"], line["bottom"], page_no))
    return lines


def extract_pdf_text(data: bytes) -> str:
    """Extract a PDF as one continuous, paragraph-aware document.

    The document is never split page-by-page here. Articles routinely span a
    page boundary, and splitting first would fragment them.

    Backends are tried in order of quality: PyMuPDF, pdfplumber, then pypdf.
    """
    for loader in (_pymupdf_lines, _pdfplumber_lines):
        try:
            lines = loader(data)
        except ImportError:
            continue
        except Exception:
            continue
        if lines:
            text = _rebuild_paragraphs(lines)
            if text.strip():
                return text

    # Last resort: no geometry available, so paragraph rhythm is lost.
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        if text.strip():
            return text
    except Exception:
        pass

    raise RuntimeError(
        "Could not extract text from the PDF. Install pymupdf "
        "(pip install pymupdf), or check that the PDF is not a scanned image."
    )


# ─── Normalisation ────────────────────────────────────────────────


def normalize_text(text: str) -> str:
    """Repair the usual PDF-extraction damage without touching the author's voice.

    * NFKC folds ligature glyphs (ﬁ, ﬂ, ﬀ) back into plain letters, so
      "beneﬁts" becomes "benefits" and embeds/generates correctly.
    * Rejoins URLs that the PDF wrapped across several lines.
    * Collapses the LinkedIn "hashtag\\n#Foo" export pattern.
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace(" ", " ").replace("​", "")

    text = _rejoin_wrapped_urls(text)

    # LinkedIn exports emit each hashtag as two lines: "hashtag" then "#Tag".
    text = re.sub(r"^[ \t]*hashtag[ \t]*\n[ \t]*(#\S+)", r"\1", text, flags=re.MULTILINE)

    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Drop bare page numbers and ligature debris left by the extractor.
        if re.fullmatch(r"(page\s*)?\d{1,3}", stripped, flags=re.IGNORECASE):
            continue
        if _LIGATURE_JUNK.fullmatch(stripped):
            continue
        lines.append(line.rstrip())

    text = "\n".join(lines)
    # Two newlines mean a paragraph break, three or more mean an article break.
    # Collapsing everything to "\n\n" here would erase the article signal that
    # the blank-line splitter depends on, so only the excess is trimmed.
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _is_url_debris(token: str) -> bool:
    """True if a token is the tail of a URL the PDF broke apart, not prose.

    Post links wrap across lines and sometimes across a page, leaving pieces
    like "utm_source=share&utm_medium=member_desktop" or "PeK0f-P5f3c2hebZ".
    Ordinary words that happen to follow a link must not match.
    """
    if len(token) < 4 or token.startswith("#"):
        return False
    if not _URL_CONTINUATION.fullmatch(token):
        return False
    if re.search(r"[?&=%/]", token):
        return True
    has_digit = any(c.isdigit() for c in token)
    has_alpha = any(c.isalpha() for c in token)
    return has_digit and has_alpha and len(token) > 8


def _rejoin_wrapped_urls(text: str) -> str:
    """Glue URL fragments the PDF layout broke apart back into one link.

    Works on whitespace tokens rather than lines, because a long link can be
    split across a paragraph break or a page boundary as well as a soft wrap.
    """
    tokens = re.findall(r"\S+|\s+", text)
    out: list[str] = []
    url_open = False
    for token in tokens:
        if token.isspace():
            out.append(token)
            continue
        if url_open and _is_url_debris(token) and out and out[-1].isspace():
            out.pop()  # drop the separator so the fragment rejoins the link
            out.append(token)
            continue
        url_open = token.lower().startswith(("http://", "https://")) or (
            url_open and _is_url_debris(token)
        )
        out.append(token)
    return "".join(out)


# ─── Header detection ─────────────────────────────────────────────


def _looks_like_article_word(token: str) -> bool:
    """True for 'Article' and its common misspellings, false for other words.

    Real exports contain Artcle / Artcile / Arctle. Words such as "Option",
    "Step" or "Point" must not match, or numbered lists inside a post would be
    treated as article boundaries.
    """
    token = token.lower()
    if token == _HEADER_WORD:
        return True
    if abs(len(token) - len(_HEADER_WORD)) > 2:
        return False
    if not token.startswith("a"):
        return False
    return SequenceMatcher(None, token, _HEADER_WORD).ratio() >= _HEADER_SIMILARITY


def parse_header_line(line: str) -> tuple[int, str] | None:
    """Return (article_number, trailing_text) if the line is an article header.

    Guarded so that numbered lines inside a post — "Option 1: @Order",
    "Step 2 - deploy" — are never mistaken for article boundaries.
    """
    if not line or len(line) > _MAX_HEADER_LINE:
        return None
    match = _HEADER_LINE.match(line)
    if not match:
        return None
    word, number, rest = match.group(1), match.group(2), match.group(3)
    if not _looks_like_article_word(word):
        return None
    num = int(number)
    if num < 1 or num > _MAX_ARTICLE_NUMBER:
        return None
    return num, rest.strip()


def is_header_line(line: str) -> bool:
    return parse_header_line(line) is not None


def find_article_headers(text: str) -> list[tuple[int, int, str]]:
    """Locate article headers.

    Returns a list of (line_index, article_number, trailing_text_on_that_line).
    """
    headers: list[tuple[int, int, str]] = []
    for idx, line in enumerate(text.split("\n")):
        parsed = parse_header_line(line)
        if parsed is None:
            continue
        num, rest = parsed
        headers.append((idx, num, rest))

    # A single match is more likely a false positive than a real structure.
    if len(headers) < 2:
        return []

    # Article numbers should broadly ascend. Drop stragglers that don't.
    cleaned: list[tuple[int, int, str]] = []
    highest = 0
    for header in headers:
        if header[1] > highest:
            cleaned.append(header)
            highest = header[1]
        elif not cleaned:
            cleaned.append(header)
            highest = header[1]
    return cleaned


# ─── Splitting ────────────────────────────────────────────────────


def _extract_trailing_url(body: str) -> tuple[str, str]:
    """Pull a trailing post URL off the end of an article body."""
    match = re.search(r"(https?://\S+)\s*$", body)
    if not match:
        return body.strip(), ""
    url = match.group(1).rstrip(".,;")
    return body[: match.start()].strip(), url


def _finalize(body: str, number: int | None = None) -> dict | None:
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if not body:
        return None
    body, url = _extract_trailing_url(body)
    # Any remaining URLs inside the body are left in place — they are part of
    # the author's writing.
    if len(body) < MIN_ARTICLE_CHARS:
        return None
    return {
        "content": body,
        "category": "",
        "url": url,
        "number": number,
    }


def split_into_articles(text: str) -> dict:
    """Split a document into whole articles.

    Strategy, in order of confidence:
      1. Explicit "Article N :" headers (typo tolerant)
      2. Horizontal-rule separators (--- / ___ / ===)
      3. Post URL as a terminator (each article ends with its LinkedIn link)
      4. Three or more consecutive blank lines
      5. The whole document as a single article

    Returns {"articles": [...], "method": str, "skipped": int, "gaps": [int]}
    """
    text = normalize_text(text)
    if not text:
        return {"articles": [], "method": "empty", "skipped": 0, "gaps": []}

    lines = text.split("\n")
    headers = find_article_headers(text)

    articles: list[dict] = []
    skipped = 0
    method = ""

    if headers:
        method = "article-headers"
        for pos, (line_idx, number, trailing) in enumerate(headers):
            end = headers[pos + 1][0] if pos + 1 < len(headers) else len(lines)
            body_lines = ([trailing] if trailing else []) + lines[line_idx + 1 : end]
            article = _finalize("\n".join(body_lines), number)
            if article:
                articles.append(article)
            else:
                skipped += 1
        # Everything before the first header is a preamble, never an article.
    else:
        chunks: list[str] = []
        if re.search(r"^\s*([-_=]{3,})\s*$", text, flags=re.MULTILINE):
            method = "separator"
            chunks = re.split(r"^\s*[-_=]{3,}\s*$", text, flags=re.MULTILINE)
        elif len(re.findall(r"https?://(?:www\.)?linkedin\.com/\S+", text)) >= 2:
            method = "post-url"
            chunks = _split_on_urls(text)
        elif re.search(r"\n\s*\n\s*\n", text):
            method = "blank-lines"
            chunks = re.split(r"\n\s*\n\s*\n+", text)
        else:
            method = "single"
            chunks = [text]

        for chunk in chunks:
            article = _finalize(chunk)
            if article:
                articles.append(article)
            elif chunk.strip():
                skipped += 1

    gaps = _numbering_gaps(articles)
    return {"articles": articles, "method": method, "skipped": skipped, "gaps": gaps}


def _split_on_urls(text: str) -> list[str]:
    """Split where each article ends with its own post URL."""
    parts = re.split(r"(https?://(?:www\.)?linkedin\.com/\S+)", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        if re.fullmatch(r"https?://(?:www\.)?linkedin\.com/\S+", part.strip()):
            chunks.append(f"{buf}\n{part.strip()}")
            buf = ""
        else:
            buf += part
    if buf.strip():
        chunks.append(buf)
    return chunks


def _numbering_gaps(articles: list[dict]) -> list[int]:
    """Article numbers present in the file but missing from the parse."""
    numbers = sorted(a["number"] for a in articles if a.get("number"))
    if len(numbers) < 2:
        return []
    return [n for n in range(numbers[0], numbers[-1] + 1) if n not in set(numbers)]


# ─── Entry point used by the upload endpoint ──────────────────────


def parse_upload(data: bytes, filename: str) -> dict:
    """Parse an uploaded file into articles.

    Returns {"articles": [...], "method": str, "skipped": int, "gaps": [int]}
    where each article is {"content", "category", "url", "number"}.
    """
    name = (filename or "").lower()

    if name.endswith(".pdf"):
        return split_into_articles(extract_pdf_text(data))

    if name.endswith(".json"):
        import json

        try:
            payload = json.loads(data.decode("utf-8", errors="ignore"))
        except Exception as exc:
            raise ValueError(f"Invalid JSON file: {exc}") from exc
        if not isinstance(payload, list):
            payload = [payload]

        articles, skipped = [], 0
        for item in payload:
            if isinstance(item, str):
                item = {"content": item}
            content = normalize_text(str(item.get("content", "")))
            if len(content) < MIN_ARTICLE_CHARS:
                skipped += 1
                continue
            articles.append(
                {
                    "content": content,
                    "category": item.get("category", "") or "",
                    "url": item.get("url", "") or "",
                    "number": None,
                }
            )
        return {"articles": articles, "method": "json", "skipped": skipped, "gaps": []}

    if name.endswith(".csv"):
        import csv
        import io

        text = data.decode("utf-8", errors="ignore")
        reader = csv.DictReader(io.StringIO(text))
        articles, skipped = [], 0
        for row in reader:
            content = normalize_text(row.get("content", "") or "")
            if len(content) < MIN_ARTICLE_CHARS:
                skipped += 1
                continue
            articles.append(
                {
                    "content": content,
                    "category": row.get("category", "") or "",
                    "url": row.get("url", "") or "",
                    "number": None,
                }
            )
        return {"articles": articles, "method": "csv", "skipped": skipped, "gaps": []}

    # .txt / .md / anything else
    return split_into_articles(data.decode("utf-8", errors="ignore"))
