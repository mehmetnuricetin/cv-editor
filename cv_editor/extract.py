"""Layout-aware extraction of a two-column CV PDF into :class:`CVData`.

The parser does not simply dump text: it reconstructs the page geometry
(columns, section rules, baselines, bold/regular font roles) so that entries,
right-aligned dates and bullet lists survive the round trip.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pymupdf

from .model import (
    DEFAULT_SKILL_CATEGORIES,
    SEC_CERTIFICATES,
    SEC_CLIENTS,
    SEC_COURSES,
    SEC_EDUCATION,
    SEC_EXPERIENCE,
    SEC_INTERESTS,
    SEC_LANGUAGES,
    SEC_SKILLS,
    SEC_SUMMARY,
    Contact,
    CVData,
    Entry,
    LayoutConfig,
    SkillCategory,
)

BULLET_CHARS = "\u2022\u25cf\u25aa\u00b7\u2023\u2043-\u2013"

SECTION_PATTERNS: Sequence[Tuple[str, str]] = (
    (SEC_CLIENTS, r"client|project|assignment|consult"),
    (SEC_EXPERIENCE, r"experience|employment|work history|career"),
    (SEC_SUMMARY, r"summary|profile|about|objective"),
    (SEC_SKILLS, r"skill|competenc|technolog|expertise"),
    (SEC_EDUCATION, r"education|academic"),
    (SEC_CERTIFICATES, r"certificat|credential|licen"),
    (SEC_COURSES, r"cource|course|training"),
    (SEC_LANGUAGES, r"language"),
    (SEC_INTERESTS, r"interest|hobb"),
)

SKILL_CATEGORY_RULES: Sequence[Tuple[str, str]] = (
    ("Containers and Kubernetes", r"kubernetes|aks|eks|openshift|docker|podman|container|helm|istio|rancher"),
    ("Infrastructure as Code", r"terraform|bicep|arm template|ansible|pulumi|crossplane|cloudformation|iac"),
    ("CI/CD and Automation", r"ci/cd|pipeline|github actions|azure devops|jenkins|argo|flux|gitlab|automation|devops"),
    ("Monitoring and Security", r"monitor|observab|prometheus|grafana|sentinel|defender|security|backup|update management|compliance|governance|entra|active directory|key vault"),
    ("AI and Agentic AI", r"\bai\b|copilot|agentic|openai|foundry|machine learning|llm"),
    ("Operating Systems and Scripting", r"linux|windows|bash|powershell|python|shell|script|rhel|ubuntu"),
    ("Cloud Platforms", r"azure|aws|gcp|google cloud|cloud|api management|app service|virtual machine"),
)

OTHER_CATEGORY = "Other"


@dataclass
class TextRow:
    page: int
    column: str
    x: float
    y: float
    text: str
    font: str
    size: float
    right_text: str = ""
    is_bold: bool = False
    is_header: bool = False


@dataclass
class ExtractionResult:
    cv: CVData
    warnings: List[str] = field(default_factory=list)
    raw_text: str = ""
    page_count: int = 0
    sections_found: List[str] = field(default_factory=list)
    unmapped_headings: List[str] = field(default_factory=list)


class ExtractionError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _canonical_section(heading: str) -> Optional[str]:
    low = heading.strip().lower()
    for section, pattern in SECTION_PATTERNS:
        if re.search(pattern, low):
            return section
    return None


def _is_heading_text(text: str) -> bool:
    stripped = re.sub(r"[^A-Za-zÅÄÖåäö]", "", text)
    if len(stripped) < 3 or len(text) > 60:
        return False
    return stripped.isupper()


def _detect_sidebar_x(page: pymupdf.Page) -> Optional[float]:
    """Find the x where a full-height, non-white band starts on the right."""
    height = page.rect.height
    width = page.rect.width
    best: Optional[float] = None
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        if not fill:
            continue
        rect = drawing["rect"]
        if rect.height < height * 0.6:
            continue
        if rect.width < width * 0.15 or rect.width > width * 0.75:
            continue
        if min(fill) > 0.995:  # pure white -> page background
            continue
        if rect.x0 < width * 0.4:
            continue
        if best is None or rect.x0 < best:
            best = rect.x0
    return best


def _rule_tops(page: pymupdf.Page) -> List[Tuple[float, float]]:
    """Return ``(x0, y_top)`` of thin dark horizontal rules (section underlines)."""
    rules = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        rect = drawing["rect"]
        if rect.height > 5 or rect.width < 60:
            continue
        if fill is not None and max(fill) > 0.6:
            continue
        if fill is None and drawing.get("color") is None:
            continue
        rules.append((rect.x0, rect.y0))
    return rules


def _collect_rows(doc: pymupdf.Document) -> Tuple[List[TextRow], Dict[str, float], List[str]]:
    warnings: List[str] = []
    sidebar_candidates = [x for x in (_detect_sidebar_x(p) for p in doc) if x]
    sidebar_x = min(sidebar_candidates) if sidebar_candidates else None

    raw_lines: List[dict] = []
    font_counter: Counter = Counter()

    for pno, page in enumerate(doc):
        rules = _rule_tops(page)
        info = page.get_text("dict")
        for block in info["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in line["spans"]).strip()
                if not text:
                    continue
                span = spans[0]
                size = round(span["size"], 1)
                font_counter[(span["font"], size)] += len(text)
                raw_lines.append(
                    {
                        "page": pno,
                        "x": span["origin"][0],
                        "y": span["origin"][1],
                        "text": text,
                        "font": span["font"],
                        "size": size,
                        "rules": rules,
                    }
                )

    if not raw_lines:
        raise ExtractionError("No selectable text found in this PDF.")

    body_font, body_size = font_counter.most_common(1)[0][0]

    # Fonts used at roughly body size but different from the body font are the
    # template's bold/emphasis fonts.
    bold_fonts = {
        font
        for (font, size), _ in font_counter.items()
        if abs(size - body_size) <= 1.0 and font != body_font
    }

    if sidebar_x is None:
        xs = [l["x"] for l in raw_lines]
        page_width = doc[0].rect.width
        right = [x for x in xs if x > page_width * 0.5]
        if right and len(right) > len(xs) * 0.15:
            sidebar_x = min(right) - 15
            warnings.append(
                "No sidebar background was detected; the column split was inferred from text positions."
            )
        else:
            sidebar_x = doc[0].rect.width + 1
            warnings.append("The PDF looks single-column; everything was placed in the main column.")

    rows: List[TextRow] = []
    for l in raw_lines:
        column = "side" if l["x"] >= sidebar_x - 5 else "main"
        is_header = False
        if _is_heading_text(l["text"]):
            for rx, ry in l["rules"]:
                if abs(rx - l["x"]) < 6 and 1.0 < (ry - l["y"]) < 12.0:
                    is_header = True
                    break
            if not is_header and l["size"] > body_size + 0.5 and _canonical_section(l["text"]):
                is_header = True
        rows.append(
            TextRow(
                page=l["page"],
                column=column,
                x=l["x"],
                y=l["y"],
                text=l["text"],
                font=l["font"],
                size=l["size"],
                is_bold=l["font"] in bold_fonts,
                is_header=is_header,
            )
        )

    rows.sort(key=lambda r: (r.column, r.page, round(r.y, 1), r.x))
    merged = _merge_right_aligned(rows)
    geo = {"sidebar_x": sidebar_x, "body_size": body_size}
    return merged, geo, warnings


def _clean_text(text: str) -> str:
    """Drop private-use icon glyphs and collapse whitespace."""
    cleaned = "".join(ch for ch in text if not ("\ue000" <= ch <= "\uf8ff"))
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_bullet_only(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) == 1 and stripped[0] in "\u2022\u25cf\u25aa\u2023"


def _join_wrapped(parts: Sequence[str]) -> str:
    """Join wrapped lines, repairing words hyphenated at a line break."""
    out = ""
    for part in parts:
        part = (part or "").strip()
        if not part:
            continue
        if not out:
            out = part
        elif out.endswith("-") and part[:1].islower():
            out = out + part
        else:
            out = f"{out} {part}"
    return out


def _merge_right_aligned(rows: Sequence[TextRow]) -> List[TextRow]:
    """Collapse each horizontal band into one row.

    Inside a band the left-most fragment is the content, while a fragment far
    to the right is right-aligned meta (dates, locations).  A lone bullet glyph
    is re-attached to the text that follows it, because the bullet and its text
    sit on slightly different baselines in the source PDF.
    """
    out: List[TextRow] = []
    by_key: Dict[Tuple[str, int], List[TextRow]] = {}
    for row in rows:
        by_key.setdefault((row.column, row.page), []).append(row)

    for key in sorted(by_key):
        group = sorted(by_key[key], key=lambda r: (r.y, r.x))
        bands: List[List[TextRow]] = []
        for row in group:
            if bands and abs(row.y - bands[-1][0].y) <= 4.0:
                bands[-1].append(row)
            else:
                bands.append([row])

        for band in bands:
            band.sort(key=lambda r: r.x)
            base = band[0]
            others = band[1:]
            right = ""
            if others and others[-1].x > base.x + 40 and not _is_bullet_only(base.text):
                right = _clean_text(others.pop().text)
            base.text = _join_wrapped([_clean_text(base.text)] + [_clean_text(o.text) for o in others])
            base.right_text = right
            if base.is_bold and any(o.is_bold for o in others):
                base.is_bold = True
            if base.text:
                out.append(base)

    out.sort(key=lambda r: (r.column, r.page, round(r.y, 1), r.x))
    return out


# ---------------------------------------------------------------------------
# section grouping
# ---------------------------------------------------------------------------

@dataclass
class RawSection:
    column: str
    heading: str
    section_id: Optional[str]
    rows: List[TextRow] = field(default_factory=list)


def _group_sections(rows: Sequence[TextRow]) -> Tuple[List[TextRow], List[RawSection]]:
    preamble: List[TextRow] = []
    sections: List[RawSection] = []
    current: Dict[str, Optional[RawSection]] = {"main": None, "side": None}

    for row in rows:
        if row.is_header:
            sid = _canonical_section(row.text)
            existing = None
            if sid is not None:
                for sec in sections:
                    if sec.column == row.column and sec.section_id == sid:
                        existing = sec
                        break
            if existing is not None:
                current[row.column] = existing  # section continues on a new page
            else:
                sec = RawSection(column=row.column, heading=row.text.strip(), section_id=sid)
                sections.append(sec)
                current[row.column] = sec
            continue
        active = current.get(row.column)
        if active is None:
            preamble.append(row)
        else:
            active.rows.append(row)
    return preamble, sections


# ---------------------------------------------------------------------------
# content parsers
# ---------------------------------------------------------------------------

def _strip_bullet(text: str) -> Tuple[bool, str]:
    stripped = text.lstrip()
    if stripped and stripped[0] in BULLET_CHARS and (len(stripped) == 1 or stripped[1] in " \t" or len(stripped) > 1):
        if stripped[0] in "-\u2013" and not stripped[1:2] == " ":
            return False, text
        return True, stripped[1:].strip()
    return False, text


def _parse_list(rows: Sequence[TextRow]) -> List[str]:
    if not rows:
        return []
    col_x = min(r.x for r in rows)
    items: List[str] = []
    for row in rows:
        is_bullet, content = _strip_bullet(row.text)
        indented = row.x > col_x + 8
        if is_bullet:
            items.append(content)
        elif indented and items:
            items[-1] = _join_wrapped([items[-1], row.text])
        elif row.text.strip():
            items.append(row.text.strip())
    return [i for i in (s.strip() for s in items) if i]


def _parse_paragraph(rows: Sequence[TextRow]) -> str:
    parts = [r.text.strip() for r in rows if r.text.strip()]
    return _join_wrapped(parts)


def _parse_entries(rows: Sequence[TextRow], body_leading: float = 13.5) -> List[Entry]:
    if not rows:
        return []
    col_x = min(r.x for r in rows)
    entries: List[Entry] = []

    current: Optional[Entry] = None
    mode = "idle"            # idle | title | sub
    sub_groups: List[List[TextRow]] = []
    prev: Optional[TextRow] = None
    title_rows: List[TextRow] = []

    def flush() -> None:
        nonlocal current, title_rows, sub_groups
        if current is None:
            return
        current.title = _join_wrapped([r.text for r in title_rows])
        if title_rows and title_rows[0].right_text:
            current.right_top = title_rows[0].right_text
        if sub_groups:
            g = sub_groups[0]
            current.subtitle = _join_wrapped([r.text for r in g])
            current.right_sub = g[0].right_text
        if len(sub_groups) > 1:
            g = sub_groups[1]
            current.third = _join_wrapped([r.text for r in g])
            current.right_third = g[0].right_text
        if len(sub_groups) > 2:
            extra = _join_wrapped([r.text for g in sub_groups[2:] for r in g])
            if extra:
                current.bullets.insert(0, extra)
        if not current.is_empty():
            entries.append(current)
        current = None
        title_rows = []
        sub_groups = []

    for row in rows:
        is_bullet, content = _strip_bullet(row.text)
        indented = row.x > col_x + 8
        same_page_gap = (
            row.y - prev.y if prev is not None and prev.page == row.page else 999.0
        )

        if is_bullet or (indented and mode == "bullets"):
            if current is None:
                current = Entry()
            if is_bullet:
                current.bullets.append(content)
            elif current.bullets:
                current.bullets[-1] = _join_wrapped([current.bullets[-1], row.text])
            else:
                current.bullets.append(row.text.strip())
            mode = "bullets"
            prev = row
            continue

        if indented and current is not None and current.bullets:
            current.bullets[-1] = _join_wrapped([current.bullets[-1], row.text])
            prev = row
            continue

        if row.is_bold:
            if mode in ("sub", "bullets") or current is None:
                flush()
                current = Entry()
                title_rows = [row]
                mode = "title"
            else:
                title_rows.append(row)
                mode = "title"
        else:
            if current is None:
                current = Entry()
                mode = "title"
            if mode == "title":
                sub_groups = [[row]]
                mode = "sub"
            else:
                if sub_groups and same_page_gap <= body_leading * 1.2:
                    sub_groups[-1].append(row)
                else:
                    sub_groups.append([row])
        prev = row

    flush()
    return entries


def categorise_skills(skills: Sequence[str]) -> List[SkillCategory]:
    """Group skills into the standard DevOps categories using local rules only."""
    buckets: Dict[str, List[str]] = {}
    for skill in skills:
        name = skill.strip()
        if not name:
            continue
        low = name.lower()
        target = OTHER_CATEGORY
        for category, pattern in SKILL_CATEGORY_RULES:
            if re.search(pattern, low):
                target = category
                break
        buckets.setdefault(target, []).append(name)

    ordered: List[SkillCategory] = []
    for category in DEFAULT_SKILL_CATEGORIES:
        if buckets.get(category):
            ordered.append(SkillCategory(name=category, skills=buckets.pop(category)))
    for category, values in buckets.items():
        ordered.append(SkillCategory(name=category, skills=values))
    return ordered


def _parse_contact(rows: Sequence[TextRow]) -> Tuple[str, str, Contact]:
    # A contact line may have been split into several horizontal fragments
    # (icon + value), so re-join each row with its right-hand fragment.
    texts = [
        _join_wrapped([r.text, r.right_text])
        for r in rows
        if _join_wrapped([r.text, r.right_text])
    ]
    name = texts[0] if texts else ""
    job_title = texts[1] if len(texts) > 1 else ""
    blob = " ".join(texts[2:]) if len(texts) > 2 else ""

    contact = Contact()
    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", blob)
    if email:
        contact.email = email.group(0)
        blob = blob.replace(email.group(0), " ")

    linkedin = re.search(r"(?:https?://)?(?:www\.)?linkedin\.com/\S+", blob, re.I)
    if linkedin:
        contact.linkedin = linkedin.group(0).rstrip(".,")
        blob = blob.replace(linkedin.group(0), " ")

    github = re.search(r"(?:https?://)?(?:www\.)?github\.com/\S+", blob, re.I)
    if github:
        contact.github = github.group(0).rstrip(".,")
        blob = blob.replace(github.group(0), " ")

    phone = re.search(r"\+?\d[\d\s().\-]{6,}\d", blob)
    if phone:
        contact.phone = phone.group(0).strip()
        blob = blob.replace(phone.group(0), " ")

    website = re.search(r"(?:https?://)\S+", blob)
    if website:
        contact.website = website.group(0).rstrip(".,")
        blob = blob.replace(website.group(0), " ")

    leftover = " ".join(w for w in blob.split() if len(w) > 1 and not w.startswith("@"))
    leftover = leftover.strip(" |·-\u2022")
    if leftover:
        contact.location = leftover
    return name, job_title, contact


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def analyse_pdf(pdf_bytes: bytes) -> List[str]:
    """Return warnings about scanned / unextractable content."""
    warnings: List[str] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for pno, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            images = page.get_images()
            if not text and images:
                warnings.append(
                    f"Page {pno} contains no selectable text but has images - it looks scanned. "
                    "Text from that page must be typed in manually (no OCR is performed locally)."
                )
            elif len(text) < 40 and images:
                warnings.append(f"Page {pno} has very little selectable text; check the extracted content carefully.")
            elif not text:
                warnings.append(f"Page {pno} appears to be empty.")
    return warnings


def extract_cv(pdf_bytes: bytes) -> ExtractionResult:
    """Parse a CV PDF into an editable :class:`CVData`."""
    warnings = analyse_pdf(pdf_bytes)

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_count = len(doc)
        raw_text = "\n".join(page.get_text("text") for page in doc)
        rows, geo, geo_warnings = _collect_rows(doc)

    warnings.extend(geo_warnings)
    preamble, sections = _group_sections(rows)

    cv = CVData()
    main_preamble = [r for r in preamble if r.column == "main"]
    cv.name, cv.job_title, cv.contact = _parse_contact(main_preamble)

    layout_main: List[str] = []
    layout_side: List[str] = []
    found: List[str] = []
    unmapped: List[str] = []

    for sec in sections:
        sid = sec.section_id
        if sid is None:
            unmapped.append(sec.heading)
            continue
        cv.headings[sid] = sec.heading
        found.append(sid)
        target = layout_side if sec.column == "side" else layout_main
        if sid not in target:
            target.append(sid)

        if sid == SEC_SUMMARY:
            cv.summary = _parse_paragraph(sec.rows)
        elif sid == SEC_SKILLS:
            cv.skill_categories = categorise_skills(_parse_list(sec.rows))
        elif sid == SEC_LANGUAGES:
            cv.languages = _parse_list(sec.rows)
        elif sid == SEC_INTERESTS:
            cv.interests = _parse_list(sec.rows)
        elif sid == SEC_EXPERIENCE:
            cv.experience.extend(_parse_entries(sec.rows))
        elif sid == SEC_CLIENTS:
            cv.clients.extend(_parse_entries(sec.rows))
        elif sid == SEC_EDUCATION:
            cv.education.extend(_parse_entries(sec.rows))
        elif sid == SEC_CERTIFICATES:
            cv.certificates.extend(_parse_entries(sec.rows))
        elif sid == SEC_COURSES:
            cv.courses.extend(_parse_entries(sec.rows))

    if layout_main or layout_side:
        cv.layout = LayoutConfig(main=layout_main or LayoutConfig().main,
                                 side=layout_side or LayoutConfig().side)

    if unmapped:
        warnings.append(
            "These headings were not recognised and their content was skipped: "
            + ", ".join(sorted(set(unmapped)))
            + ". Add the content manually if you need it."
        )
    if not found:
        warnings.append(
            "No standard CV sections were detected. Use the raw text view to copy content into the editors."
        )
    if not cv.name:
        warnings.append("Could not detect a name at the top of the CV - please fill it in.")

    return ExtractionResult(
        cv=cv,
        warnings=warnings,
        raw_text=raw_text,
        page_count=page_count,
        sections_found=found,
        unmapped_headings=sorted(set(unmapped)),
    )
