import copy

import pytest

from cv_editor.model import CVData, Contact, Entry, SkillCategory


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Keep every test out of the real ~/CVEditor directory."""
    monkeypatch.setenv("CV_EDITOR_HOME", str(tmp_path / "CVEditor"))


@pytest.fixture
def sample_cv() -> CVData:
    """A CV with enough entries to exercise reorder / delete controls."""
    cv = copy.deepcopy(make_cv())
    cv.experience.append(
        Entry(
            title="AWS Technical Specialist",
            right_top="Nov 2022 - Aug 2023",
            subtitle="Volkswagen Finans Sverige",
            right_sub="Sweden",
            bullets=["Supported AWS infrastructure and CI/CD pipelines."],
        )
    )
    return cv


@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    """Render a CV with the app itself and use it as a round-trip fixture.

    This keeps the test suite self-contained: it does not depend on a personal
    CV being present on the machine.
    """
    from cv_editor.render import render_cv_pdf

    return render_cv_pdf(make_cv())


def make_cv() -> CVData:
    cv = CVData(
        name="NURI CETIN",
        job_title="Cloud Devops Engineer",
        contact=Contact(
            phone="+46735916734",
            email="mehmetnuricetin@gmail.com",
            linkedin="www.linkedin.com/in/m-nuri-cetin",
            github="https://github.com/mehmetnuricetin",
            location="Sweden",
        ),
        summary=(
            "Cloud DevOps Engineer with experience delivering secure, automated, and scalable "
            "infrastructure solutions across Azure and OpenShift environments. Skilled in "
            "infrastructure-as-code using Terraform, PowerShell, and GitHub Actions."
        ),
        skill_categories=[
            SkillCategory(name="Cloud Platforms", skills=["Azure", "AWS"]),
            SkillCategory(name="Infrastructure as Code", skills=["Terraform", "Crossplane"]),
            SkillCategory(name="Containers and Kubernetes", skills=["Kubernetes", "OpenShift", "Podman"]),
        ],
        languages=["English", "Swedish", "Turkish"],
        interests=["Film Making", "Music"],
    )
    cv.experience.append(
        Entry(
            title="Cloud Devops Engineer",
            right_top="Aug 2025 - Present",
            subtitle="Vivicta",
            right_sub="Sweden",
            bullets=[
                "Supported Azure cloud and DevOps environments, focusing on infrastructure "
                "automation, CI/CD, cloud operations, and platform reliability."
            ],
        )
    )
    cv.clients.append(
        Entry(
            title="AIBEL",
            right_top="Cloud / Platform Engineering",
            subtitle="Azure · Terraform · Kubernetes",
            bullets=["Managed and improved Kubernetes clusters and Azure platform architecture."],
        )
    )
    cv.education.append(
        Entry(
            title="Cloud & IT-Infrastructure Engineer",
            subtitle="Lernia Yrkeshögskola",
            third="Sweden",
            right_third="Sep 2021 - Jun 2023",
        )
    )
    cv.certificates.append(
        Entry(title="Microsoft Certified: Azure Administrator Associate", subtitle="Microsoft")
    )
    cv.courses.append(Entry(title="Master Azure Bicep", subtitle="Udemy"))
    return cv
