"""Layout constants measured directly from the original CV PDF.

Every number here was read out of ``nuri_cv.pdf`` with PyMuPDF (page geometry,
fill rectangles, text baselines and leadings), so the generated PDF reproduces
the original grid rather than approximating it by eye.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class Theme:
    # --- page -----------------------------------------------------------
    page_width: float = 595.0
    page_height: float = 841.9

    # --- main (left) column --------------------------------------------
    main_x: float = 30.0
    main_width: float = 288.75

    # --- sidebar (right) column -----------------------------------------
    side_bg_x: float = 348.75
    side_x: float = 363.75
    side_width: float = 216.75
    side_bg: Tuple[float, float, float] = (0.9686, 0.9686, 0.9686)

    # --- vertical rhythm -------------------------------------------------
    #: First text baseline on a continuation page (main column).
    main_top_baseline: float = 30.75
    #: First text baseline in the sidebar on every page.
    side_top_baseline: float = 42.75
    #: Lowest baseline we are willing to use before breaking the page.
    max_baseline: float = 795.0

    # --- typography ------------------------------------------------------
    font_regular: str = "Helvetica"
    font_bold: str = "Helvetica-Bold"
    size_name: float = 18.0
    size_job_title: float = 12.0
    size_section: float = 12.0
    size_body: float = 10.5
    size_contact: float = 10.0

    leading_body: float = 13.5
    #: Leading between the wrapped lines of a bullet in the main column.
    leading_bullet: float = 15.75
    #: Extra space after a bullet item.
    space_after_bullet: float = 1.5
    #: Extra space after a sidebar list item.
    space_after_side_item: float = 3.75
    #: Gap between the heading baseline and the first content baseline.
    section_header_to_body: float = 24.75
    #: Gap left above a section heading.
    space_before_section: float = 19.5
    #: Offsets of the black rule drawn under a section heading.
    rule_top_offset: float = 5.25
    rule_height: float = 2.25

    #: Entry internal leadings.
    entry_title_leading: float = 15.75
    entry_sub_leading: float = 17.25
    space_after_entry: float = 21.0

    #: Indent of bullet text relative to the bullet glyph.
    bullet_indent_main: float = 15.4
    bullet_indent_side: float = 12.3
    size_bullet_glyph: float = 12.0

    text_color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    muted_color: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    # --- header block (page 1, main column) -------------------------------
    header_name_baseline: float = 43.5
    header_title_gap: float = 21.7
    header_contact_gap: float = 24.0
    header_contact_leading: float = 21.0
    header_bottom_gap: float = 33.0

    icon_size: float = 9.0
    icon_gap: float = 5.0

    def column_geometry(self, column: str) -> Dict[str, float]:
        if column == "side":
            return {"x": self.side_x, "width": self.side_width, "top": self.side_top_baseline}
        return {"x": self.main_x, "width": self.main_width, "top": self.main_top_baseline}


DEFAULT_THEME = Theme()


@dataclass
class ThemeOverrides:
    """User-tweakable knobs exposed in the UI (density / font scaling)."""

    body_size: float = DEFAULT_THEME.size_body
    line_spacing: float = 1.0
    section_spacing: float = 1.0
    font_family: str = ""

    def apply(self, theme: Theme = DEFAULT_THEME) -> Theme:
        from .fonts import DEFAULT_FAMILY, resolve_family

        regular, bold = resolve_family(self.font_family or DEFAULT_FAMILY)
        scale = self.body_size / DEFAULT_THEME.size_body
        ls = self.line_spacing
        ss = self.section_spacing
        return Theme(
            font_regular=regular,
            font_bold=bold,
            size_body=self.body_size,
            size_section=round(DEFAULT_THEME.size_section * scale, 2),
            size_job_title=round(DEFAULT_THEME.size_job_title * scale, 2),
            size_name=round(DEFAULT_THEME.size_name * scale, 2),
            size_contact=round(DEFAULT_THEME.size_contact * scale, 2),
            leading_body=round(DEFAULT_THEME.leading_body * scale * ls, 2),
            leading_bullet=round(DEFAULT_THEME.leading_bullet * scale * ls, 2),
            entry_title_leading=round(DEFAULT_THEME.entry_title_leading * scale * ls, 2),
            entry_sub_leading=round(DEFAULT_THEME.entry_sub_leading * scale * ls, 2),
            space_after_entry=round(DEFAULT_THEME.space_after_entry * ss, 2),
            space_before_section=round(DEFAULT_THEME.space_before_section * ss, 2),
            section_header_to_body=round(DEFAULT_THEME.section_header_to_body * scale * ls, 2),
            space_after_side_item=round(DEFAULT_THEME.space_after_side_item * ss, 2),
            space_after_bullet=round(DEFAULT_THEME.space_after_bullet * ss, 2),
        )
