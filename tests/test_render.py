"""Tests for PDF generation and layout safety."""

from __future__ import annotations

import pymupdf
import pytest

from cv_editor.model import CVData, Entry, SkillCategory
from cv_editor.render import Line, build_column, paginate, pdf_text, render_cv_pdf, wrap_text
from cv_editor.theme import DEFAULT_THEME, ThemeOverrides
from tests.conftest import make_cv


def _spans(pdf_bytes: bytes):
    out = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for pno, page in enumerate(doc):
            for block in page.get_text("dict")["blocks"]:
                if block.get("type"):
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        if span["text"].strip():
                            out.append((pno, span["bbox"], span["text"]))
    return out


def test_pdf_is_valid_and_non_empty():
    pdf = render_cv_pdf(make_cv())
    assert pdf.startswith(b"%PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        assert len(doc) >= 1
        assert abs(doc[0].rect.width - 595.0) < 1.5
        assert abs(doc[0].rect.height - 841.9) < 1.5


def test_new_skill_appears_in_exported_pdf():
    cv = make_cv()
    cv.skill_categories[0].skills.append("Azure AI Foundry")
    text = pdf_text(render_cv_pdf(cv))
    assert "Azure AI Foundry" in text


def test_all_content_reaches_the_pdf():
    cv = make_cv()
    text = " ".join(pdf_text(render_cv_pdf(cv)).split())
    for expected in [
        cv.name,
        cv.job_title,
        cv.contact.email,
        "Terraform",
        "Kubernetes",
        cv.experience[0].title,
        cv.experience[0].subtitle,
        cv.experience[0].right_top,
        cv.clients[0].title,
        cv.education[0].subtitle,
        cv.certificates[0].title,
        cv.courses[0].title,
        "Swedish",
        "Film Making",
    ]:
        assert expected in text, f"missing from export: {expected!r}"


def test_sections_render_in_the_expected_columns():
    pdf = render_cv_pdf(make_cv())
    spans = _spans(pdf)
    skills = [s for s in spans if s[2].strip() == "SKILLS"]
    summary = [s for s in spans if s[2].strip() == "SUMMARY"]
    assert skills and skills[0][1][0] > DEFAULT_THEME.side_bg_x
    assert summary and summary[0][1][0] < DEFAULT_THEME.side_bg_x


def test_no_text_overlaps_the_column_gutter():
    pdf = render_cv_pdf(make_cv())
    for pno, bbox, text in _spans(pdf):
        x0, _, x1, _ = bbox
        if x0 < DEFAULT_THEME.side_bg_x:
            assert x1 <= DEFAULT_THEME.main_x + DEFAULT_THEME.main_width + 1.5, (
                f"main column text overflows: {text!r}")
        else:
            assert x1 <= DEFAULT_THEME.side_x + DEFAULT_THEME.side_width + 1.5, (
                f"sidebar text overflows: {text!r}")


def test_no_overlapping_lines_within_a_column():
    pdf = render_cv_pdf(make_cv())
    by_col = {}
    for pno, bbox, text in _spans(pdf):
        column = "side" if bbox[0] >= DEFAULT_THEME.side_bg_x else "main"
        by_col.setdefault((pno, column), []).append(bbox)
    for boxes in by_col.values():
        boxes.sort(key=lambda b: b[1])
        for a, b in zip(boxes, boxes[1:]):
            same_line = abs(a[1] - b[1]) < 1.0
            if not same_line:
                assert b[1] >= a[1] - 0.5, "text lines overlap vertically"


def test_long_skill_list_paginates_without_blank_or_lost_content():
    cv = make_cv()
    cv.skill_categories.append(
        SkillCategory(name="Bulk", skills=[f"Skill number {i:03d}" for i in range(140)])
    )
    pdf = render_cv_pdf(cv)
    text = pdf_text(pdf)
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        assert len(doc) > 1
        for page in doc:
            assert page.get_text("text").strip(), "a blank page was produced"
    for i in range(140):
        assert f"Skill number {i:03d}" in text


def test_very_long_single_word_is_hard_wrapped():
    word = "A" * 400
    lines = wrap_text(word, DEFAULT_THEME.font_regular, 10.5, 200.0)
    assert len(lines) > 1
    assert "".join(lines) == word


def test_section_heading_repeats_on_continuation_pages():
    cv = make_cv()
    cv.skill_categories.append(
        SkillCategory(name="Bulk", skills=[f"Skill {i}" for i in range(120)])
    )
    pdf = render_cv_pdf(cv)
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pages_with_skills = sum(1 for p in doc if "SKILLS" in p.get_text("text"))
    assert pages_with_skills >= 2


def test_empty_cv_does_not_crash():
    pdf = render_cv_pdf(CVData())
    assert pdf.startswith(b"%PDF")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        assert len(doc) == 1


def test_empty_entries_are_skipped():
    cv = make_cv()
    cv.experience.append(Entry())
    text = pdf_text(render_cv_pdf(cv))
    assert text.count("WORK EXPERIENCE") >= 1


def test_theme_overrides_change_density():
    cv = make_cv()
    cv.skill_categories.append(SkillCategory(name="Bulk", skills=[f"Skill {i}" for i in range(90)]))
    dense = ThemeOverrides(body_size=9.0, line_spacing=0.9, section_spacing=0.8).apply()
    loose = ThemeOverrides(body_size=12.0, line_spacing=1.25, section_spacing=1.4).apply()

    def pages(theme):
        with pymupdf.open(stream=render_cv_pdf(cv, theme), filetype="pdf") as doc:
            return len(doc)

    assert pages(dense) <= pages(loose)


def test_fallback_font_is_used_when_family_is_unknown():
    theme = ThemeOverrides(font_family="Does Not Exist").apply()
    assert theme.font_regular and theme.font_bold
    pdf = render_cv_pdf(make_cv(), theme)
    assert pdf.startswith(b"%PDF")


def test_pagination_never_loops_forever():
    cv = make_cv()
    cv.summary = " ".join(["word"] * 5000)
    lines = build_column(cv, DEFAULT_THEME, "main")
    placed = paginate(lines, cv, DEFAULT_THEME, "main",
                      DEFAULT_THEME.header_name_baseline, DEFAULT_THEME.main_top_baseline)
    assert placed
    assert max(p.page for p in placed) > 1


def test_courses_keep_wrapped_titles_with_providers_and_single_heading(tmp_path):
    cv = CVData()
    cv.layout.main = ["courses"]
    cv.layout.side = []
    cv.courses = [
        Entry(
            title=f"Course {index:03d} advanced cloud infrastructure automation and platform engineering",
            subtitle=f"Udemy provider {index:03d}",
        )
        for index in range(35)
    ]
    pdf = render_cv_pdf(cv, DEFAULT_THEME)
    (tmp_path / "courses-pagination.pdf").write_bytes(pdf)
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        texts = [page.get_text("text") for page in doc]
        assert len(doc) > 1
        assert sum(text.count("COURSES") for text in texts) == 1
        assert "Course 000" in texts[0] and "Udemy provider 000" in texts[0]
        for index in range(35):
            title_pages = [page for page, text in enumerate(texts) if f"Course {index:03d}" in text]
            provider_pages = [page for page, text in enumerate(texts) if f"Udemy provider {index:03d}" in text]
            assert len(title_pages) == 1 and title_pages == provider_pages
        for page in doc:
            boxes = sorted((span["bbox"] for span in page.get_texttrace()), key=lambda box: box[1])
            for above, below in zip(boxes, boxes[1:]):
                assert above[3] <= below[1]
            rules = [drawing["rect"] for drawing in page.get_drawings()
                     if drawing["rect"].height == DEFAULT_THEME.rule_height]
            for box in boxes:
                assert not any(pymupdf.Rect(box).intersects(rule) for rule in rules)


def test_courses_heading_moves_with_complete_first_entry():
    cv = CVData()
    cv.layout.main = ["courses"]
    cv.layout.side = []
    cv.courses = [Entry(
        title="Advanced cloud infrastructure automation and platform engineering training",
        subtitle="Coursera",
    )]
    lines = build_column(cv, DEFAULT_THEME, "main")
    preceding = Line(advance=1.0, draw=lambda canvas, x, y: None)
    placed = paginate([preceding, *lines], cv, DEFAULT_THEME, "main",
                      DEFAULT_THEME.max_baseline - 45.0, DEFAULT_THEME.main_top_baseline)
    assert {item.page for item in placed if item.line.section == "courses"} == {1}


def test_oversized_course_continues_without_repeating_heading():
    cv = CVData()
    cv.layout.main = ["courses"]
    cv.layout.side = []
    cv.courses = [Entry(
        title="Extended course",
        subtitle="Coursera",
        bullets=[f"Lesson {index:03d}" for index in range(120)],
    ), Entry(title="Next course", subtitle="Udemy")]
    with pymupdf.open(stream=render_cv_pdf(cv, DEFAULT_THEME), filetype="pdf") as doc:
        texts = [page.get_text("text") for page in doc]
        assert len(doc) > 1
        assert sum(text.count("COURSES") for text in texts) == 1
        for index in range(120):
            assert sum(text.count(f"Lesson {index:03d}") for text in texts) == 1
        assert any("Next course" in text and "Udemy" in text for text in texts)


def test_client_entry_moves_intact_below_continuation_heading():
    cv = CVData()
    cv.layout.main = ["clients"]
    cv.layout.side = []
    cv.clients = [Entry(title="Client project", subtitle="Azure and Terraform",
                        bullets=["Client delivery description. " * 8])]
    lines = build_column(cv, DEFAULT_THEME, "main")
    preceding = Line(advance=1.0, draw=lambda canvas, x, y: None)
    placed = paginate([preceding, *lines], cv, DEFAULT_THEME, "main",
                      DEFAULT_THEME.max_baseline - 90.0, DEFAULT_THEME.main_top_baseline)
    client_lines = [item for item in placed if item.line.section == "clients"]
    assert {item.page for item in client_lines} == {1}
    assert sum(item.line.is_header for item in client_lines) == 1
    assert client_lines[1].baseline >= client_lines[0].baseline + DEFAULT_THEME.section_header_to_body


def test_imported_courses_heading_typo_is_corrected():
    cv = make_cv()
    cv.headings["courses"] = "COURCES"
    text = pdf_text(render_cv_pdf(cv))
    assert "COURSES" in text and "COURCES" not in text


def test_nonbreaking_hyphens_do_not_produce_missing_pdf_glyphs():
    cv = CVData(summary="Terraform\u2011based automation and well\u2011governed operations.")
    text = pdf_text(render_cv_pdf(cv))
    assert "Terraform-based" in text and "well-governed" in text
    assert "\x00" not in text


def test_oversized_client_continues_safely_before_courses():
    cv = CVData()
    cv.layout.main = ["clients", "courses"]
    cv.layout.side = []
    cv.clients = [Entry(title="Large client", subtitle="Platform engineering",
                        bullets=[f"Delivery item {index:03d}" for index in range(120)])]
    cv.courses = [Entry(title="Following course", subtitle="Udemy")]
    lines = build_column(cv, DEFAULT_THEME, "main")
    placed = paginate(lines, cv, DEFAULT_THEME, "main",
                      DEFAULT_THEME.main_top_baseline, DEFAULT_THEME.main_top_baseline)
    assert max(item.page for item in placed) > 1
    for page in {item.page for item in placed}:
        page_lines = [item for item in placed if item.page == page]
        headers = [item for item in page_lines if item.line.is_header and item.line.section == "clients"]
        assert len(headers) <= 1
        for above, below in zip(page_lines, page_lines[1:]):
            assert below.baseline >= above.baseline + above.line.advance
        assert all(item.baseline <= DEFAULT_THEME.max_baseline for item in page_lines)
    text = pdf_text(render_cv_pdf(cv, DEFAULT_THEME))
    for index in range(120):
        assert text.count(f"Delivery item {index:03d}") == 1
    assert text.count("COURSES") == 1 and "Following course" in text
