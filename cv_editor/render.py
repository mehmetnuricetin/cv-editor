"""Two-column CV renderer.

The renderer rebuilds the CV on a measured grid instead of patching the
original PDF (see README for the trade-offs).  It works in two stages:

1. Each column (main + sidebar) is turned into a flat list of :class:`Line`
   objects.  A line knows how tall it is, whether it must stay with the lines
   that follow, and how to draw itself at a given baseline.
2. A pagination pass walks each column independently, breaking pages and
   re-emitting section headings when a section continues onto a new page --
   exactly the behaviour of the original document.

This keeps the output free of overlapping text, orphaned headings and blank
pages regardless of how much content the user adds.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from reportlab.lib.colors import Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from .icons import draw_icon
from .model import (
    ALL_SECTIONS,
    ENTRY_SECTIONS,
    LIST_SECTIONS,
    SEC_CERTIFICATES,
    SEC_CLIENTS,
    SEC_COURSES,
    SEC_EDUCATION,
    SEC_EXPERIENCE,
    SEC_INTERESTS,
    SEC_LANGUAGES,
    SEC_SKILLS,
    SEC_SUMMARY,
    CVData,
    Entry,
)
from .theme import DEFAULT_THEME, Theme, ThemeOverrides

DrawFn = Callable[[Canvas, float, float], None]

BULLET = "\u2022"


class RenderError(RuntimeError):
    """Raised when the CV cannot be laid out at all."""


# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------

def text_width(text: str, font: str, size: float) -> float:
    return pdfmetrics.stringWidth(text or "", font, size)


def wrap_text(
    text: str,
    font: str,
    size: float,
    width: float,
    first_line_width: Optional[float] = None,
) -> List[str]:
    """Greedy word wrap.  ``first_line_width`` narrows only the first line."""
    text = (text or "").replace("\u2011", "-").strip()
    if not text:
        return []
    if width <= 1:
        return [text]
    lines: List[str] = []
    avail = first_line_width if first_line_width is not None else width
    avail = max(avail, size)  # never collapse to nothing
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if text_width(candidate, font, size) <= avail or not current:
            current = candidate
            # A single word longer than the line: hard-split it so no
            # characters are silently lost.
            while text_width(current, font, size) > avail and len(current) > 1:
                cut = len(current)
                while cut > 1 and text_width(current[:cut], font, size) > avail:
                    cut -= 1
                lines.append(current[:cut])
                current = current[cut:]
                avail = width
        else:
            lines.append(current)
            current = word
            avail = width
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# line model
# ---------------------------------------------------------------------------

@dataclass
class Line:
    advance: float
    draw: Optional[DrawFn] = None
    space_before: float = 0.0
    keep_with_next: int = 0
    section: Optional[str] = None
    is_header: bool = False


@dataclass
class Placed:
    page: int
    baseline: float
    line: Line


# ---------------------------------------------------------------------------
# builders
# ---------------------------------------------------------------------------

class FlowBuilder:
    def __init__(self, cv: CVData, theme: Theme, column: str):
        self.cv = cv
        self.t = theme
        self.column = column
        geo = theme.column_geometry(column)
        self.width = geo["width"]
        self.lines: List[Line] = []

    # -- primitives ------------------------------------------------------
    def _text_line(
        self,
        text: str,
        font: str,
        size: float,
        advance: float,
        dx: float = 0.0,
        right_text: str = "",
        right_font: str = "",
        right_size: float = 0.0,
        keep: int = 0,
        section: Optional[str] = None,
    ) -> None:
        rf = right_font or font
        rs = right_size or size
        width = self.width

        def draw(c: Canvas, x: float, y: float, _t=text, _f=font, _s=size, _dx=dx,
                 _rt=right_text, _rf=rf, _rs=rs) -> None:
            c.setFillColorRGB(0, 0, 0)
            c.setFont(_f, _s)
            c.drawString(x + _dx, y, _t)
            if _rt:
                c.setFont(_rf, _rs)
                c.drawRightString(x + width, y, _rt)

        self.lines.append(Line(advance=advance, draw=draw, keep_with_next=keep, section=section))

    def _spacer(self, height: float) -> None:
        if height:
            self.lines.append(Line(advance=height))

    # -- section heading ---------------------------------------------------
    def section_header_line(self, section: str, heading: str, keep: int = 1) -> Line:
        t = self.t
        width = self.width

        def draw(c: Canvas, x: float, y: float, _h=heading) -> None:
            c.setFillColorRGB(0, 0, 0)
            c.setFont(t.font_bold, t.size_section)
            c.drawString(x, y, _h)
            c.rect(x, y - t.rule_top_offset - t.rule_height, width, t.rule_height, stroke=0, fill=1)

        return Line(
            advance=t.section_header_to_body,
            draw=draw,
            space_before=t.space_before_section,
            keep_with_next=keep,
            section=section,
            is_header=True,
        )

    def add_section_header(self, section: str, keep: int = 1) -> None:
        self.lines.append(self.section_header_line(section, self.cv.heading(section), keep=keep))

    # -- header block (page 1, main column only) ---------------------------
    def add_document_header(self) -> None:
        t = self.t
        cv = self.cv
        start = len(self.lines)

        if (cv.name or "").strip():
            self._text_line(cv.name.strip(), t.font_bold, t.size_name, t.header_title_gap)
        if (cv.job_title or "").strip():
            self._text_line(cv.job_title.strip(), t.font_regular, t.size_job_title, t.header_contact_gap)

        rows = self._contact_rows()
        for i, row in enumerate(rows):
            last = i == len(rows) - 1
            advance = t.leading_body if last else t.header_contact_leading
            self.lines.append(self._contact_line(row, advance))

        if len(self.lines) > start:
            self.lines[-1].advance = t.leading_body

    def _contact_rows(self) -> List[List[Tuple[str, str]]]:
        """Greedily pack contact items into lines that fit the main column."""
        t = self.t
        items = self.cv.contact.as_items()
        rows: List[List[Tuple[str, str]]] = []
        current: List[Tuple[str, str]] = []
        used = 0.0
        gap = 14.0
        for kind, text in items:
            w = t.icon_size + t.icon_gap + text_width(text, t.font_regular, t.size_contact)
            extra = w if not current else w + gap
            if current and used + extra > self.width:
                rows.append(current)
                current, used = [(kind, text)], w
            else:
                current.append((kind, text))
                used += extra
        if current:
            rows.append(current)
        return rows

    def _contact_line(self, row: Sequence[Tuple[str, str]], advance: float) -> Line:
        t = self.t

        def draw(c: Canvas, x: float, y: float, _row=tuple(row)) -> None:
            cursor = x
            c.setFillColorRGB(0, 0, 0)
            for kind, text in _row:
                draw_icon(c, kind, cursor, y, t.icon_size)
                cursor += t.icon_size + t.icon_gap
                c.setFillColorRGB(0, 0, 0)
                c.setFont(t.font_regular, t.size_contact)
                c.drawString(cursor, y, text)
                cursor += text_width(text, t.font_regular, t.size_contact) + 14.0

        return Line(advance=advance, draw=draw, keep_with_next=0)

    # -- content sections ---------------------------------------------------
    def add_summary(self) -> None:
        t = self.t
        paragraphs = [p.strip() for p in (self.cv.summary or "").split("\n\n")]
        paragraphs = [p for p in paragraphs if p]
        if not paragraphs:
            return
        self.add_section_header(SEC_SUMMARY, keep=2)
        for pi, para in enumerate(paragraphs):
            wrapped = wrap_text(para.replace("\n", " "), t.font_regular, t.size_body, self.width)
            for i, text in enumerate(wrapped):
                end_of_para = i == len(wrapped) - 1
                last_para = pi == len(paragraphs) - 1
                advance = t.leading_body
                if end_of_para and not last_para:
                    advance += t.leading_body * 0.5
                self._text_line(
                    text,
                    t.font_regular,
                    t.size_body,
                    advance,
                    keep=1 if i == 0 else 0,
                    section=SEC_SUMMARY,
                )

    def add_entries(self, section: str, entries: Sequence[Entry]) -> None:
        entries = [e for e in entries if not e.is_empty()]
        if not entries:
            return
        self.add_section_header(section, keep=2)
        header = self.lines[-1]
        for idx, entry in enumerate(entries):
            start = len(self.lines)
            self._entry_lines(section, entry)
            if len(self.lines) > start:
                last_entry = idx == len(entries) - 1
                self.lines[-1].advance = (
                    self.t.leading_body if last_entry else self.t.space_after_entry
                )
                if section in (SEC_COURSES, SEC_CLIENTS):
                    entry_height = sum(line.advance for line in self.lines[start:-1])
                    top = self.t.column_geometry(self.column)["top"]
                    header_height = (
                        header.advance if idx == 0 or (
                            section == SEC_CLIENTS and self.cv.layout.repeat_section_headings
                        ) else 0.0
                    )
                    if entry_height + header_height <= self.t.max_baseline - top:
                        for offset, line in enumerate(self.lines[start:]):
                            line.keep_with_next = len(self.lines) - start - offset - 1
                        if idx == 0:
                            header.keep_with_next = len(self.lines) - start

    def _entry_lines(self, section: str, entry: Entry) -> None:
        t = self.t
        has_bullets = bool([b for b in entry.bullets if b.strip()])
        rows: List[Tuple[str, str, str, str]] = []  # (text, right, font, role)

        if entry.title.strip():
            rows.append((entry.title.strip(), entry.right_top.strip(), t.font_bold, "title"))
        if entry.subtitle.strip() or entry.right_sub.strip():
            rows.append((entry.subtitle.strip(), entry.right_sub.strip(), t.font_regular, "sub"))
        if entry.third.strip() or entry.right_third.strip():
            rows.append((entry.third.strip(), entry.right_third.strip(), t.font_regular, "third"))

        for ri, (text, right, font, role) in enumerate(rows):
            right_w = text_width(right, t.font_regular, t.size_body) if right else 0.0
            first_w = self.width - (right_w + 8.0) if right_w else self.width
            wrapped = wrap_text(text, font, t.size_body, self.width, first_line_width=first_w) or [""]
            is_last_row = ri == len(rows) - 1
            for li, chunk in enumerate(wrapped):
                is_last_line = li == len(wrapped) - 1
                if not is_last_line:
                    advance = t.leading_body
                elif is_last_row:
                    advance = t.entry_sub_leading if has_bullets else t.leading_body
                else:
                    advance = (
                        t.entry_title_leading if (role == "title" and has_bullets) else t.entry_sub_leading
                    )
                self._text_line(
                    chunk,
                    font,
                    t.size_body,
                    advance,
                    right_text=right if li == 0 else "",
                    keep=1 if (ri == 0 and li == 0) else 0,
                    section=section,
                )

        for bullet in entry.bullets:
            if bullet.strip():
                self._bullet(section, bullet.strip(), main_style=True)

    def _bullet(self, section: str, text: str, main_style: bool) -> None:
        t = self.t
        indent = t.bullet_indent_main if main_style else t.bullet_indent_side
        leading = t.leading_bullet if main_style else t.leading_body
        wrapped = wrap_text(text, t.font_regular, t.size_body, self.width - indent) or [""]
        for i, chunk in enumerate(wrapped):
            show_glyph = i == 0
            last = i == len(wrapped) - 1
            advance = leading + (t.space_after_bullet if last and main_style else 0.0)
            if last and not main_style:
                advance = leading + t.space_after_side_item

            def draw(c: Canvas, x: float, y: float, _c=chunk, _g=show_glyph, _i=indent) -> None:
                c.setFillColorRGB(0, 0, 0)
                if _g:
                    c.setFont(t.font_regular, t.size_bullet_glyph)
                    c.drawString(x, y, BULLET)
                c.setFont(t.font_regular, t.size_body)
                c.drawString(x + _i, y, _c)

            self.lines.append(
                Line(advance=advance, draw=draw, keep_with_next=1 if i == 0 and len(wrapped) > 1 else 0,
                     section=section)
            )

    def add_skills(self) -> None:
        t = self.t
        cats = [c for c in self.cv.skill_categories if [s for s in c.skills if s.strip()]]
        if not cats:
            return
        self.add_section_header(SEC_SKILLS, keep=2)
        if self.cv.layout.show_skill_categories:
            for ci, cat in enumerate(cats):
                if cat.name.strip():
                    self._text_line(
                        cat.name.strip(), t.font_bold, t.size_body, t.entry_sub_leading,
                        keep=1, section=SEC_SKILLS,
                    )
                for skill in cat.skills:
                    if skill.strip():
                        self._bullet(SEC_SKILLS, skill.strip(), main_style=False)
                if ci < len(cats) - 1 and self.lines:
                    self.lines[-1].advance += t.space_after_side_item
        else:
            seen = set()
            for cat in cats:
                for skill in cat.skills:
                    key = skill.strip().casefold()
                    if skill.strip() and key not in seen:
                        seen.add(key)
                        self._bullet(SEC_SKILLS, skill.strip(), main_style=False)

    def add_simple_list(self, section: str, values: Sequence[str]) -> None:
        values = [v.strip() for v in values if v.strip()]
        if not values:
            return
        self.add_section_header(section, keep=2)
        for value in values:
            self._bullet(section, value, main_style=False)


def build_column(cv: CVData, theme: Theme, column: str) -> List[Line]:
    builder = FlowBuilder(cv, theme, column)
    sections = cv.layout.main if column == "main" else cv.layout.side
    if column == "main":
        builder.add_document_header()
    for section in sections:
        if section not in ALL_SECTIONS:
            continue
        if section == SEC_SUMMARY:
            builder.add_summary()
        elif section == SEC_SKILLS:
            builder.add_skills()
        elif section in LIST_SECTIONS:
            builder.add_simple_list(section, cv.simple_list_for(section))
        elif section in ENTRY_SECTIONS:
            builder.add_entries(section, cv.entries_for(section))
    return builder.lines


# ---------------------------------------------------------------------------
# pagination
# ---------------------------------------------------------------------------

def paginate(
    lines: Sequence[Line],
    cv: CVData,
    theme: Theme,
    column: str,
    first_top: float,
    cont_top: float,
) -> List[Placed]:
    placed: List[Placed] = []
    if not lines:
        return placed

    builder = FlowBuilder(cv, theme, column)
    page = 0
    cursor = first_top
    page_has_content = False
    i = 0
    guard = 0
    max_iterations = len(lines) * 40 + 1000

    while i < len(lines):
        guard += 1
        if guard > max_iterations:
            raise RenderError("Layout did not converge; content may be malformed.")

        line = lines[i]
        group_end = min(len(lines), i + 1 + max(0, line.keep_with_next))
        space = line.space_before if page_has_content else 0.0
        group_height = sum(l.advance for l in lines[i:group_end - 1]) if group_end - 1 > i else 0.0
        if line.section in (SEC_COURSES, SEC_CLIENTS) and line.is_header:
            if group_height > theme.max_baseline - cont_top:
                group_height = sum(item.advance for item in lines[i:i + 2])
        last_baseline = cursor + space + group_height

        if page_has_content and last_baseline > theme.max_baseline:
            page += 1
            cursor = cont_top
            page_has_content = False
            if (
                cv.layout.repeat_section_headings
                and line.section
                and line.section != SEC_COURSES
                and not line.is_header
            ):
                header = builder.section_header_line(line.section, cv.heading(line.section), keep=0)
                placed.append(Placed(page, cursor, header))
                cursor += header.advance
                page_has_content = True
            continue

        cursor += space
        if line.draw is not None:
            placed.append(Placed(page, cursor, line))
            page_has_content = True
        elif page_has_content:
            pass
        cursor += line.advance
        i += 1

    return placed


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def render_cv_pdf(cv: CVData, theme: Optional[Theme] = None, title: str = "CV") -> bytes:
    """Render ``cv`` and return the PDF as bytes."""
    if theme is None:
        theme = ThemeOverrides().apply()
    main_lines = build_column(cv, theme, "main")
    side_lines = build_column(cv, theme, "side")

    has_header = bool((cv.name or "").strip() or (cv.job_title or "").strip())
    main_first_top = theme.header_name_baseline if has_header else theme.main_top_baseline

    main_placed = paginate(main_lines, cv, theme, "main", main_first_top, theme.main_top_baseline)
    side_placed = paginate(side_lines, cv, theme, "side", theme.side_top_baseline, theme.side_top_baseline)

    n_pages = 1 + max(
        [p.page for p in main_placed] + [p.page for p in side_placed] + [0]
    )

    buf = io.BytesIO()
    c = Canvas(buf, pagesize=(theme.page_width, theme.page_height))
    c.setTitle(title)
    c.setAuthor(cv.name or "")

    by_page: Dict[int, List[Tuple[float, Placed]]] = {p: [] for p in range(n_pages)}
    for p in main_placed:
        by_page[p.page].append((theme.main_x, p))
    for p in side_placed:
        by_page[p.page].append((theme.side_x, p))

    for page in range(n_pages):
        _draw_background(c, theme)
        for x, item in by_page[page]:
            y = theme.page_height - item.baseline
            if item.line.draw is not None:
                item.line.draw(c, x, y)
        c.showPage()

    c.save()
    return buf.getvalue()


def _draw_background(c: Canvas, theme: Theme) -> None:
    c.setFillColor(Color(1, 1, 1))
    c.rect(0, 0, theme.page_width, theme.page_height, stroke=0, fill=1)
    c.setFillColor(Color(*theme.side_bg))
    c.rect(theme.side_bg_x, 0, theme.page_width - theme.side_bg_x, theme.page_height, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)


def render_preview_images(pdf_bytes: bytes, dpi: int = 110) -> List[bytes]:
    """Rasterise a PDF to PNG bytes, one per page (used by the Streamlit UI)."""
    import pymupdf

    images: List[bytes] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        zoom = dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            images.append(pix.tobytes("png"))
    return images


def pdf_text(pdf_bytes: bytes) -> str:
    """Return all text in a PDF (used by tests and the verification panel)."""
    import pymupdf

    out = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            out.append(page.get_text("text"))
    return "\n".join(out)
