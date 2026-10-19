"""Data model for the CV project.

Everything the user edits lives in :class:`CVData`.  The model is plain
dataclasses so it serialises to / from JSON without any extra machinery.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List

SCHEMA_VERSION = 1

# Section identifiers used throughout the app.
SEC_SUMMARY = "summary"
SEC_EXPERIENCE = "experience"
SEC_CLIENTS = "clients"
SEC_COURSES = "courses"
SEC_SKILLS = "skills"
SEC_EDUCATION = "education"
SEC_CERTIFICATES = "certificates"
SEC_LANGUAGES = "languages"
SEC_INTERESTS = "interests"

ENTRY_SECTIONS = (SEC_EXPERIENCE, SEC_CLIENTS, SEC_COURSES, SEC_EDUCATION, SEC_CERTIFICATES)
LIST_SECTIONS = (SEC_LANGUAGES, SEC_INTERESTS)

ALL_SECTIONS = (
    SEC_SUMMARY,
    SEC_EXPERIENCE,
    SEC_CLIENTS,
    SEC_COURSES,
    SEC_SKILLS,
    SEC_EDUCATION,
    SEC_CERTIFICATES,
    SEC_LANGUAGES,
    SEC_INTERESTS,
)

DEFAULT_HEADINGS: Dict[str, str] = {
    SEC_SUMMARY: "SUMMARY",
    SEC_EXPERIENCE: "WORK EXPERIENCE",
    SEC_CLIENTS: "SELECTED CLIENT EXPERIENCE",
    SEC_COURSES: "COURSES",
    SEC_SKILLS: "SKILLS",
    SEC_EDUCATION: "EDUCATION",
    SEC_CERTIFICATES: "CERTIFICATES",
    SEC_LANGUAGES: "LANGUAGES",
    SEC_INTERESTS: "INTERESTS",
}

#: Per-section labels for the generic entry fields, used by the Streamlit UI.
ENTRY_FIELD_LABELS: Dict[str, Dict[str, str]] = {
    SEC_EXPERIENCE: {
        "title": "Job title",
        "right_top": "Period",
        "subtitle": "Company",
        "right_sub": "Location",
        "third": "",
        "right_third": "",
    },
    SEC_CLIENTS: {
        "title": "Client",
        "right_top": "Role / category",
        "subtitle": "Tech stack",
        "right_sub": "",
        "third": "",
        "right_third": "",
    },
    SEC_EDUCATION: {
        "title": "Programme / degree",
        "right_top": "",
        "subtitle": "School",
        "right_sub": "",
        "third": "Country",
        "right_third": "Period",
    },
    SEC_CERTIFICATES: {
        "title": "Certificate",
        "right_top": "",
        "subtitle": "Issuer",
        "right_sub": "",
        "third": "",
        "right_third": "",
    },
    SEC_COURSES: {
        "title": "Course",
        "right_top": "",
        "subtitle": "Provider",
        "right_sub": "",
        "third": "",
        "right_third": "",
    },
}

#: Suggested skill categories for a Cloud / DevOps profile.
DEFAULT_SKILL_CATEGORIES = [
    "Cloud Platforms",
    "Infrastructure as Code",
    "Containers and Kubernetes",
    "CI/CD and Automation",
    "Monitoring and Security",
    "AI and Agentic AI",
    "Operating Systems and Scripting",
]


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Contact:
    phone: str = ""
    email: str = ""
    linkedin: str = ""
    github: str = ""
    location: str = ""
    website: str = ""

    def as_items(self) -> List[tuple]:
        """Return ``(icon, text)`` pairs in the order used by the original CV."""
        items = []
        if self.phone:
            items.append(("phone", self.phone))
        if self.email:
            items.append(("email", self.email))
        if self.linkedin:
            items.append(("linkedin", self.linkedin))
        if self.location:
            items.append(("location", self.location))
        if self.github:
            items.append(("github", self.github))
        if self.website:
            items.append(("web", self.website))
        return items


@dataclass
class Entry:
    """A generic CV entry.

    The same shape covers jobs, client projects, education, certificates and
    courses; only the labels and which rows are populated differ.
    """

    title: str = ""
    right_top: str = ""
    subtitle: str = ""
    right_sub: str = ""
    third: str = ""
    right_third: str = ""
    bullets: List[str] = field(default_factory=list)
    id: str = field(default_factory=_new_id)

    def is_empty(self) -> bool:
        return not any(
            [self.title, self.subtitle, self.third, self.right_top, self.right_sub, self.right_third]
        ) and not [b for b in self.bullets if b.strip()]

    def searchable(self) -> str:
        return " ".join([self.title, self.subtitle, self.right_top, self.right_sub, *self.bullets]).lower()


@dataclass
class SkillCategory:
    name: str = ""
    skills: List[str] = field(default_factory=list)
    id: str = field(default_factory=_new_id)


@dataclass
class LayoutConfig:
    """Which sections live in which column, and in which order."""

    main: List[str] = field(
        default_factory=lambda: [SEC_SUMMARY, SEC_EXPERIENCE, SEC_CLIENTS, SEC_COURSES]
    )
    side: List[str] = field(
        default_factory=lambda: [SEC_SKILLS, SEC_EDUCATION, SEC_CERTIFICATES, SEC_LANGUAGES, SEC_INTERESTS]
    )
    #: Print skill category names as sub-headings in the sidebar.
    show_skill_categories: bool = False
    #: Repeat the section heading when a section continues onto a new page.
    repeat_section_headings: bool = True

    def ordered_sections(self) -> List[str]:
        return list(self.main) + list(self.side)


@dataclass
class CVData:
    name: str = ""
    job_title: str = ""
    contact: Contact = field(default_factory=Contact)
    summary: str = ""
    skill_categories: List[SkillCategory] = field(default_factory=list)
    experience: List[Entry] = field(default_factory=list)
    clients: List[Entry] = field(default_factory=list)
    education: List[Entry] = field(default_factory=list)
    certificates: List[Entry] = field(default_factory=list)
    courses: List[Entry] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    interests: List[str] = field(default_factory=list)
    headings: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_HEADINGS))
    layout: LayoutConfig = field(default_factory=LayoutConfig)

    # -- skills helpers -------------------------------------------------
    def all_skills(self) -> List[str]:
        out: List[str] = []
        for cat in self.skill_categories:
            out.extend(cat.skills)
        return out

    def has_skill(self, skill: str) -> bool:
        target = skill.strip().casefold()
        return any(s.strip().casefold() == target for s in self.all_skills())

    def entries_for(self, section: str) -> List[Entry]:
        return {
            SEC_EXPERIENCE: self.experience,
            SEC_CLIENTS: self.clients,
            SEC_EDUCATION: self.education,
            SEC_CERTIFICATES: self.certificates,
            SEC_COURSES: self.courses,
        }[section]

    def simple_list_for(self, section: str) -> List[str]:
        return {SEC_LANGUAGES: self.languages, SEC_INTERESTS: self.interests}[section]

    def heading(self, section: str) -> str:
        heading = self.headings.get(section) or DEFAULT_HEADINGS.get(section, section.upper())
        if section == SEC_COURSES and heading.strip().upper() == "COURCES":
            return DEFAULT_HEADINGS[SEC_COURSES]
        return heading

    # -- serialisation --------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["schema_version"] = SCHEMA_VERSION
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CVData":
        data = dict(data or {})
        data.pop("schema_version", None)
        contact = Contact(**{k: v for k, v in (data.pop("contact", {}) or {}).items() if k in Contact.__annotations__})

        def _entries(key: str) -> List[Entry]:
            out = []
            for raw in data.pop(key, []) or []:
                raw = {k: v for k, v in raw.items() if k in Entry.__annotations__}
                raw.setdefault("id", _new_id())
                raw["bullets"] = list(raw.get("bullets") or [])
                out.append(Entry(**raw))
            return out

        cats = []
        for raw in data.pop("skill_categories", []) or []:
            cats.append(
                SkillCategory(
                    name=raw.get("name", ""),
                    skills=list(raw.get("skills") or []),
                    id=raw.get("id") or _new_id(),
                )
            )

        layout_raw = data.pop("layout", None) or {}
        layout = LayoutConfig(
            main=list(layout_raw.get("main") or LayoutConfig().main),
            side=list(layout_raw.get("side") or LayoutConfig().side),
            show_skill_categories=bool(layout_raw.get("show_skill_categories", False)),
            repeat_section_headings=bool(layout_raw.get("repeat_section_headings", True)),
        )

        headings = dict(DEFAULT_HEADINGS)
        headings.update(data.pop("headings", {}) or {})

        return cls(
            name=data.get("name", ""),
            job_title=data.get("job_title", ""),
            contact=contact,
            summary=data.get("summary", ""),
            skill_categories=cats,
            experience=_entries("experience"),
            clients=_entries("clients"),
            education=_entries("education"),
            certificates=_entries("certificates"),
            courses=_entries("courses"),
            languages=list(data.get("languages") or []),
            interests=list(data.get("interests") or []),
            headings=headings,
            layout=layout,
        )

    def clone(self) -> "CVData":
        return CVData.from_dict(self.to_dict())
