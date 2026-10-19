"""Lightweight, non-blocking content validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from .model import CVData

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.]+$")


@dataclass
class Issue:
    level: str   # "error" | "warning" | "info"
    section: str
    message: str


def validate_cv(cv: CVData) -> List[Issue]:
    issues: List[Issue] = []

    if not cv.name.strip():
        issues.append(Issue("error", "Contact", "Name is empty."))
    if not cv.job_title.strip():
        issues.append(Issue("warning", "Contact", "Professional title is empty."))
    if not cv.contact.email.strip():
        issues.append(Issue("warning", "Contact", "No email address."))
    elif not EMAIL_RE.match(cv.contact.email.strip()):
        issues.append(Issue("error", "Contact", f"'{cv.contact.email}' does not look like an email address."))
    if not cv.contact.phone.strip():
        issues.append(Issue("info", "Contact", "No phone number."))

    if not cv.summary.strip():
        issues.append(Issue("warning", "Summary", "Professional summary is empty."))
    elif len(cv.summary.split()) > 220:
        issues.append(Issue("info", "Summary", "The summary is long and may push other content onto a new page."))

    skills = [s.strip() for s in cv.all_skills() if s.strip()]
    if not skills:
        issues.append(Issue("warning", "Skills", "No skills added."))
    seen = {}
    for skill in skills:
        key = skill.casefold()
        seen[key] = seen.get(key, 0) + 1
    duplicates = sorted(k for k, v in seen.items() if v > 1)
    if duplicates:
        issues.append(Issue("error", "Skills", "Duplicate skills: " + ", ".join(duplicates)))

    empty_categories = [c.name for c in cv.skill_categories if not [s for s in c.skills if s.strip()]]
    if empty_categories:
        issues.append(
            Issue("info", "Skills", "Empty categories are not exported: " + ", ".join(empty_categories))
        )

    for label, entries in (
        ("Work experience", cv.experience),
        ("Client projects", cv.clients),
        ("Education", cv.education),
        ("Certificates", cv.certificates),
        ("Courses", cv.courses),
    ):
        for i, entry in enumerate(entries, start=1):
            if not entry.title.strip():
                issues.append(Issue("error", label, f"Entry {i} has no title and will be hard to read."))
            if entry.is_empty():
                issues.append(Issue("warning", label, f"Entry {i} is empty and will be skipped on export."))

    if not cv.layout.main and not cv.layout.side:
        issues.append(Issue("error", "Layout", "No sections are assigned to a column."))

    return issues


def summarise(issues: List[Issue]) -> str:
    errors = sum(1 for i in issues if i.level == "error")
    warnings = sum(1 for i in issues if i.level == "warning")
    if errors:
        return f"{errors} error(s), {warnings} warning(s)"
    if warnings:
        return f"{warnings} warning(s)"
    return "No issues"
