"""Font registration with graceful fallback.

The original CV embeds Type3 subset fonts, which cannot be re-used for new
text.  We therefore register a visually close serif family from the system and
fall back to ReportLab's built-in Helvetica if nothing is available, so the
exporter never fails because of a missing font.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_MAC_FONT_DIRS = (
    "/System/Library/Fonts/Supplemental",
    "/System/Library/Fonts",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
)


@dataclass(frozen=True)
class FontSpec:
    file: str
    regular_index: Optional[int] = None
    bold_index: Optional[int] = None
    bold_file: Optional[str] = None


#: Display name -> candidate files.  First match wins.
FAMILIES: Dict[str, Sequence[FontSpec]] = {
    "Charter (closest to original)": (FontSpec("Charter.ttc", 0, 3),),
    "Georgia": (FontSpec("Georgia.ttf", bold_file="Georgia Bold.ttf"),),
    "Palatino": (FontSpec("Palatino.ttc", 0, 2),),
    "PT Serif": (FontSpec("PTSerif.ttc", 0, 3),),
    "Times New Roman": (FontSpec("Times New Roman.ttf", bold_file="Times New Roman Bold.ttf"),),
    "Helvetica (built-in)": (),
}

DEFAULT_FAMILY = "Charter (closest to original)"
FALLBACK = ("Helvetica", "Helvetica-Bold")

_registered: Dict[str, Tuple[str, str]] = {}


def _find(filename: str) -> Optional[str]:
    if os.path.isabs(filename):
        return filename if os.path.exists(filename) else None
    for directory in _MAC_FONT_DIRS:
        path = os.path.join(directory, filename)
        if os.path.exists(path):
            return path
    return None


def _register_spec(family: str, spec: FontSpec) -> Optional[Tuple[str, str]]:
    path = _find(spec.file)
    if path is None:
        return None
    slug = "".join(ch for ch in family if ch.isalnum())
    regular, bold = f"{slug}-R", f"{slug}-B"
    try:
        if spec.regular_index is None:
            pdfmetrics.registerFont(TTFont(regular, path))
        else:
            pdfmetrics.registerFont(TTFont(regular, path, subfontIndex=spec.regular_index))

        bold_path = _find(spec.bold_file) if spec.bold_file else path
        if bold_path is None:
            bold_path = path
        if spec.bold_index is None:
            pdfmetrics.registerFont(TTFont(bold, bold_path))
        else:
            pdfmetrics.registerFont(TTFont(bold, bold_path, subfontIndex=spec.bold_index))
    except Exception:
        return None
    pdfmetrics.registerFontFamily(slug, normal=regular, bold=bold, italic=regular, boldItalic=bold)
    return regular, bold


def resolve_family(family: str = DEFAULT_FAMILY) -> Tuple[str, str]:
    """Return ``(regular, bold)`` PostScript names, registering fonts as needed."""
    if family in _registered:
        return _registered[family]
    for spec in FAMILIES.get(family, ()):  # empty tuple -> built-in Helvetica
        names = _register_spec(family, spec)
        if names:
            _registered[family] = names
            return names
    _registered[family] = FALLBACK
    return FALLBACK


def available_families() -> List[str]:
    """Families that can actually be used on this machine."""
    out = []
    for family, specs in FAMILIES.items():
        if not specs:
            out.append(family)
            continue
        if any(_find(spec.file) for spec in specs):
            out.append(family)
    return out
