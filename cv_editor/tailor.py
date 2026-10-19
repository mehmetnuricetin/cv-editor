"""Job-specific CV versions.

Tailoring only ever *selects, reorders or hides* content that already exists in
the master CV.  Nothing is generated, rewritten or invented, and no external
service or AI model is involved -- the relevance hints below are a static,
local keyword map used purely to pre-select checkboxes, which the user can
always override.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from .model import CVData, Entry

#: Preset roles with the local keywords used to pre-select content.
ROLE_PRESETS: Dict[str, List[str]] = {
    "Azure Cloud Engineer": [
        "azure", "entra", "active directory", "arm", "bicep", "api management",
        "update management", "backup", "monitor", "cloud",
    ],
    "DevOps Engineer": [
        "devops", "ci/cd", "pipeline", "github actions", "azure devops", "terraform",
        "automation", "git", "docker", "jenkins",
    ],
    "Platform Engineer": [
        "platform", "kubernetes", "aks", "terraform", "crossplane", "governance",
        "reliability", "topology", "automation",
    ],
    "OpenShift Administrator": [
        "openshift", "ex280", "red hat", "kubernetes", "podman", "container", "linux", "do180",
    ],
    "AI Platform Engineer": [
        "ai", "copilot", "agentic", "foundry", "openai", "machine learning", "azure ai",
        "kubernetes", "platform",
    ],
}


@dataclass
class TailorSelection:
    """What the user chose to keep for a tailored version."""

    role: str = ""
    headline: str = ""
    summary: str = ""
    skills: List[str] = field(default_factory=list)
    experience_ids: List[str] = field(default_factory=list)
    client_ids: List[str] = field(default_factory=list)
    certificate_ids: List[str] = field(default_factory=list)
    course_ids: List[str] = field(default_factory=list)
    keep_all_education: bool = True
    skills_first: bool = True


def _matches(text: str, keywords: Sequence[str]) -> bool:
    low = text.lower()
    return any(k in low for k in keywords)


def suggest_skills(cv: CVData, role: str) -> List[str]:
    keywords = ROLE_PRESETS.get(role, [])
    if not keywords:
        return list(cv.all_skills())
    hits = [s for s in cv.all_skills() if _matches(s, keywords)]
    return hits or list(cv.all_skills())


def suggest_entries(entries: Sequence[Entry], role: str) -> List[str]:
    keywords = ROLE_PRESETS.get(role, [])
    if not keywords:
        return [e.id for e in entries]
    hits = [e.id for e in entries if _matches(e.searchable(), keywords)]
    return hits or [e.id for e in entries]


def default_selection(cv: CVData, role: str) -> TailorSelection:
    return TailorSelection(
        role=role,
        headline=cv.job_title,
        summary=cv.summary,
        skills=suggest_skills(cv, role),
        experience_ids=[e.id for e in cv.experience],
        client_ids=suggest_entries(cv.clients, role),
        certificate_ids=[e.id for e in cv.certificates],
        course_ids=suggest_entries(cv.courses, role),
    )


def _filter(entries: Sequence[Entry], keep_ids: Sequence[str], prioritise: Sequence[str]) -> List[Entry]:
    keep = set(keep_ids)
    chosen = [e for e in entries if e.id in keep]
    if prioritise:
        priority = set(prioritise)
        chosen.sort(key=lambda e: 0 if e.id in priority else 1)
    return chosen


def build_tailored_cv(master: CVData, selection: TailorSelection) -> CVData:
    """Return a copy of ``master`` restricted to the selected content."""
    cv = master.clone()

    id_map = {}
    for src_list, dst_list in (
        (master.experience, cv.experience),
        (master.clients, cv.clients),
        (master.certificates, cv.certificates),
        (master.courses, cv.courses),
    ):
        for src, dst in zip(src_list, dst_list):
            id_map[dst.id] = src.id
            dst.id = src.id

    if selection.headline.strip():
        cv.job_title = selection.headline.strip()
    if selection.summary.strip():
        cv.summary = selection.summary.strip()

    keep_skills = {s.strip().casefold() for s in selection.skills if s.strip()}
    if keep_skills:
        order = {s.strip().casefold(): i for i, s in enumerate(selection.skills)}
        for category in cv.skill_categories:
            category.skills = sorted(
                [s for s in category.skills if s.strip().casefold() in keep_skills],
                key=lambda s: order.get(s.strip().casefold(), 9999),
            )
        cv.skill_categories = [c for c in cv.skill_categories if c.skills]

    cv.experience = _filter(master.experience, selection.experience_ids, [])
    cv.clients = _filter(master.clients, selection.client_ids, selection.client_ids)
    cv.certificates = _filter(master.certificates, selection.certificate_ids, [])
    cv.courses = _filter(master.courses, selection.course_ids, [])
    if not selection.keep_all_education:
        cv.education = list(master.education)

    if selection.skills_first and "skills" in cv.layout.side:
        cv.layout.side = ["skills"] + [s for s in cv.layout.side if s != "skills"]

    return cv


def validate_tailored(master: CVData, tailored: CVData) -> List[str]:
    """Guard rail: a tailored version must never contain invented content."""
    problems: List[str] = []
    master_skills = {s.strip().casefold() for s in master.all_skills()}
    for skill in tailored.all_skills():
        if skill.strip().casefold() not in master_skills:
            problems.append(f"Skill '{skill}' is not present in the master CV.")

    for label, m_list, t_list in (
        ("work experience", master.experience, tailored.experience),
        ("client project", master.clients, tailored.clients),
        ("certificate", master.certificates, tailored.certificates),
        ("course", master.courses, tailored.courses),
        ("education", master.education, tailored.education),
    ):
        titles = {e.title.strip().casefold() for e in m_list}
        for entry in t_list:
            if entry.title.strip().casefold() not in titles:
                problems.append(f"{label.capitalize()} '{entry.title}' is not present in the master CV.")
    return problems
