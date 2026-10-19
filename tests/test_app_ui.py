"""Interaction tests for the Streamlit UI.

These drive the real app through Streamlit's AppTest harness, which executes
``app.py`` exactly as the browser would.  They cover the add / edit / delete /
reorder workflow and the "added skills end up in the exported PDF" requirement.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from cv_editor.render import pdf_text

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
TIMEOUT = 240


def _app(cv, page):
    at = AppTest.from_file(APP, default_timeout=TIMEOUT)
    at.session_state["nav"] = page
    at.run()
    at.session_state.project.cv = copy.deepcopy(cv)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_every_page_renders(sample_cv):
    pages = [
        "Upload & original", "Contact & title", "Summary", "Skills",
        "Work experience", "Client projects", "Education", "Certificates",
        "Courses", "Languages & interests", "Layout & design",
        "Preview & export", "Tailored versions", "Project & backup",
    ]
    for page in pages:
        at = _app(sample_cv, page)
        assert not at.exception, f"{page}: {[e.value for e in at.exception]}"


def test_add_skill_appears_in_exported_pdf(sample_cv):
    from cv_editor.ui.common import build_pdf

    at = _app(sample_cv, "Skills")
    settings = at.session_state.project.render_settings
    before = build_pdf(at.session_state.project.cv, settings)
    assert "Azure AI Foundry" not in pdf_text(before)
    at.text_input(key="sk_new").set_value("Azure AI Foundry")
    at.button(key="sk_add").click().run()

    assert not at.exception, [e.value for e in at.exception]
    data = at.session_state.project.cv
    assert "Azure AI Foundry" in data.all_skills()
    # the input is cleared so the next skill can be typed straight away
    assert at.text_input(key="sk_new").value == ""

    assert "Azure AI Foundry" in pdf_text(build_pdf(data, settings))


def test_duplicate_skill_is_rejected_case_insensitively(sample_cv):
    at = _app(sample_cv, "Skills")
    at.text_input(key="sk_new").set_value("Terraform Cloud")
    at.button(key="sk_add").click().run()
    count = len(at.session_state.project.cv.all_skills())

    at.text_input(key="sk_new").set_value("terraform cloud")
    at.button(key="sk_add").click().run()

    assert len(at.session_state.project.cv.all_skills()) == count
    assert any("already in your skills" in w.value for w in at.warning)


def test_skill_reorder_and_delete_are_not_undone_by_stale_widgets(sample_cv):
    """Regression: widgets keyed by list index used to write their old value
    back over the model, silently reverting a move."""
    at = _app(sample_cv, "Skills")
    cat = at.session_state.project.cv.skill_categories[0]
    first, second = cat.skills[0], cat.skills[1]

    at.button(key=f"sk_dn_{cat.id}_0").click().run()
    skills = at.session_state.project.cv.skill_categories[0].skills
    assert skills[0] == second and skills[1] == first

    at.button(key=f"sk_up_{cat.id}_1").click().run()
    skills = at.session_state.project.cv.skill_categories[0].skills
    assert skills[0] == first and skills[1] == second

    remaining = list(skills[1:])
    at.button(key=f"sk_rm_{cat.id}_0").click().run()
    assert at.session_state.project.cv.skill_categories[0].skills == remaining


def test_bullet_add_reorder_and_delete(sample_cv):
    """Regression: deleting a bullet used to raise IndexError because the
    render loop kept going with stale indices."""
    at = _app(sample_cv, "Work experience")
    entry = at.session_state.project.cv.experience[0]
    original = entry.bullets[0]

    at.button(key=f"en_{entry.id}_addb").click().run()
    at.text_area(key=f"en_{entry.id}_b1").set_value("Second bullet.")
    at.run()
    bullets = lambda: at.session_state.project.cv.experience[0].bullets  # noqa: E731
    assert bullets() == [original, "Second bullet."]

    at.button(key=f"en_{entry.id}_bd0").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert bullets() == ["Second bullet.", original]

    at.button(key=f"en_{entry.id}_bx0").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert bullets() == [original]


def test_entry_reorder_and_delete(sample_cv):
    at = _app(sample_cv, "Work experience")
    entries = lambda: at.session_state.project.cv.experience  # noqa: E731
    first, second = entries()[0].title, entries()[1].title

    at.button(key=f"en_ctrl_{entries()[0].id}_down").click().run()
    assert entries()[0].title == second and entries()[1].title == first

    count = len(entries())
    at.button(key=f"en_ctrl_{entries()[0].id}_del").click().run()
    assert len(entries()) == count - 1
    assert entries()[0].title == first


def test_simple_list_add_and_reorder(sample_cv):
    at = _app(sample_cv, "Languages & interests")
    at.text_input(key="li_new_languages").set_value("Turkish (Native)")
    at.button(key="li_add_languages").click().run()

    values = lambda: at.session_state.project.cv.languages  # noqa: E731
    assert "Turkish (Native)" in values()
    assert at.text_input(key="li_new_languages").value == ""

    first, second = values()[0], values()[1]
    at.button(key="li_dn_languages_0").click().run()
    assert values()[0] == second and values()[1] == first


def test_saved_project_is_not_reported_as_dirty(tmp_path, monkeypatch, sample_cv):
    """Navigating after a save must not mark the project unsaved again."""
    at = _app(sample_cv, "Skills")
    at.text_input(key="sk_new").set_value("Azure AI Foundry")
    at.button(key="sk_add").click().run()
    assert any("Unsaved" in c.value for c in at.caption)

    at.button(key="side_save").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("All changes saved" in c.value for c in at.caption)

    for page in ("Summary", "Work experience", "Languages & interests"):
        at.session_state["nav"] = page
        at.run()
        assert any("All changes saved" in c.value for c in at.caption), page
