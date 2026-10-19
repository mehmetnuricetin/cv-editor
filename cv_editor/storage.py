"""Local-only project storage.

Everything lives under ``~/CVEditor`` (overridable with ``CV_EDITOR_HOME``):

``projects/``   one JSON file per project (master CV + tailored versions)
``originals/``  untouched copies of every uploaded PDF
``exports/``    generated PDFs
``index.sqlite`` small catalogue used to list projects quickly

Nothing is ever sent anywhere: the only I/O this module performs is on the
local filesystem.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .model import CVData

APP_DIR_ENV = "CV_EDITOR_HOME"
DEFAULT_HOME = Path.home() / "CVEditor"

PROJECT_VERSION = 1


class StorageError(RuntimeError):
    pass


def home() -> Path:
    base = Path(os.environ.get(APP_DIR_ENV, str(DEFAULT_HOME))).expanduser()
    for sub in ("projects", "originals", "exports", "backups"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def projects_dir() -> Path:
    return home() / "projects"


def originals_dir() -> Path:
    return home() / "originals"


def exports_dir() -> Path:
    return home() / "exports"


def backups_dir() -> Path:
    return home() / "backups"


def safe_name(name: str, fallback: str = "cv") -> str:
    cleaned = "".join(ch if (ch.isalnum() or ch in " -_") else "_" for ch in (name or "")).strip()
    cleaned = "_".join(cleaned.split())
    return cleaned or fallback


# ---------------------------------------------------------------------------
# project document
# ---------------------------------------------------------------------------

@dataclass
class TailoredVersion:
    name: str
    role: str = ""
    notes: str = ""
    cv: Optional[CVData] = None
    created_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "notes": self.notes,
            "created_at": self.created_at,
            "cv": self.cv.to_dict() if self.cv else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TailoredVersion":
        return cls(
            name=data.get("name", ""),
            role=data.get("role", ""),
            notes=data.get("notes", ""),
            created_at=data.get("created_at", ""),
            cv=CVData.from_dict(data["cv"]) if data.get("cv") else None,
        )


@dataclass
class Project:
    name: str = "My CV"
    cv: CVData = field(default_factory=CVData)
    original_pdf: str = ""          # path to the preserved upload
    original_filename: str = ""
    versions: List[TailoredVersion] = field(default_factory=list)
    render_settings: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_version": PROJECT_VERSION,
            "name": self.name,
            "cv": self.cv.to_dict(),
            "original_pdf": self.original_pdf,
            "original_filename": self.original_filename,
            "versions": [v.to_dict() for v in self.versions],
            "render_settings": self.render_settings,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        return cls(
            name=data.get("name", "My CV"),
            cv=CVData.from_dict(data.get("cv") or {}),
            original_pdf=data.get("original_pdf", ""),
            original_filename=data.get("original_filename", ""),
            versions=[TailoredVersion.from_dict(v) for v in data.get("versions") or []],
            render_settings=dict(data.get("render_settings") or {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def path(self) -> Path:
        return projects_dir() / f"{safe_name(self.name, 'project')}.json"


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(home() / "index.sqlite")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
               name TEXT PRIMARY KEY,
               path TEXT NOT NULL,
               updated_at TEXT NOT NULL,
               versions INTEGER NOT NULL DEFAULT 0
           )"""
    )
    return conn


def _index_upsert(project: Project, path: Path) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO projects(name, path, updated_at, versions) VALUES(?,?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET path=excluded.path, updated_at=excluded.updated_at, "
            "versions=excluded.versions",
            (project.name, str(path), project.updated_at, len(project.versions)),
        )


def _index_delete(name: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM projects WHERE name = ?", (name,))


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def save_project(project: Project) -> Path:
    now = datetime.now().isoformat(timespec="seconds")
    project.created_at = project.created_at or now
    project.updated_at = now
    path = project.path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(project.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    _index_upsert(project, path)
    return path


def load_project(path: str | Path) -> Project:
    path = Path(path)
    if not path.exists():
        raise StorageError(f"Project file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StorageError(f"{path.name} is not a valid project file: {exc}") from exc
    return Project.from_dict(data)


def load_project_bytes(raw: bytes) -> Project:
    try:
        return Project.from_dict(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StorageError(f"Not a valid project file: {exc}") from exc


def list_projects() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for path in sorted(projects_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rows.append(
            {
                "name": data.get("name", path.stem),
                "path": str(path),
                "updated_at": data.get("updated_at", ""),
                "versions": len(data.get("versions") or []),
            }
        )
    rows.sort(key=lambda r: r["updated_at"], reverse=True)
    return rows


def delete_project(path: str | Path) -> None:
    path = Path(path)
    if path.exists():
        try:
            name = json.loads(path.read_text(encoding="utf-8")).get("name", path.stem)
        except Exception:
            name = path.stem
        path.unlink()
        _index_delete(name)


def store_original(pdf_bytes: bytes, filename: str) -> Path:
    """Keep an untouched copy of the uploaded PDF.  Never overwritten."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = safe_name(Path(filename).stem, "original")
    target = originals_dir() / f"{stem}_{stamp}.pdf"
    counter = 1
    while target.exists():
        target = originals_dir() / f"{stem}_{stamp}_{counter}.pdf"
        counter += 1
    target.write_bytes(pdf_bytes)
    try:
        target.chmod(0o444)  # read-only: the original must stay pristine
    except OSError:
        pass
    return target


def save_export(pdf_bytes: bytes, filename: str) -> Path:
    target = exports_dir() / filename
    counter = 1
    while target.exists():
        target = exports_dir() / f"{Path(filename).stem}_{counter}.pdf"
        counter += 1
    target.write_bytes(pdf_bytes)
    return target


def backup_zip(project: Project) -> bytes:
    """Build an in-memory zip with the project JSON and its original PDF."""
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            f"{safe_name(project.name)}.json",
            json.dumps(project.to_dict(), indent=2, ensure_ascii=False),
        )
        original = Path(project.original_pdf)
        if project.original_pdf and original.exists():
            zf.write(original, f"original/{original.name}")
        zf.writestr(
            "README.txt",
            "CV Editor backup\n"
            "================\n"
            "Restore by uploading the .json file via 'Project > Load project'.\n"
            f"Created: {datetime.now().isoformat(timespec='seconds')}\n",
        )
    return buf.getvalue()


def restore_from_zip(raw: bytes) -> Project:
    import io

    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = [n for n in zf.namelist() if n.endswith(".json")]
        if not names:
            raise StorageError("The archive does not contain a project JSON file.")
        project = load_project_bytes(zf.read(names[0]))
        originals = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
        if originals:
            target = originals_dir() / Path(originals[0]).name
            if not target.exists():
                target.write_bytes(zf.read(originals[0]))
            project.original_pdf = str(target)
    return project
