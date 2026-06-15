# scholar. v4q — two-tier top bar + first-open greeting

**No schema change → no DB reset.** Frontend only.

## What changed

### Two-tier top bar
The single overcrowded bar is split into two rows:
- **Global row** — `scholar.` wordmark · Calendar / Task List · (spacer) · study
  streak · running-timer pill · cushion chip · `+ task`.
- **Calendar toolbar** — Week / Month / Next-N · today · ‹ › · week range.

Because the date/view controls now live on their own row, they can never crash
into the status pills, which is what made the old one-row bar wrap and break.

### Smooth dynamic resizing (the part that must not mess up)
Both rows are `white-space:nowrap; overflow:hidden`, and a `ResizeObserver`
watches the **main column's own width** (not the window) — so the bar reacts
correctly even when the task panel opens or closes. It sets `data-w` on the bar
(`full / md / sm / xs`) and elements drop in priority order:
- `md` (<720px): the `scholar.` wordmark hides
- `sm` (<560px): the streak dots and the "today" button hide
- `xs` (<460px): `+ task` collapses to `+`, the week label shrinks

Nothing wraps onto a broken second line at any width.

### First-open greeting
On the first load of each calendar day, a full-screen time-of-day greeting
("Good morning/afternoon/evening, <name>") fades in, holds ~2.4s, then fades
away to reveal the app — tap to dismiss early. Gated once per day via
`localStorage` (key `scholar_greeted`), so it won't replay on every navigation.
If a name isn't set in settings, it just says "Good evening" etc.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4q kit
docker compose build --no-cache hive-api && docker compose up -d
```
Hard-refresh once (the greeting is gated per day — to see it again, it resets at
midnight, or clear the `scholar_greeted` localStorage key).

## Worth a look on first run
- Reload → greeting fades in and out; reload again → it does NOT replay (gated).
- Collapse/expand the task panel → watch the bar shed the wordmark, then dots,
  then the "today" label, without wrapping.
- Resize the browser window narrow → same graceful collapse.

## Next (unchanged backlog)
Pomodoro mode, repeating tasks, drag tuning, calibration, onboarding.
