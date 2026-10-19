"""Tests for PDF content extraction."""

from __future__ import annotations

import pymupdf
import pytest

from cv_editor.extract import (
    ExtractionError,
    _canonical_section,
    _join_wrapped,
    analyse_pdf,
    categorise_skills,
    extract_cv,
)
from cv_editor.model import (
    SEC_CERTIFICATES,
    SEC_CLIENTS,
    SEC_COURSES,
    SEC_EDUCATION,
    SEC_EXPERIENCE,
    SEC_INTERESTS,
    SEC_LANGUAGES,
    SEC_SKILLS,
    SEC_SUMMARY,
)


def test_section_heading_mapping():
    assert _canonical_section("WORK EXPERIENCE") == SEC_EXPERIENCE
    assert _canonical_section("SELECTED CLIENT EXPERIENCE") == SEC_CLIENTS
    assert _canonical_section("TECHNICAL SKILLS") == SEC_SKILLS
    assert _canonical_section("CERTIFICATES") == SEC_CERTIFICATES
    assert _canonical_section("COURCES") == SEC_COURSES  # typo in the original CV
    assert _canonical_section("LANGUAGES") == SEC_LANGUAGES
    assert _canonical_section("INTERESTS") == SEC_INTERESTS
    assert _canonical_section("EDUCATION") == SEC_EDUCATION
    assert _canonical_section("SUMMARY") == SEC_SUMMARY
    assert _canonical_section("RANDOM HEADING") is None


def test_join_wrapped_keeps_real_hyphens():
    assert _join_wrapped(["Building Cloud-", "native Applications"]) == "Building Cloud-native Applications"
    assert _join_wrapped(["Supported Azure cloud", "and DevOps"]) == "Supported Azure cloud and DevOps"
    assert _join_wrapped(["", "  ", "Only"]) == "Only"


def test_categorise_skills_is_deterministic_and_local():
    cats = categorise_skills(["Azure", "Terraform", "Kubernetes", "GitHub Copilot", "Linux", "Zzz"])
    mapping = {c.name: c.skills for c in cats}
    assert "Azure" in mapping["Cloud Platforms"]
    assert "Terraform" in mapping["Infrastructure as Code"]
    assert "Kubernetes" in mapping["Containers and Kubernetes"]
    assert "GitHub Copilot" in mapping["AI and Agentic AI"]
    assert "Linux" in mapping["Operating Systems and Scripting"]
    assert "Zzz" in mapping["Other"]
    # no skill is lost or duplicated
    flat = [s for c in cats for s in c.skills]
    assert sorted(flat) == sorted(["Azure", "Terraform", "Kubernetes", "GitHub Copilot", "Linux", "Zzz"])


def test_extract_round_trip(sample_pdf_bytes):
    result = extract_cv(sample_pdf_bytes)
    cv = result.cv

    assert cv.name == "NURI CETIN"
    assert cv.job_title == "Cloud Devops Engineer"
    assert cv.contact.email == "mehmetnuricetin@gmail.com"
    assert cv.contact.phone.replace(" ", "") == "+46735916734"
    assert "linkedin.com/in/m-nuri-cetin" in cv.contact.linkedin
    assert "github.com/mehmetnuricetin" in cv.contact.github

    assert "Cloud DevOps Engineer with experience" in cv.summary
    assert {s.casefold() for s in cv.all_skills()} >= {"azure", "terraform", "kubernetes"}
    assert cv.languages == ["English", "Swedish", "Turkish"]
    assert cv.interests == ["Film Making", "Music"]


def test_extract_columns_and_layout(sample_pdf_bytes):
    result = extract_cv(sample_pdf_bytes)
    assert SEC_SUMMARY in result.cv.layout.main
    assert SEC_EXPERIENCE in result.cv.layout.main
    assert SEC_SKILLS in result.cv.layout.side
    assert SEC_EDUCATION in result.cv.layout.side


def test_extract_entries_keep_structure(sample_pdf_bytes):
    cv = extract_cv(sample_pdf_bytes).cv

    job = cv.experience[0]
    assert job.title == "Cloud Devops Engineer"
    assert job.right_top == "Aug 2025 - Present"
    assert job.subtitle == "Vivicta"
    assert job.right_sub == "Sweden"
    assert job.bullets and "infrastructure automation" in job.bullets[0]

    client = cv.clients[0]
    assert client.title == "AIBEL"
    assert client.right_top == "Cloud / Platform Engineering"

    education = cv.education[0]
    assert education.subtitle == "Lernia Yrkeshögskola"
    assert education.right_third == "Sep 2021 - Jun 2023"

    assert cv.certificates[0].subtitle == "Microsoft"
    assert cv.courses[0].title == "Master Azure Bicep"


def test_warns_about_pages_without_text():
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    blank = doc.tobytes()
    doc.close()
    warnings = analyse_pdf(blank)
    assert any("empty" in w.lower() for w in warnings)


def test_empty_pdf_raises_extraction_error():
    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    blank = doc.tobytes()
    doc.close()
    with pytest.raises(ExtractionError):
        extract_cv(blank)
