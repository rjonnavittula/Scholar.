# scholar. v4h — Apple-style settings redesign + task/timer polish

No schema change → **no DB reset.** UI-only.

## Settings — full redesign (Apple inset-grouped, ma. flavored)
- Wider panel; content **grouped into inset cards** with section headers,
  row dividers, and generous spacing (the Apple Settings / Calendar idiom).
- **Responsive fields** — side-by-side when wide, stack when narrow (fixes the
  cramped Term section).
- **Animated section transitions** — panes glide in when you switch.
- Every section (Term, Personalization, Appearance, Notifications, Account)
  rebuilt in the new language.

## Task / timer polish
- A task being timed shows a **live "timing…" chip** (ticking) on its card.
- Logged time shows on the card, **rounded to the nearest minute**
  (29m 10s → 29m; verified).
- Timer still logs to the right task/subtask and rolls up.

## Small fixes
- Greeting capitalized: "Good morning, …".
- Mint-a-key now reveals the key inline.

## Apply (no reset)
```bash
cd ~/shared/docker/hive-tasks      # replace contents with v4h kit
docker compose build --no-cache hive-api && docker compose up -d
```
Normal refresh.

## Notes
- Light theme contrast pass still deferred (skin).
- Next: roll the design language to the rest of the app, then Pomodoro,
  repeating tasks, calibration engine, onboarding.
