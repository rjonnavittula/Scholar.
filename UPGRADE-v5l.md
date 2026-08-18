# scholar. v5l — course hub (Courses & LMS, part 1 of 3)

**Schema change (adds columns to `course`), auto-applied on boot. No DB reset.**
First of three: hub → grades → scheduled auto-sync.

## What changed
- New **Courses** view (the ❏ button in the left rail): a card grid of all your
  courses — color, name, instructor, open-task count, source, credits — plus
  **+ course** and **import** buttons.
- The course dialog now holds real detail: **instructor, link (course page /
  syllabus URL), credits, and notes**, alongside name + color.
- Columns added to `course`: `instructor`, `url`, `notes`, `credits`.

## Apply (migration auto-runs)
```bash
cd /home/rk/shared/docker/hive-scholar
git apply scholar-v5l.patch
git commit -am "v5l: course hub"
git push
```
The reload re-runs migrations on boot — no rebuild, no reset. Refresh; click ❏.

## Next in this series
- **v5m — grades**: per-course weighted categories + entries → live course grade,
  shown in the course dialog.
- **v5n — scheduled auto-sync**: background Canvas/feed polling on an interval,
  with a settings toggle.
