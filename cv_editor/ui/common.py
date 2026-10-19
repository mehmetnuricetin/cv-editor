"""Shared helpers for the Streamlit UI."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

import streamlit as st

from ..model import CVData
from ..render import render_cv_pdf, render_preview_images
from ..storage import Project
from ..theme import ThemeOverrides

WIDGET_PREFIXES = ("f_", "sk_", "en_", "li_", "lay_", "tl_")


def reset_widget_state() -> None:
    """Drop editor widget state so a freshly loaded project is shown correctly."""
    for key in [k for k in list(st.session_state.keys()) if str(k).startswith(WIDGET_PREFIXES)]:
        del st.session_state[key]


def clear_keys(*prefixes: str) -> None:
    """Drop widget state for index-keyed editors.

    Widgets keyed by list position keep their old value after the list is
    reordered or an item is deleted, which would silently write the stale text
    back over the model on the next run.  Clearing the keys makes the widgets
    re-initialise from the data.
    """
    if not prefixes:
        return
    for key in [k for k in list(st.session_state.keys()) if str(k).startswith(prefixes)]:
        del st.session_state[key]


def project() -> Project:
    return st.session_state.project


def cv() -> CVData:
    return st.session_state.project.cv


def touch() -> None:
    """Kept for explicit mutations; the authoritative dirty check is is_dirty()."""
    st.session_state.unsaved = True


def _project_fingerprint() -> str:
    payload = json.dumps(project().to_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def mark_saved() -> None:
    """Record the current content as the saved baseline."""
    st.session_state.saved_fingerprint = _project_fingerprint()
    st.session_state.unsaved = False


def is_dirty() -> bool:
    """True when the project differs from the last saved/loaded state.

    Derived from the content itself rather than a flag, because the editors
    write widget values back into the model on every run.
    """
    baseline = st.session_state.get("saved_fingerprint")
    if baseline is None:
        return bool(st.session_state.get("unsaved", False))
    return _project_fingerprint() != baseline


def overrides_from_settings(settings: Dict[str, Any]) -> ThemeOverrides:
    return ThemeOverrides(
        body_size=float(settings.get("body_size", 10.5)),
        line_spacing=float(settings.get("line_spacing", 1.0)),
        section_spacing=float(settings.get("section_spacing", 1.0)),
        font_family=settings.get("font_family", ""),
    )


def fingerprint(data: CVData, settings: Dict[str, Any]) -> str:
    blob = json.dumps([data.to_dict(), settings], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@st.cache_data(show_spinner=False, max_entries=8)
def _render_cached(fp: str, payload: str, settings_json: str) -> bytes:
    data = CVData.from_dict(json.loads(payload))
    settings = json.loads(settings_json)
    return render_cv_pdf(data, overrides_from_settings(settings).apply())


def build_pdf(data: CVData, settings: Dict[str, Any]) -> bytes:
    fp = fingerprint(data, settings)
    return _render_cached(
        fp,
        json.dumps(data.to_dict(), sort_keys=True, ensure_ascii=False),
        json.dumps(settings, sort_keys=True),
    )


@st.cache_data(show_spinner=False, max_entries=8)
def _preview_cached(pdf_hash: str, pdf_bytes: bytes, dpi: int) -> List[bytes]:
    return render_preview_images(pdf_bytes, dpi=dpi)


def preview_images(pdf_bytes: bytes, dpi: int = 110) -> List[bytes]:
    return _preview_cached(hashlib.sha256(pdf_bytes).hexdigest(), pdf_bytes, dpi)


def show_pdf(pdf_bytes: bytes, dpi: int = 110, caption_prefix: str = "Page") -> None:
    try:
        images = preview_images(pdf_bytes, dpi=dpi)
    except Exception as exc:  # pragma: no cover - defensive UI path
        st.error(f"Could not render the preview: {exc}")
        return
    if not images:
        st.info("Nothing to preview yet.")
        return
    for i, image in enumerate(images, start=1):
        st.image(image, caption=f"{caption_prefix} {i} of {len(images)}", width="stretch")


# ---------------------------------------------------------------------------
# list manipulation helpers
# ---------------------------------------------------------------------------

def move(items: List[Any], index: int, delta: int) -> bool:
    target = index + delta
    if 0 <= target < len(items):
        items[index], items[target] = items[target], items[index]
        return True
    return False


def move_controls(items: List[Any], index: int, key: str) -> bool:
    """Render up / down / delete controls.  Returns True if the list changed."""
    changed = False
    c1, c2, c3 = st.columns(3)
    if c1.button("Move up", key=f"{key}_up", disabled=index == 0, width="stretch"):
        changed = move(items, index, -1)
    if c2.button("Move down", key=f"{key}_down", disabled=index == len(items) - 1, width="stretch"):
        changed = move(items, index, 1)
    if c3.button("Delete", key=f"{key}_del", width="stretch"):
        items.pop(index)
        changed = True
    return changed


def rerun_if(changed: bool) -> None:
    if changed:
        touch()
        st.rerun()
