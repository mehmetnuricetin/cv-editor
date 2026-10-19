# CV Editor

A local web app for editing your PDF CV and exporting a new one that keeps the
original two-column design.

Everything runs on your Mac. Nothing is uploaded anywhere, no account is needed,
no external or AI service is called, and your original PDF is never modified.

---

## Quick start

```bash
cd ~/cv-editor
./run.sh
```

That is all. The script creates a virtual environment, installs the
dependencies on first run, and opens the app at <http://localhost:8501>.

Manual equivalent, if you prefer:

```bash
cd ~/cv-editor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Requirements: macOS with Python 3.10 or newer (`brew install python`).
Press `Ctrl+C` in the terminal to stop the app.

---

## Workflow

1. **Upload & original** — drop in your PDF. The text is extracted, split into
   sections, and the original is copied read-only into your project folder. You
   get a warning if a page looks scanned or if little text could be read.
2. **Edit** — work through the sections in the left-hand navigation. Everything
   is a plain form field.
3. **Preview & export** — see the rendered CV, compare it side by side with the
   original, then **Download PDF** or save a copy into the exports folder.
4. **Save project** — the sidebar button writes your work to a local JSON file
   so you can come back to it later.

### Skills editor

The Skills page is built for frequent edits:

- Type a skill, pick a category, press **Add**.
- Edit any skill in place.
- **↑ / ↓** to reorder, **✕** to delete, and a **Move to…** dropdown to send a
  skill to another category.
- Duplicates are rejected case-insensitively, so "Terraform" and "terraform"
  cannot both be added.
- Default categories: Cloud Platforms, Infrastructure as Code, Containers and
  Kubernetes, CI/CD and Automation, Monitoring and Security, AI and Agentic AI,
  Operating Systems and Scripting. You can rename, add, reorder and delete
  categories freely.

Changes are kept in the session as you type; press **💾 Save project** to write
them to disk. The sidebar always tells you whether you have unsaved changes.

### Work experience, projects and other sections

Work experience, client projects, education, certificates and courses are all
entry lists: add, edit, delete and reorder entries, and for experience and
projects also add, edit, delete and reorder bullet points. Languages and
interests are simple lists with the same controls.

### Tailored versions

The **Tailored versions** page builds a CV aimed at one role — Azure Cloud
Engineer, DevOps Engineer, Platform Engineer, OpenShift Administrator or AI
Platform Engineer — by letting you pick which of your existing skills and
projects to emphasise.

It never invents anything. A tailored version can only contain skills, projects
and text that already exist in your master CV; the app validates this before
saving and refuses content it cannot trace back to your data. The role presets
only *preselect* items you already have. Your master CV is left untouched, and
each version is stored separately inside the project.

---

## PDF design: what is preserved, and the trade-off

**The app rebuilds your CV from a measured template rather than editing the
original PDF file.** This is the central design decision, so here is why.

### Why the original file cannot simply be edited

Your CV embeds its body text as **unnamed Type 3 subset fonts**, plus a
subsetted *FontAwesome 6 Free Solid* font for the contact icons. A subset only
contains the glyphs the document already uses, and these particular fonts cannot
be extracted or re-embedded (PyMuPDF's `extract_font` returns a stub). So if the
app patched text into the original page, any newly added character — the "y" in
a skill you just typed, or a whole new line — would have no glyph to draw with.
The result would be missing or substituted characters and broken spacing.

### What the app does instead

The original CV was measured page by page and its layout grid was encoded in
`cv_editor/theme.py`: page size, column positions and widths, the sidebar
background colour, section-heading size and the rule beneath it, and the exact
leading used between every kind of line. The renderer in `cv_editor/render.py`
rebuilds the document on that grid.

**Reproduced faithfully:**

- A4 page size, the 288.75 pt main column and the 216.75 pt grey sidebar
  (`#F7F7F7`) with identical margins
- Section headings in 12 pt bold uppercase with the 2.25 pt rule underneath
- All original line spacing, paragraph spacing and entry spacing
- Right-aligned dates and locations opposite entry titles
- Bullet styling, the contact icons, and the 4-page structure
- Each column paginates independently, and a section heading is repeated when a
  section continues onto the next page, exactly like the original

**Approximated:**

- **The typeface.** The original font cannot be identified or reused, so glyph
  widths from the original were measured and compared against the serif fonts
  available on macOS. *Charter* matched most closely (within about 5% on
  average) and is used by default. If Charter is missing the app falls back to
  Helvetica. You can pick a different family on the **Layout & design** page.
- **Skill order in the sidebar.** On import, skills are sorted into categories
  using a local keyword list, which changes their original flat order. Reorder
  them on the Skills page, or switch categories off and arrange them by hand.
- Page count may change if you add enough content; the layout engine reflows
  rather than overlapping or clipping text.

Long skill lists and long text wrap automatically, words too long for a column
are split rather than dropped, and blank pages are not produced.

The **Layout & design** page lets you move sections between the main column and
the sidebar, change the font, body size, line spacing and section spacing, and
toggle category headings — useful if your content grows and you want it to fit.

---

## Your data

Everything is stored under `~/CVEditor` (override with the `CV_EDITOR_HOME`
environment variable):

```
~/CVEditor/
├── projects/      one .json file per project — your editable data
├── originals/     read-only copies of every PDF you upload
├── exports/       generated PDFs
├── backups/       .zip backups
└── index.sqlite   small catalogue used to list projects quickly
```

- Uploaded originals are timestamped and set read-only (`chmod 444`). The app
  never writes to the file you uploaded.
- Exports never overwrite each other; a counter is appended instead.

### Backup and restore

On **Project & backup**: **Download backup (.zip)** saves the project plus its
original PDF; the uploader on the same page restores from a `.json` project file
or from a `.zip` backup. To back up everything at once, just copy the
`~/CVEditor` folder.

---

## Tests

```bash
cd ~/cv-editor
.venv/bin/python -m pytest
```

The suite covers text extraction from a PDF, section detection, the layout
engine and pagination, PDF export (including that a newly added skill really
appears in the exported file), storage round-trips, the anti-invention rules for
tailored versions, and the full UI workflow driven through Streamlit's own test
harness. The tests build their own PDF fixture, so they do not depend on your
personal CV being present, and they write to a temporary directory rather than
`~/CVEditor`.

---

## Project layout

```
app.py                  Streamlit app: navigation and pages
run.sh                  macOS start script
cv_editor/
├── model.py            CVData / Entry / SkillCategory and JSON serialisation
├── extract.py          layout-aware PDF extraction and scanned-page detection
├── render.py           two-column layout engine and PDF export
├── theme.py            layout constants measured from the original CV
├── fonts.py            font discovery with Helvetica fallback
├── icons.py            vector contact icons
├── storage.py          local projects, originals, exports, backups
├── tailor.py           job-specific versions and anti-invention validation
├── validate.py         content warnings shown in the sidebar
└── ui/                 shared widgets and the section editors
tests/                  pytest suite
```

## Troubleshooting

- **"Little or no text could be extracted"** — the PDF is probably a scan.
  There is no OCR in the app; fill the sections in manually.
- **Sections land in the wrong place** — section detection relies on headings.
  Move content between sections in the editors, or use Layout & design to
  change which column a section appears in.
- **Content spills onto an extra page** — reduce body size or line spacing on
  Layout & design, or shorten a bullet point.
- **Port already in use** — `streamlit run app.py --server.port 8600`.
