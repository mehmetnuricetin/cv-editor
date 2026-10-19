"""Local PDF CV editor - Streamlit application.

Run with::

    ./run.sh          # or: streamlit run app.py

Everything happens on this machine: no network calls, no cloud services and no
AI models are used at any point.
"""

from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cv_editor import storage
from cv_editor.extract import ExtractionError, extract_cv
from cv_editor.fonts import DEFAULT_FAMILY, available_families
from cv_editor.model import (
    ALL_SECTIONS,
    DEFAULT_HEADINGS,
    SEC_CERTIFICATES,
    SEC_CLIENTS,
    SEC_COURSES,
    SEC_EDUCATION,
    SEC_EXPERIENCE,
    SEC_SKILLS,
    SEC_SUMMARY,
    CVData,
)
from cv_editor.render import RenderError
from cv_editor.storage import Project, TailoredVersion
from cv_editor.tailor import (
    ROLE_PRESETS,
    TailorSelection,
    build_tailored_cv,
    default_selection,
    validate_tailored,
)
from cv_editor.ui.common import (
    build_pdf,
    cv,
    is_dirty,
    mark_saved,
    move,
    project,
    reset_widget_state,
    show_pdf,
    touch,
)
from cv_editor.ui.sections import (
    page_contact,
    page_entries,
    page_languages_interests,
    page_skills,
    page_summary,
)
from cv_editor.validate import summarise, validate_cv

st.set_page_config(page_title="CV Editor", page_icon="📄", layout="wide")

DEFAULT_SETTINGS = {
    "font_family": DEFAULT_FAMILY,
    "body_size": 10.5,
    "line_spacing": 1.0,
    "section_spacing": 1.0,
    "preview_dpi": 110,
}

PAGES = [
    "Upload & original",
    "Contact & title",
    "Summary",
    "Skills",
    "Work experience",
    "Client projects",
    "Education",
    "Certificates",
    "Courses",
    "Languages & interests",
    "Layout & design",
    "Preview & export",
    "Tailored versions",
    "Project & backup",
]


# ---------------------------------------------------------------------------
# session bootstrap
# ---------------------------------------------------------------------------

def init_state() -> None:
    if "project" not in st.session_state:
        st.session_state.project = Project(name="My CV", cv=CVData())
    if "unsaved" not in st.session_state:
        st.session_state.unsaved = False
    if "original_pdf_bytes" not in st.session_state:
        st.session_state.original_pdf_bytes = None
    if "extraction_warnings" not in st.session_state:
        st.session_state.extraction_warnings = []
    if "raw_text" not in st.session_state:
        st.session_state.raw_text = ""
    settings = st.session_state.project.render_settings
    for key, value in DEFAULT_SETTINGS.items():
        settings.setdefault(key, value)


def settings() -> Dict:
    return st.session_state.project.render_settings


def load_original_bytes() -> bytes | None:
    if st.session_state.original_pdf_bytes:
        return st.session_state.original_pdf_bytes
    path = project().original_pdf
    if path and Path(path).exists():
        st.session_state.original_pdf_bytes = Path(path).read_bytes()
        return st.session_state.original_pdf_bytes
    return None


def current_pdf() -> bytes | None:
    try:
        return build_pdf(cv(), settings())
    except RenderError as exc:
        st.error(f"The CV could not be laid out: {exc}")
    except Exception as exc:  # pragma: no cover - defensive UI path
        st.error(f"Unexpected error while generating the PDF: {exc}")
    return None


# ---------------------------------------------------------------------------
# pages
# ---------------------------------------------------------------------------

def page_upload() -> None:
    st.subheader("Upload your CV")
    st.caption(
        "The uploaded file is copied to a read-only backup folder and is never modified. "
        "Extraction happens entirely on this machine."
    )

    uploaded = st.file_uploader("PDF CV", type=["pdf"], key="uploader")
    c1, c2 = st.columns([1, 3])
    replace = c2.checkbox(
        "Replace the content I am editing", value=True,
        help="Uncheck to only preview the PDF without touching your current edits.",
    )

    if uploaded is not None and c1.button("Extract content", type="primary"):
        raw = uploaded.getvalue()
        try:
            original_path = storage.store_original(raw, uploaded.name)
        except OSError as exc:
            st.error(f"Could not save a backup of the original: {exc}")
            return
        st.session_state.original_pdf_bytes = raw
        project().original_pdf = str(original_path)
        project().original_filename = uploaded.name

        if replace:
            try:
                result = extract_cv(raw)
            except ExtractionError as exc:
                st.error(
                    f"{exc} If this PDF is a scan, the text cannot be read automatically - "
                    "you can still type the content into the editors."
                )
                return
            except Exception as exc:  # pragma: no cover - defensive UI path
                st.error(f"Extraction failed: {exc}")
                return

            reset_widget_state()
            project().cv = result.cv
            if project().name in ("", "My CV") and result.cv.name:
                project().name = f"{result.cv.name} CV"
            st.session_state.extraction_warnings = result.warnings
            st.session_state.raw_text = result.raw_text
            touch()
            st.success(
                f"Extracted {result.page_count} page(s): "
                + ", ".join(DEFAULT_HEADINGS.get(s, s) for s in result.sections_found)
            )
        else:
            st.success("Original stored. Your current content was left untouched.")
        st.rerun()

    for warning in st.session_state.extraction_warnings:
        st.warning(warning)

    if project().original_pdf:
        st.info(f"Original preserved at: `{project().original_pdf}` (read-only)")

    original = load_original_bytes()
    if original:
        left, right = st.columns(2)
        with left:
            st.markdown("#### Original PDF")
            show_pdf(original, dpi=settings()["preview_dpi"], caption_prefix="Original page")
        with right:
            st.markdown("#### Rebuilt from your edits")
            pdf = current_pdf()
            if pdf:
                show_pdf(pdf, dpi=settings()["preview_dpi"], caption_prefix="New page")

    if st.session_state.raw_text:
        with st.expander("Raw extracted text (use this to copy anything the parser missed)"):
            st.text_area("Raw text", st.session_state.raw_text, height=400, key="f_rawtext")


def page_layout() -> None:
    data = cv()
    st.subheader("Layout & design")
    st.caption(
        "The template reproduces the grid of your original CV: a white main column and a grey "
        "sidebar, with the same margins, rules and spacing."
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Main column (left)**")
        for i, section in enumerate(list(data.layout.main)):
            r1, r2, r3, r4 = st.columns([4, 1, 1, 1])
            r1.write(data.heading(section))
            if r2.button("↑", key=f"lay_mu_{section}", disabled=i == 0, width="stretch"):
                move(data.layout.main, i, -1)
                touch()
                st.rerun()
            if r3.button("↓", key=f"lay_md_{section}", disabled=i == len(data.layout.main) - 1,
                         width="stretch"):
                move(data.layout.main, i, 1)
                touch()
                st.rerun()
            if r4.button("→", key=f"lay_mv_{section}", width="stretch", help="Move to sidebar"):
                data.layout.main.remove(section)
                data.layout.side.append(section)
                touch()
                st.rerun()
    with c2:
        st.markdown("**Sidebar (right, grey)**")
        for i, section in enumerate(list(data.layout.side)):
            r1, r2, r3, r4 = st.columns([4, 1, 1, 1])
            r1.write(data.heading(section))
            if r2.button("↑", key=f"lay_su_{section}", disabled=i == 0, width="stretch"):
                move(data.layout.side, i, -1)
                touch()
                st.rerun()
            if r3.button("↓", key=f"lay_sd_{section}", disabled=i == len(data.layout.side) - 1,
                         width="stretch"):
                move(data.layout.side, i, 1)
                touch()
                st.rerun()
            if r4.button("←", key=f"lay_sv_{section}", width="stretch", help="Move to main column"):
                data.layout.side.remove(section)
                data.layout.main.append(section)
                touch()
                st.rerun()

    missing = [s for s in ALL_SECTIONS if s not in data.layout.main + data.layout.side]
    if missing:
        st.markdown("**Not shown**")
        for section in missing:
            c1, c2, c3 = st.columns([4, 1, 1])
            c1.write(data.heading(section))
            if c2.button("Add to main", key=f"lay_am_{section}"):
                data.layout.main.append(section)
                touch()
                st.rerun()
            if c3.button("Add to sidebar", key=f"lay_as_{section}"):
                data.layout.side.append(section)
                touch()
                st.rerun()

    st.divider()
    data.layout.show_skill_categories = st.checkbox(
        "Show skill category headings in the PDF",
        value=data.layout.show_skill_categories,
        help="Off reproduces the original flat bullet list.",
        key="lay_showcats",
    )
    data.layout.repeat_section_headings = st.checkbox(
        "Repeat a section heading when it continues on the next page",
        value=data.layout.repeat_section_headings,
        key="lay_repeat",
    )

    st.divider()
    st.markdown("**Typography**")
    families = available_families()
    current = settings().get("font_family", DEFAULT_FAMILY)
    if current not in families:
        current = families[0]
    c1, c2, c3 = st.columns(3)
    settings()["font_family"] = c1.selectbox(
        "Font family", families, index=families.index(current), key="lay_font",
        help="Charter is the closest match to the typeface in your original CV.",
    )
    settings()["body_size"] = c2.slider("Body text size (pt)", 9.0, 12.0,
                                        float(settings()["body_size"]), 0.25, key="lay_size")
    settings()["line_spacing"] = c3.slider("Line spacing", 0.85, 1.25,
                                           float(settings()["line_spacing"]), 0.05, key="lay_ls")
    settings()["section_spacing"] = st.slider("Spacing between entries and sections", 0.7, 1.4,
                                              float(settings()["section_spacing"]), 0.05, key="lay_ss")
    touch()


def page_preview() -> None:
    st.subheader("Preview & export")
    pdf = current_pdf()
    if not pdf:
        return

    import pymupdf

    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pages = len(doc)

    c1, c2, c3 = st.columns([1, 1, 2])
    c1.metric("Pages", pages)
    c2.metric("Skills", len(cv().all_skills()))
    settings()["preview_dpi"] = c3.select_slider(
        "Preview quality (dpi)", options=[72, 90, 110, 140, 180],
        value=settings()["preview_dpi"], key="f_dpi",
    )

    if pages != 4:
        st.info(
            f"Your CV is currently {pages} page(s); the original was 4. "
            "Adjust spacing under Layout & design if you want to get back to four."
        )

    stem = storage.safe_name(cv().name or project().name, "cv")
    filename = f"{stem}_CV_{datetime.now():%Y%m%d}.pdf"

    d1, d2 = st.columns([1, 1])
    d1.download_button("⬇ Download PDF", data=pdf, file_name=filename,
                       mime="application/pdf", type="primary", width="stretch")
    if d2.button("Save a copy to the exports folder", width="stretch"):
        path = storage.save_export(pdf, filename)
        st.success(f"Saved to `{path}`")

    st.caption(
        "Your original upload is never overwritten - exports always go to a new file."
    )

    st.divider()
    issues = validate_cv(cv())
    if issues:
        with st.expander(f"Validation: {summarise(issues)}", expanded=any(i.level == "error" for i in issues)):
            for issue in issues:
                renderer = {"error": st.error, "warning": st.warning}.get(issue.level, st.info)
                renderer(f"**{issue.section}** - {issue.message}")
    else:
        st.success("Validation passed: no issues found.")

    st.divider()
    original = load_original_bytes()
    if original:
        mode = st.radio("View", ["New CV", "Side by side with the original"],
                        horizontal=True, key="f_previewmode")
        if mode == "New CV":
            show_pdf(pdf, dpi=settings()["preview_dpi"])
        else:
            left, right = st.columns(2)
            with left:
                st.markdown("#### Original")
                show_pdf(original, dpi=settings()["preview_dpi"], caption_prefix="Original page")
            with right:
                st.markdown("#### New")
                show_pdf(pdf, dpi=settings()["preview_dpi"], caption_prefix="New page")
    else:
        show_pdf(pdf, dpi=settings()["preview_dpi"])


def page_tailored() -> None:
    st.subheader("Job-specific CV versions")
    st.caption(
        "Tailored versions only select, reorder or hide content that already exists in your master CV. "
        "Nothing is generated or rewritten, and no AI model is involved."
    )

    master = cv()
    roles = list(ROLE_PRESETS)
    c1, c2 = st.columns(2)
    role = c1.selectbox("Target role", roles + ["Custom"], key="tl_role")
    version_name = c2.text_input("Version name", value=role if role != "Custom" else "",
                                 key="tl_name")

    if st.button("Reset selection from this role", key="tl_reset"):
        for key in [k for k in list(st.session_state.keys()) if str(k).startswith("tl_sel_")]:
            del st.session_state[key]
        st.rerun()

    base = default_selection(master, role if role in ROLE_PRESETS else "")

    selection = TailorSelection(role=role)
    selection.headline = st.text_input("Professional title for this version",
                                       value=role if role in ROLE_PRESETS else master.job_title,
                                       key="tl_sel_headline")
    selection.summary = st.text_area("Summary for this version", value=master.summary,
                                     height=180, key="tl_sel_summary",
                                     help="Edit freely - but only state things that are true.")

    all_skills = master.all_skills()
    selection.skills = st.multiselect(
        "Skills to emphasise (order matters)", options=all_skills,
        default=[s for s in base.skills if s in all_skills], key="tl_sel_skills",
    )

    def _entry_picker(label: str, entries, defaults, key: str) -> List[str]:
        options = [e.id for e in entries]
        labels = {e.id: (e.title or "(untitled)") + (f" - {e.subtitle}" if e.subtitle else "")
                  for e in entries}
        return st.multiselect(label, options=options, default=[d for d in defaults if d in options],
                              format_func=lambda i: labels[i], key=key)

    selection.experience_ids = _entry_picker("Work experience to include", master.experience,
                                             base.experience_ids, "tl_sel_exp")
    selection.client_ids = _entry_picker("Client projects to include", master.clients,
                                         base.client_ids, "tl_sel_cli")
    selection.certificate_ids = _entry_picker("Certificates to include", master.certificates,
                                              base.certificate_ids, "tl_sel_cert")
    selection.course_ids = _entry_picker("Courses to include", master.courses,
                                         base.course_ids, "tl_sel_crs")

    tailored = build_tailored_cv(master, selection)
    problems = validate_tailored(master, tailored)
    if problems:
        for problem in problems:
            st.error(problem)
        return

    try:
        pdf = build_pdf(tailored, settings())
    except Exception as exc:  # pragma: no cover - defensive UI path
        st.error(f"Could not render this version: {exc}")
        return

    stem = storage.safe_name(f"{cv().name}_{version_name or role}", "tailored_cv")
    c1, c2 = st.columns(2)
    c1.download_button("⬇ Download this version", data=pdf, file_name=f"{stem}.pdf",
                       mime="application/pdf", type="primary", width="stretch")
    if c2.button("Save version into the project", width="stretch", key="tl_save"):
        name = (version_name or role).strip() or "Untitled version"
        project().versions = [v for v in project().versions if v.name != name]
        project().versions.append(
            TailoredVersion(name=name, role=role, cv=tailored,
                            created_at=datetime.now().isoformat(timespec="seconds"))
        )
        touch()
        st.success(f"Saved version '{name}'. The master CV is unchanged.")

    if project().versions:
        st.divider()
        st.markdown("**Saved versions**")
        for version in list(project().versions):
            c1, c2, c3 = st.columns([4, 2, 1])
            c1.write(f"**{version.name}** — {version.role or 'custom'}  \n`{version.created_at}`")
            if version.cv is not None:
                try:
                    c2.download_button(
                        "Download", data=build_pdf(version.cv, settings()),
                        file_name=f"{storage.safe_name(version.name)}.pdf",
                        mime="application/pdf", key=f"tl_dl_{version.name}",
                        width="stretch",
                    )
                except Exception:
                    c2.caption("Render failed")
            if c3.button("Delete", key=f"tl_del_{version.name}", width="stretch"):
                project().versions.remove(version)
                touch()
                st.rerun()

    st.divider()
    show_pdf(pdf, dpi=settings()["preview_dpi"], caption_prefix="Tailored page")


def page_project() -> None:
    st.subheader("Project & backup")
    st.caption(f"All data is stored locally under `{storage.home()}`.")

    project().name = st.text_input("Project name", value=project().name, key="f_projname")

    c1, c2 = st.columns(2)
    if c1.button("💾 Save project", type="primary", width="stretch"):
        try:
            path = storage.save_project(project())
            mark_saved()
            st.success(f"Saved to `{path}`")
        except OSError as exc:
            st.error(f"Could not save: {exc}")
    c2.download_button(
        "⬇ Download backup (.zip)",
        data=storage.backup_zip(project()),
        file_name=f"{storage.safe_name(project().name)}_backup.zip",
        mime="application/zip", width="stretch",
    )

    st.divider()
    st.markdown("**Load a saved project**")
    rows = storage.list_projects()
    if rows:
        labels = [f"{r['name']}  ({r['updated_at']}, {r['versions']} version(s))" for r in rows]
        index = st.selectbox("Saved projects", range(len(rows)), format_func=lambda i: labels[i],
                             key="f_loadsel")
        c1, c2 = st.columns(2)
        if c1.button("Load selected", width="stretch"):
            try:
                loaded = storage.load_project(rows[index]["path"])
            except storage.StorageError as exc:
                st.error(str(exc))
            else:
                reset_widget_state()
                st.session_state.project = loaded
                st.session_state.original_pdf_bytes = None
                mark_saved()
                init_state()
                st.success(f"Loaded '{loaded.name}'.")
                st.rerun()
        if c2.button("Delete selected", width="stretch"):
            storage.delete_project(rows[index]["path"])
            st.rerun()
    else:
        st.info("No saved projects yet.")

    st.divider()
    st.markdown("**Restore from a file**")
    restore = st.file_uploader("Project .json or backup .zip", type=["json", "zip"], key="f_restore")
    if restore is not None and st.button("Restore"):
        raw = restore.getvalue()
        try:
            loaded = (storage.restore_from_zip(raw) if restore.name.lower().endswith(".zip")
                      else storage.load_project_bytes(raw))
        except storage.StorageError as exc:
            st.error(str(exc))
        else:
            reset_widget_state()
            st.session_state.project = loaded
            st.session_state.original_pdf_bytes = None
            init_state()
            st.success(f"Restored '{loaded.name}'.")
            st.rerun()

    st.divider()
    if st.button("Start a new, empty project"):
        reset_widget_state()
        st.session_state.project = Project(name="My CV", cv=CVData())
        st.session_state.original_pdf_bytes = None
        st.session_state.extraction_warnings = []
        st.session_state.raw_text = ""
        init_state()
        st.rerun()


# ---------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------

def main() -> None:
    init_state()

    with st.sidebar:
        st.title("📄 CV Editor")
        st.caption("100% local · no cloud · no AI")
        page = st.radio("Sections", PAGES, key="nav", label_visibility="collapsed")
        st.divider()
        status = st.container()

    handlers = {
        "Upload & original": page_upload,
        "Contact & title": page_contact,
        "Summary": page_summary,
        "Skills": page_skills,
        "Work experience": lambda: page_entries(
            SEC_EXPERIENCE, "Work experience", "Add, edit, reorder and delete roles."),
        "Client projects": lambda: page_entries(
            SEC_CLIENTS, "Client projects", "Selected client / consulting assignments."),
        "Education": lambda: page_entries(SEC_EDUCATION, "Education"),
        "Certificates": lambda: page_entries(SEC_CERTIFICATES, "Certificates"),
        "Courses": lambda: page_entries(SEC_COURSES, "Courses"),
        "Languages & interests": page_languages_interests,
        "Layout & design": page_layout,
        "Preview & export": page_preview,
        "Tailored versions": page_tailored,
        "Project & backup": page_project,
    }
    handlers[page]()

    # Rendered last so it reflects edits the page just wrote back into the model.
    with status:
        issues = validate_cv(cv())
        errors = [i for i in issues if i.level == "error"]
        if errors:
            st.error(f"⚠ {summarise(issues)}")
        elif issues:
            st.warning(summarise(issues))
        else:
            st.success("No validation issues")

        if is_dirty():
            st.caption("● Unsaved changes in this session")
        else:
            st.caption("✓ All changes saved")
        if st.button("💾 Save project", width="stretch", key="side_save"):
            try:
                storage.save_project(project())
                mark_saved()
                st.toast("Project saved")
                st.rerun()
            except OSError as exc:
                st.error(f"Could not save: {exc}")

        st.caption(f"Project: **{project().name}**")


if __name__ == "__main__":
    main()
