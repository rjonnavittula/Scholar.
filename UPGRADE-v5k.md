# scholar. v5k — syllabus PDF import (Courses & LMS, the no-Canvas path)

**No schema change → no DB reset. BUT requirements changed (adds `pypdf`), so this
one needs a rebuild, not just a hot-reload.**

## What changed
- The Canvas dialog is now an **import** dialog with a 4th tab: **Syllabus PDF**.
- Upload a syllabus (**PDF or .txt**) → scholar extracts the dated assignments
  and shows them in a **review list** (include/skip, edit title, date, category)
  → import the ones you want, optionally under a course you name.
- Built for your friends in India too: it reads **US and international date
  formats** — "September 12", "12 September", `2025-09-12`, and numeric dates
  with a **day-first toggle** (so `13/09` and `4/5` resolve correctly). It also
  rolls Jan–Jun dates into the next year when the syllabus spans a fall term.
- Nothing is created silently — you always confirm the list first.
- The PDF text is uploaded as base64 through the normal API (no new multipart
  dependency); parsing is a pure module with 14 unit tests.

## Apply (rebuild required)
```bash
cd /home/rk/shared/docker/hive-scholar
git apply scholar-v5k.patch
git commit -am "v5k: syllabus PDF import"
docker compose up -d --build      # rebuild: requirements.txt added pypdf
git push
```
Then: top bar → import (the Canvas button) → **Syllabus PDF**.

## Notes / limits
- Works on **text-based** PDFs. Scanned/image-only PDFs have no text layer — it
  will say so; OCR would be a later add.
- It's a heuristic extractor (keyword + date per line). The review step is where
  you fix anything it misread. An optional Ollama-assisted parse for messy
  syllabi is a natural follow-on.

## Category status
**Courses & LMS** — Canvas ✓ (token/feed/script), **syllabus PDF ✓**. Skipped by
choice: Brightspace/Moodle. Still open if you want them later: course hub,
grades, scheduled auto-sync.
