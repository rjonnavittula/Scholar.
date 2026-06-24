# scholar. v5m — grades (Courses & LMS, part 2 of 3)

**Schema change (adds `gradecategory` + `gradeitem` tables), auto-applied on
boot. No DB reset.** Builds on v5l.

## What changed
- Open a course (❏ Courses → a card, or edit a course) and hit **grades…** to
  open a grade editor:
  - weighted **categories** (e.g. Homework 30, Exams 50, Final 20) each holding
    **items** (title + earned/possible points), add/remove freely;
  - a **live current grade** (letter + %) at the top that updates as you type;
  - weights are **normalized over categories that actually have grades**, so an
    empty "Final 20%" doesn't tank your number early in the term.
- Course cards in the hub now show a **grade badge** (e.g. `A- · 91%`).
- New endpoints: `GET /grades/{cid}`, `PUT /grades/{cid}` (replace), and
  `GET /grades/summary` (per-course summary for the hub) — so H.I.V.E. can read
  grades too. The grade math is a pure module with 7 unit tests.

## Apply (migration auto-runs)
```bash
cd /home/rk/shared/docker/hive-scholar
git apply scholar-v5m.patch
git commit -am "v5m: grades"
git push
```
Reload re-runs migrations on boot — no rebuild, no reset.

## Next
- **v5n — scheduled auto-sync**: background Canvas/feed polling on an interval +
  a settings toggle. (Closes the Courses & LMS items you asked for.)
