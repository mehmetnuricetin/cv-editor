"""Vector icons for the contact line.

The original PDF uses a subsetted FontAwesome Type0 font that cannot be
re-embedded, so the handful of icons we need are drawn as small vector shapes
instead.  They are intentionally simple and monochrome to match the original.
"""

from __future__ import annotations

from reportlab.pdfgen.canvas import Canvas


def _badge(c: Canvas, letter: str, x: float, y: float, s: float) -> None:
    c.saveState()
    c.setFillColorRGB(0, 0, 0)
    c.roundRect(x, y, s, s, s * 0.18, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", s * 0.62)
    c.drawCentredString(x + s / 2.0, y + s * 0.26, letter)
    c.restoreState()


def _phone(c: Canvas, x: float, y: float, s: float) -> None:
    c.saveState()
    c.setFillColorRGB(0, 0, 0)
    w = s * 0.62
    x0 = x + (s - w) / 2.0
    c.roundRect(x0, y, w, s, s * 0.14, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.rect(x0 + w * 0.22, y + s * 0.82, w * 0.56, s * 0.06, stroke=0, fill=1)
    c.circle(x0 + w / 2.0, y + s * 0.13, s * 0.07, stroke=0, fill=1)
    c.restoreState()


def _email(c: Canvas, x: float, y: float, s: float) -> None:
    c.saveState()
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(max(0.6, s * 0.11))
    h = s * 0.72
    y0 = y + (s - h) / 2.0
    c.rect(x, y0, s, h, stroke=1, fill=0)
    c.line(x, y0 + h, x + s / 2.0, y0 + h * 0.38)
    c.line(x + s, y0 + h, x + s / 2.0, y0 + h * 0.38)
    c.restoreState()


def _location(c: Canvas, x: float, y: float, s: float) -> None:
    c.saveState()
    c.setFillColorRGB(0, 0, 0)
    cx = x + s / 2.0
    c.circle(cx, y + s * 0.66, s * 0.33, stroke=0, fill=1)
    p = c.beginPath()
    p.moveTo(cx - s * 0.26, y + s * 0.56)
    p.lineTo(cx + s * 0.26, y + s * 0.56)
    p.lineTo(cx, y)
    p.close()
    c.drawPath(p, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.circle(cx, y + s * 0.68, s * 0.12, stroke=0, fill=1)
    c.restoreState()


def _web(c: Canvas, x: float, y: float, s: float) -> None:
    c.saveState()
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(max(0.6, s * 0.1))
    r = s / 2.0
    cx, cy = x + r, y + r
    c.circle(cx, cy, r, stroke=1, fill=0)
    c.line(cx - r, cy, cx + r, cy)
    c.ellipse(cx - r * 0.45, cy - r, cx + r * 0.45, cy + r, stroke=1, fill=0)
    c.restoreState()


_DRAWERS = {
    "phone": _phone,
    "email": _email,
    "location": _location,
    "web": _web,
    "linkedin": lambda c, x, y, s: _badge(c, "in", x, y, s),
    "github": lambda c, x, y, s: _badge(c, "G", x, y, s),
}


def draw_icon(c: Canvas, kind: str, x: float, baseline: float, size: float) -> None:
    """Draw ``kind`` with its bottom-left corner sitting on the text baseline."""
    drawer = _DRAWERS.get(kind)
    if drawer is None:
        return
    drawer(c, x, baseline - size * 0.08, size)
