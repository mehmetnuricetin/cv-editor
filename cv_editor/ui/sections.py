"""Editor pages for every CV section."""

from __future__ import annotations

from typing import List

import streamlit as st

from ..model import (
    DEFAULT_SKILL_CATEGORIES,
    ENTRY_FIELD_LABELS,
    SEC_CERTIFICATES,
    SEC_CLIENTS,
    SEC_COURSES,
    SEC_EDUCATION,
    SEC_EXPERIENCE,
    SEC_INTERESTS,
    SEC_LANGUAGES,
    CVData,
    Entry,
    SkillCategory,
)
from .common import clear_keys, cv, move, move_controls, rerun_if, touch


# ---------------------------------------------------------------------------
# contact / title
# ---------------------------------------------------------------------------

def page_contact() -> None:
    data = cv()
    st.subheader("Contact information and professional title")
    st.caption("These appear in the header block at the top of page 1.")

    c1, c2 = st.columns(2)
    data.name = c1.text_input("Full name", value=data.name, key="f_name")
    data.job_title = c2.text_input("Professional title", value=data.job_title, key="f_job_title")

    c1, c2 = st.columns(2)
    data.contact.phone = c1.text_input("Phone", value=data.contact.phone, key="f_phone")
    data.contact.email = c2.text_input("Email", value=data.contact.email, key="f_email")

    c1, c2 = st.columns(2)
    data.contact.linkedin = c1.text_input("LinkedIn", value=data.contact.linkedin, key="f_linkedin")
    data.contact.github = c2.text_input("GitHub", value=data.contact.github, key="f_github")

    c1, c2 = st.columns(2)
    data.contact.location = c1.text_input("Location", value=data.contact.location, key="f_location")
    data.contact.website = c2.text_input("Website (optional)", value=data.contact.website, key="f_website")

    st.divider()
    st.markdown("**Section headings**")
    st.caption("Keep the original wording to stay faithful to your existing design.")
    cols = st.columns(3)
    for i, section in enumerate(sorted(data.headings)):
        col = cols[i % 3]
        data.headings[section] = col.text_input(
            section.replace("_", " ").title(), value=data.heading(section), key=f"f_head_{section}"
        )


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

def page_summary() -> None:
    data = cv()
    st.subheader("Professional summary")
    st.caption("Leave a blank line between paragraphs to create a paragraph break in the PDF.")
    data.summary = st.text_area("Summary", value=data.summary, height=260, key="f_summary")
    words = len(data.summary.split())
    st.caption(f"{words} words - the original summary is around 100 words.")


# ---------------------------------------------------------------------------
# skills
# ---------------------------------------------------------------------------

def _add_skill(data: CVData, category: SkillCategory, value: str) -> bool:
    value = value.strip()
    if not value:
        st.warning("Enter a skill name first.")
        return False
    if data.has_skill(value):
        st.warning(f"'{value}' is already in your skills list.")
        return False
    category.skills.append(value)
    touch()
    return True


def _reset_skill_widgets(data: CVData) -> None:
    """Skill rows are keyed by list position, so reordering or deleting one
    invalidates every row widget below it."""
    prefixes = ["sk_mv_"] + [f"sk_{c.id}_" for c in data.skill_categories]
    clear_keys(*prefixes)


def page_skills() -> None:
    data = cv()

    # Text inputs must be cleared before the widgets are instantiated, so the
    # "Add" handlers only request a clear and it is applied on the next run.
    for pending, widget in (("sk_pending_clear", "sk_new"),
                            ("sk_cat_pending_clear", "sk_new_cat_name")):
        if st.session_state.pop(pending, False):
            st.session_state[widget] = ""
    flash = st.session_state.pop("sk_flash", None)

    st.subheader("Technical skills")
    st.caption(
        "Skills are grouped into categories for easy editing. "
        "Turn on 'Show category headings' under Layout & design to print the category names in the PDF."
    )

    if not data.skill_categories:
        data.skill_categories.append(SkillCategory(name=DEFAULT_SKILL_CATEGORIES[0]))

    names = [c.name or "(unnamed)" for c in data.skill_categories]

    with st.container(border=True):
        st.markdown("**Add a skill**")
        c1, c2, c3 = st.columns([3, 2, 1])
        new_skill = c1.text_input("New skill", key="sk_new", label_visibility="collapsed",
                                  placeholder="e.g. Azure AI Foundry")
        target = c2.selectbox("Category", options=list(range(len(names))),
                              format_func=lambda i: names[i], key="sk_new_cat",
                              label_visibility="collapsed")
        if c3.button("Add", type="primary", width="stretch", key="sk_add"):
            if _add_skill(data, data.skill_categories[target], new_skill):
                st.session_state["sk_flash"] = f"Added '{new_skill.strip()}'."
                st.session_state["sk_pending_clear"] = True
                st.rerun()
        if flash:
            st.success(flash)

    with st.expander("Manage categories"):
        c1, c2 = st.columns([3, 1])
        preset = [n for n in DEFAULT_SKILL_CATEGORIES if n not in names]
        new_cat = c1.text_input("New category name", key="sk_new_cat_name",
                                placeholder=preset[0] if preset else "New category")
        if c2.button("Add category", width="stretch", key="sk_add_cat"):
            name = (new_cat or (preset[0] if preset else "")).strip()
            if not name:
                st.warning("Enter a category name.")
            elif any(c.name.casefold() == name.casefold() for c in data.skill_categories):
                st.warning("That category already exists.")
            else:
                data.skill_categories.append(SkillCategory(name=name))
                touch()
                st.session_state["sk_cat_pending_clear"] = True
                st.rerun()

    total = 0
    for ci, category in enumerate(list(data.skill_categories)):
        with st.container(border=True):
            head, ctrl = st.columns([3, 2])
            category.name = head.text_input(
                "Category name", value=category.name, key=f"sk_cat_{category.id}",
                label_visibility="collapsed",
            )
            with ctrl:
                if move_controls(data.skill_categories, ci, f"sk_catctrl_{category.id}"):
                    touch()
                    st.rerun()

            if not category.skills:
                st.caption("No skills in this category yet.")
            for si, skill in enumerate(list(category.skills)):
                total += 1
                c1, c2, c3, c4, c5 = st.columns([5, 1, 1, 1, 2])
                category.skills[si] = c1.text_input(
                    "Skill", value=skill, key=f"sk_{category.id}_{si}", label_visibility="collapsed"
                )
                if c2.button("↑", key=f"sk_up_{category.id}_{si}", disabled=si == 0,
                             width="stretch", help="Move up"):
                    move(category.skills, si, -1)
                    _reset_skill_widgets(data)
                    touch()
                    st.rerun()
                if c3.button("↓", key=f"sk_dn_{category.id}_{si}", disabled=si == len(category.skills) - 1,
                             width="stretch", help="Move down"):
                    move(category.skills, si, 1)
                    _reset_skill_widgets(data)
                    touch()
                    st.rerun()
                if c4.button("✕", key=f"sk_rm_{category.id}_{si}", width="stretch", help="Delete"):
                    category.skills.pop(si)
                    _reset_skill_widgets(data)
                    touch()
                    st.rerun()
                dest = c5.selectbox(
                    "Move to", options=[-1] + list(range(len(data.skill_categories))),
                    format_func=lambda i: "Move to…" if i == -1 else names[i],
                    key=f"sk_mv_{category.id}_{si}", label_visibility="collapsed",
                )
                if dest != -1 and data.skill_categories[dest] is not category:
                    value = category.skills.pop(si)
                    data.skill_categories[dest].skills.append(value)
                    _reset_skill_widgets(data)
                    touch()
                    st.rerun()

            if st.button("Delete this category", key=f"sk_delcat_{category.id}"):
                data.skill_categories.pop(ci)
                _reset_skill_widgets(data)
                touch()
                st.rerun()

    st.caption(f"{total} skills in {len(data.skill_categories)} categories.")


# ---------------------------------------------------------------------------
# generic entry sections
# ---------------------------------------------------------------------------

def _entry_editor(section: str, entries: List[Entry], index: int) -> bool:
    labels = ENTRY_FIELD_LABELS[section]
    entry = entries[index]
    changed = False
    with st.container(border=True):
        header = entry.title.strip() or f"Entry {index + 1}"
        st.markdown(f"**{index + 1}. {header}**")

        c1, c2 = st.columns(2)
        entry.title = c1.text_input(labels["title"], value=entry.title, key=f"en_{entry.id}_title")
        if labels["right_top"]:
            entry.right_top = c2.text_input(labels["right_top"], value=entry.right_top, key=f"en_{entry.id}_rt")

        c1, c2 = st.columns(2)
        if labels["subtitle"]:
            entry.subtitle = c1.text_input(labels["subtitle"], value=entry.subtitle, key=f"en_{entry.id}_sub")
        if labels["right_sub"]:
            entry.right_sub = c2.text_input(labels["right_sub"], value=entry.right_sub, key=f"en_{entry.id}_rs")

        c1, c2 = st.columns(2)
        if labels["third"]:
            entry.third = c1.text_input(labels["third"], value=entry.third, key=f"en_{entry.id}_third")
        if labels["right_third"]:
            entry.right_third = c2.text_input(labels["right_third"], value=entry.right_third,
                                              key=f"en_{entry.id}_r3")

        if section in (SEC_EXPERIENCE, SEC_CLIENTS):
            st.markdown("Bullet points")
            bullets_changed = False
            for bi, bullet in enumerate(list(entry.bullets)):
                b1, b2, b3, b4 = st.columns([8, 1, 1, 1])
                entry.bullets[bi] = b1.text_area(
                    f"Bullet {bi + 1}", value=bullet, key=f"en_{entry.id}_b{bi}",
                    height=90, label_visibility="collapsed",
                )
                if b2.button("↑", key=f"en_{entry.id}_bu{bi}", disabled=bi == 0, width="stretch"):
                    move(entry.bullets, bi, -1)
                    bullets_changed = True
                if b3.button("↓", key=f"en_{entry.id}_bd{bi}",
                             disabled=bi == len(entry.bullets) - 1, width="stretch"):
                    move(entry.bullets, bi, 1)
                    bullets_changed = True
                if b4.button("✕", key=f"en_{entry.id}_bx{bi}", width="stretch"):
                    entry.bullets.pop(bi)
                    bullets_changed = True
                # Stop rendering rows as soon as the list changes: the remaining
                # indices are stale and their widgets hold outdated text.
                if bullets_changed:
                    clear_keys(f"en_{entry.id}_b")
                    return True
            if st.button("Add bullet point", key=f"en_{entry.id}_addb"):
                entry.bullets.append("")
                changed = True

        if move_controls(entries, index, f"en_ctrl_{entry.id}"):
            changed = True
    return changed


def page_entries(section: str, heading: str, help_text: str = "") -> None:
    data = cv()
    entries = data.entries_for(section)
    st.subheader(heading)
    if help_text:
        st.caption(help_text)

    if st.button(f"Add {heading.rstrip('s').lower()}", type="primary", key=f"en_add_{section}"):
        entries.insert(0, Entry())
        touch()
        st.rerun()

    if not entries:
        st.info("No entries yet. Use the button above to add one.")
        return

    changed = False
    for index in range(len(entries)):
        if index >= len(entries):
            break
        if _entry_editor(section, entries, index):
            changed = True
            break
    rerun_if(changed)


# ---------------------------------------------------------------------------
# simple lists (languages / interests)
# ---------------------------------------------------------------------------

def page_simple_list(section: str, heading: str) -> None:
    data = cv()
    values = data.simple_list_for(section)

    if st.session_state.pop(f"li_pending_clear_{section}", False):
        st.session_state[f"li_new_{section}"] = ""

    st.subheader(heading)

    c1, c2 = st.columns([4, 1])
    new_value = c1.text_input("Add", key=f"li_new_{section}", label_visibility="collapsed",
                              placeholder=f"Add a new {heading.rstrip('s').lower()}")
    if c2.button("Add", type="primary", width="stretch", key=f"li_add_{section}"):
        value = new_value.strip()
        if not value:
            st.warning("Enter a value first.")
        elif any(v.strip().casefold() == value.casefold() for v in values):
            st.warning(f"'{value}' is already in the list.")
        else:
            values.append(value)
            st.session_state[f"li_pending_clear_{section}"] = True
            touch()
            st.rerun()

    for i, value in enumerate(list(values)):
        c1, c2, c3, c4 = st.columns([6, 1, 1, 1])
        values[i] = c1.text_input("Value", value=value, key=f"li_{section}_{i}", label_visibility="collapsed")
        if c2.button("↑", key=f"li_up_{section}_{i}", disabled=i == 0, width="stretch"):
            move(values, i, -1)
            clear_keys(f"li_{section}_")
            touch()
            st.rerun()
        if c3.button("↓", key=f"li_dn_{section}_{i}", disabled=i == len(values) - 1, width="stretch"):
            move(values, i, 1)
            clear_keys(f"li_{section}_")
            touch()
            st.rerun()
        if c4.button("✕", key=f"li_rm_{section}_{i}", width="stretch"):
            values.pop(i)
            clear_keys(f"li_{section}_")
            touch()
            st.rerun()


def page_languages_interests() -> None:
    tab1, tab2 = st.tabs(["Languages", "Interests"])
    with tab1:
        page_simple_list(SEC_LANGUAGES, "Languages")
    with tab2:
        page_simple_list(SEC_INTERESTS, "Interests")
