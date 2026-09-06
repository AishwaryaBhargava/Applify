"""Markdown to DOCX: turning a generated document into a file people can send.

Everything Applify generates is Markdown, and nobody applies for a job by
pasting Markdown into a form. This module is the last mile: it renders that
Markdown into a Word document a recruiter's ATS will parse and a human will read
without noticing it was machine-made.

The renderer is deliberately small. It understands the subset of Markdown the
generation prompts actually emit -- headings, paragraphs, bullet and numbered
lists, bold, italic, links, horizontal rules -- and nothing else. Anything it
does not recognise falls through as plain text rather than as a raised
exception, because a resume that renders one line as literal ``**`` is a
blemish, while a resume that fails to export at all is a lost application.

Two decisions worth naming:

* **Only the document title uses a built-in Word style.** The name at the top is
  Word's ``Title``, so the file has a real title in outlines and navigation
  panes; its inherited accent border is replaced with the same hairline the
  section headers use, so the document has one rule and not two. Everything
  below it is a plain paragraph with explicit size and weight -- Word's Heading
  1/2 are blue, oversized, and carry outline levels some ATS parsers trip over.
* **Links are flattened to "text (url)".** A real hyperlink field is invisible
  on paper and invisible to a plain-text ATS parse. The URL is the information;
  it goes in the text.
"""

import re
import unicodedata
from io import BytesIO

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

# --------------------------------------------------------------------------
# Look
# --------------------------------------------------------------------------

BODY_FONT = "Calibri"
BODY_SIZE_PT = 11
PAGE_MARGIN_INCHES = 0.75

# The one built-in Word style used, and only for the document's own title.
TITLE_STYLE = "Title"

TITLE_SIZE_PT = 16
SECTION_SIZE_PT = 12
SUBSECTION_SIZE_PT = 11

# A dark desaturated teal. Reads as considered on screen and as near-black in
# greyscale, which is how half of these documents get printed.
TITLE_COLOR = RGBColor(0x11, 0x4B, 0x5A)

# The hairline under each section header, in eighths of a point.
RULE_SIZE_EIGHTHS = "6"
RULE_COLOR = "AAB4B8"

# Where ``w:pBdr`` has to sit inside ``w:pPr``. python-docx models only part of
# that element, so the border is inserted before every sibling the schema says
# must follow it -- appending it would produce a file Word calls corrupt.
_AFTER_PBDR: tuple[str, ...] = (
    "w:shd",
    "w:tabs",
    "w:suppressAutoHyphens",
    "w:kinsoku",
    "w:wordWrap",
    "w:overflowPunct",
    "w:topLinePunct",
    "w:autoSpaceDE",
    "w:autoSpaceDN",
    "w:bidi",
    "w:adjustRightInd",
    "w:snapToGrid",
    "w:spacing",
    "w:ind",
    "w:contextualSpacing",
    "w:mirrorIndents",
    "w:suppressOverlap",
    "w:jc",
    "w:textDirection",
    "w:textAlignment",
    "w:textboxTightWrap",
    "w:outlineLvl",
    "w:divId",
    "w:cnfStyle",
    "w:rPr",
    "w:sectPr",
    "w:pPrChange",
)

# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBER_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_RULE_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")

# ``[label](https://example.com "title")`` -- the optional title is discarded.
_LINK_RE = re.compile(r"\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")

# Bold before italic, so ``**x**`` is never read as an empty italic wrapping
# ``*x*``. Backticks are captured only to strip them.
_INLINE_RE = re.compile(
    r"(\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_|`[^`\n]+`)"
)

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def flatten_links(text: str) -> str:
    """Rewrite Markdown links as ``label (url)``.

    A bare link, or one whose label is already the URL, collapses to the URL
    alone -- "https://git.io/x (https://git.io/x)" helps nobody.
    """

    def replace(match: re.Match) -> str:
        label = match.group(1).strip()
        url = match.group(2).strip()
        if not label or label == url:
            return url
        return "{} ({})".format(label, url)

    return _LINK_RE.sub(replace, text)


def add_runs(paragraph, text: str) -> None:
    """Write ``text`` into a paragraph, honouring bold, italic, and links.

    Emphasis markers are consumed; anything malformed (an unclosed ``**``, a
    stray underscore inside a word) simply does not match and survives as
    literal text, which is the right failure for a document nobody will proof
    before sending.
    """
    for piece in _INLINE_RE.split(flatten_links(text)):
        if not piece:
            continue
        run = paragraph.add_run()
        if piece.startswith("**") and piece.endswith("**"):
            run.text = piece[2:-2]
            run.bold = True
        elif piece.startswith("__") and piece.endswith("__"):
            run.text = piece[2:-2]
            run.bold = True
        elif piece.startswith("*") and piece.endswith("*"):
            run.text = piece[1:-1]
            run.italic = True
        elif piece.startswith("_") and piece.endswith("_"):
            run.text = piece[1:-1]
            run.italic = True
        elif piece.startswith("`") and piece.endswith("`"):
            run.text = piece[1:-1]
        else:
            run.text = piece


def _add_bottom_rule(paragraph) -> None:
    """Draw a hairline under one paragraph, as a section divider.

    Written directly onto the paragraph rather than left to the style, which is
    also how the ``Title`` style's inherited accent border gets overridden: an
    explicit ``w:pBdr`` on the paragraph wins over the one it inherits.
    """
    properties = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), RULE_SIZE_EIGHTHS)
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), RULE_COLOR)
    borders.append(bottom)
    properties.insert_element_before(borders, *_AFTER_PBDR)


def _configure(document) -> None:
    """Set the page geometry and the body typeface for the whole document."""
    margin = Inches(PAGE_MARGIN_INCHES)
    for section in document.sections:
        section.top_margin = margin
        section.bottom_margin = margin
        section.left_margin = margin
        section.right_margin = margin

    normal = document.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = Pt(BODY_SIZE_PT)
    # East-Asian font mapping is a separate attribute; without it Word
    # substitutes its own default for anything outside Latin-1.
    fonts = normal.element.get_or_add_rPr().get_or_add_rFonts()
    fonts.set(qn("w:eastAsia"), BODY_FONT)

    spacing = normal.paragraph_format
    spacing.line_spacing = 1.0
    spacing.space_before = Pt(0)
    spacing.space_after = Pt(6)


# Markdown heading level -> (style, point size, colour, rule underneath).
# Levels below 3 collapse onto level 3: a resume with an H4 in it is a model
# slip, not a structure worth rendering differently.
_HEADING_LEVELS: dict[int, tuple[str | None, int, RGBColor | None, bool]] = {
    1: (TITLE_STYLE, TITLE_SIZE_PT, TITLE_COLOR, True),
    2: (None, SECTION_SIZE_PT, None, True),
    3: (None, SUBSECTION_SIZE_PT, None, False),
}


def _heading(document, text: str, level: int):
    """Append one heading paragraph at the requested Markdown level."""
    style, size, color, ruled = _HEADING_LEVELS[min(level, 3)]

    paragraph = document.add_paragraph(style=style) if style else document.add_paragraph()

    spacing = paragraph.paragraph_format
    spacing.space_before = Pt(0 if level == 1 else 10 if level == 2 else 6)
    spacing.space_after = Pt(2 if level != 2 else 4)
    spacing.line_spacing = 1.0

    add_runs(paragraph, text)
    for run in paragraph.runs:
        run.bold = True
        run.font.name = BODY_FONT
        run.font.size = Pt(size)
        if color is not None:
            run.font.color.rgb = color

    if ruled:
        _add_bottom_rule(paragraph)
    return paragraph


def markdown_to_docx(markdown: str, title: str = "") -> bytes:
    """Render a Markdown document as a .docx file.

    Args:
        markdown: The generated document, as the model wrote it.
        title: The document's title. Stored as a Word core property so the file
            identifies itself in a document library; it is never drawn on the
            page, because the Markdown already opens with the candidate's name.

    Returns:
        The complete .docx file as bytes.
    """
    document = Document()
    _configure(document)
    if title:
        document.core_properties.title = title

    for raw_line in (markdown or "").splitlines():
        line = raw_line.rstrip()

        if not line.strip():
            continue

        if _RULE_RE.match(line):
            # A horizontal rule becomes breathing room rather than a line:
            # a printed rule across a resume reads as a formatting accident.
            document.add_paragraph()
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            _heading(document, heading.group(2).strip(), len(heading.group(1)))
            continue

        quoted = _QUOTE_RE.match(line)
        if quoted:
            line = quoted.group(1)

        bullet = _BULLET_RE.match(line)
        if bullet:
            add_runs(document.add_paragraph(style="List Bullet"), bullet.group(1))
            continue

        numbered = _NUMBER_RE.match(line)
        if numbered:
            add_runs(document.add_paragraph(style="List Number"), numbered.group(1))
            continue

        add_runs(document.add_paragraph(), line.strip())

    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Filenames
# --------------------------------------------------------------------------


def slugify(text: str, fallback: str = "applify") -> str:
    """Reduce a company or job title to a safe, readable filename fragment.

    Accents are folded rather than dropped ("Zürich" -> "zurich"), everything
    else that is not a letter or a digit becomes a single hyphen, and an empty
    result falls back rather than producing a filename that starts with a dot.
    """
    folded = unicodedata.normalize("NFKD", text or "")
    ascii_only = folded.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_STRIP_RE.sub("-", ascii_only).strip("-")
    return slug or fallback


def export_filename(company: str | None, output_type: str, extension: str) -> str:
    """Build the download filename for one exported document.

    ``<company>-<kind>.<ext>``, all slugified: the two things the user needs to
    tell twenty files apart in a downloads folder six weeks from now.
    """
    kind = slugify(output_type.replace("_", "-"), fallback="document")
    return "{}-{}.{}".format(slugify(company or ""), kind, extension)
