"""Tests for local storage and job-specific tailoring."""

from __future__ import annotations

import os

import pytest

from cv_editor import storage
from cv_editor.model import CVData, Entry
from cv_editor.storage import Project, TailoredVersion
from cv_editor.tailor import (
    ROLE_PRESETS,
    build_tailored_cv,
    default_selection,
    validate_tailored,
)
from tests.conftest import make_cv


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv(storage.APP_DIR_ENV, str(tmp_path / "CVEditor"))
    yield


def test_save_and_load_round_trip():
    project = Project(name="Round Trip", cv=make_cv())
    path = storage.save_project(project)
    assert path.exists()

    loaded = storage.load_project(path)
    assert loaded.name == "Round Trip"
    assert loaded.cv.name == project.cv.name
    assert loaded.cv.all_skills() == project.cv.all_skills()
    assert loaded.cv.experience[0].right_top == project.cv.experience[0].right_top
    assert loaded.cv.layout.main == project.cv.layout.main


def test_list_projects():
    storage.save_project(Project(name="One", cv=CVData()))
    storage.save_project(Project(name="Two", cv=CVData()))
    names = {row["name"] for row in storage.list_projects()}
    assert {"One", "Two"} <= names


def test_original_pdf_is_preserved_read_only():
    from cv_editor.render import render_cv_pdf

    raw = render_cv_pdf(make_cv())
    first = storage.store_original(raw, "nuri_cv.pdf")
    second = storage.store_original(raw, "nuri_cv.pdf")
    assert first != second, "an existing original must never be overwritten"
    assert first.read_bytes() == raw
    assert not os.access(first, os.W_OK)


def test_export_never_overwrites():
    a = storage.save_export(b"%PDF-1.4 a", "cv.pdf")
    b = storage.save_export(b"%PDF-1.4 b", "cv.pdf")
    assert a != b
    assert a.read_bytes() == b"%PDF-1.4 a"


def test_backup_zip_round_trip():
    from cv_editor.render import render_cv_pdf

    project = Project(name="Backup Me", cv=make_cv())
    project.original_pdf = str(storage.store_original(render_cv_pdf(make_cv()), "orig.pdf"))
    blob = storage.backup_zip(project)
    restored = storage.restore_from_zip(blob)
    assert restored.name == "Backup Me"
    assert restored.cv.name == project.cv.name


def test_invalid_project_file_raises():
    with pytest.raises(storage.StorageError):
        storage.load_project_bytes(b"not json")


# ---------------------------------------------------------------------------
# tailoring
# ---------------------------------------------------------------------------

def test_tailoring_only_keeps_existing_content():
    master = make_cv()
    selection = default_selection(master, "OpenShift Administrator")
    tailored = build_tailored_cv(master, selection)
    assert validate_tailored(master, tailored) == []
    assert set(tailored.all_skills()) <= set(master.all_skills())
    titles = {e.title for e in master.experience}
    assert {e.title for e in tailored.experience} <= titles


def test_tailoring_leaves_the_master_untouched():
    master = make_cv()
    before = master.to_dict()
    selection = default_selection(master, "DevOps Engineer")
    selection.skills = ["Terraform"]
    selection.client_ids = []
    build_tailored_cv(master, selection)
    assert master.to_dict() == before


def test_tailoring_filters_skills_and_entries():
    master = make_cv()
    selection = default_selection(master, "Platform Engineer")
    selection.skills = ["Kubernetes", "Terraform"]
    selection.client_ids = []
    tailored = build_tailored_cv(master, selection)
    assert sorted(tailored.all_skills()) == ["Kubernetes", "Terraform"]
    assert tailored.clients == []


def test_all_role_presets_produce_a_valid_cv():
    master = make_cv()
    for role in ROLE_PRESETS:
        tailored = build_tailored_cv(master, default_selection(master, role))
        assert validate_tailored(master, tailored) == []
        assert tailored.name == master.name


def test_validate_tailored_detects_invented_content():
    master = make_cv()
    tailored = master.clone()
    tailored.skill_categories[0].skills.append("Quantum Kubernetes")
    tailored.experience.append(Entry(title="Chief Astronaut"))
    problems = validate_tailored(master, tailored)
    assert any("Quantum Kubernetes" in p for p in problems)
    assert any("Chief Astronaut" in p for p in problems)


def test_tailored_version_serialises_inside_a_project():
    master = make_cv()
    tailored = build_tailored_cv(master, default_selection(master, "Azure Cloud Engineer"))
    project = Project(name="With Versions", cv=master,
                      versions=[TailoredVersion(name="Azure", role="Azure Cloud Engineer", cv=tailored)])
    path = storage.save_project(project)
    loaded = storage.load_project(path)
    assert len(loaded.versions) == 1
    assert loaded.versions[0].cv is not None
    assert loaded.versions[0].cv.all_skills() == tailored.all_skills()
