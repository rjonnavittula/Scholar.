# HIVE STUDY — BUILD GUIDE
### From cloning to modifying to first run. Every command, in order.

This guide assembles the system whose code is fully included in this kit:

```
hive-tasks/                      ← THE KIT (this folder)
├── app/                         ← the brain: FastAPI + Cushion engine  [tested ✅]
│   ├── main.py  api.py  models.py  cushion.py  db.py
├── tests/test_cushion.py        ← 8 passing unit tests for the engine  [run them]
├── clients/
│   ├── canvas_sync.py           ← Canvas → HIVE ingestion
│   └── relay.py                 ← HIVE → Super Productivity push
├── sp-mods/                     ← Super Productivity modification kit
│   ├── PATCHES.md               ← the 4 tiny edits, exact strings
│   ├── electron/external-api-server.ts   ← drop-in new file
│   └── src/task-api.effects.ts           ← drop-in new file
├── sp-plugin/hive-cushion/      ← the Cushion side-panel plugin
│   ├── manifest.json  plugin.js  index.html
├── theme/hive.css               ← the ma. skin
├── docker-compose.yml  Dockerfile  requirements.txt  .env.example
└── README.md
```

**Honesty box (read once):** the Cushion engine is genuinely unit-tested (8/8
passing in this kit — run `python3 -m unittest tests.test_cushion -v` yourself).
All Python and JS is syntax-verified. What I *couldn't* do from here is run
FastAPI (no package installs in my sandbox) or build SP against your checkout —
so Stage 1 Step 4 and Stage 3 have explicit verify-points where you confirm
reality. Each ⚠ marks one. There are five total; none take more than a minute.

**Time budget:** Stage 1 ≈ 20 min · Stage 2 ≈ 20 min · Stage 3 ≈ 1–2 h (the SP
build is the long pole) · Stage 4 ≈ 15 min · Stage 5 ≈ 10 min.

---

# STAGE 1 — The brain, running locally (~20 min)

### Step 1.1 — Lay out the workspace
```bash
mkdir -p ~/hive && cd ~/hive
# put this kit at ~/hive/hive-tasks  (copy/unzip it here)
cd hive-tasks
```

### Step 1.2 — Python env + deps
```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
> WSL note: do this inside WSL, not Windows-native Python, so paths in later
> stages stay consistent with your Docker setup.

### Step 1.3 — Prove the engine before the server
```bash
python3 -m unittest tests.test_cushion -v        # expect: Ran 8 tests ... OK
```
You've now verified the soul of the app on your machine.

### Step 1.4 — First run ⚠ verify-point 1
```bash
uvicorn app.main:app --reload --port 8077
```
Open **http://127.0.0.1:8077/docs** — you should see Swagger with tag groups:
`auth`, `courses`, `tasks`, `ingest`, `cushion`, `meta`. If imports fail here,
the error will name the missing piece; `pip install -r requirements.txt` again
inside the venv is the usual fix.

### Step 1.5 — Mint a key, create a task, ask the Cushion
```bash
curl -s -X POST "http://127.0.0.1:8077/auth/keys?label=dev"
# → {"id":1,"label":"dev","api_key":"hive_AbC..."}   ← SAVE THIS, shown once
export KEY=hive_AbC...

curl -s -X POST http://127.0.0.1:8077/tasks \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"title":"CMPSC 465 HW3","due_at":"2026-06-15T23:59:00","time_needed_min":180}'

curl -s http://127.0.0.1:8077/cushion -H "X-API-Key: $KEY" | python3 -m json.tool
```
**Expected:** `"feasible": true`, a `total_cushion_human` like `"21h 0m"`, and
your task in `per_task` with a positive `slack_min`.

### Step 1.6 — Make the Cushion *yours*
1. Add each course: `POST /courses` (use Swagger's *Try it out* — fastest way).
2. Add weekly commitments (lectures, work). `weekday`: 0=Mon … 6=Sun:
```bash
# CMPEN 331 lecture MWF 10:00–10:50 → three rows. Direct SQL or extend the API;
# quickest v0 path is Swagger on a small POST /commitments route you add, or:
python3 - <<'EOF'
from sqlmodel import Session
from app.db import engine, init_db
from app.models import Commitment
from datetime import time
init_db()
with Session(engine) as s:
    for wd in (0, 2, 4):  # Mon Wed Fri
        s.add(Commitment(title="CMPEN 331", weekday=wd,
                         start=time(10, 0), end=time(10, 50)))
    s.commit()
print("commitments added")
EOF
```
3. Edit `DEFAULT_CAPACITY` in `app/cushion.py` to your real study minutes per
   weekday.
4. Re-GET `/cushion` → the number should **drop**. The model now reflects your
   actual week.

### Step 1.7 — Canvas ingestion
Canvas → Account → Settings → **+ New Access Token**. Then:
```bash
export CANVAS_URL=https://psu.instructure.com
export CANVAS_TOKEN=<paste>
export HIVE_API_URL=http://127.0.0.1:8077
export HIVE_API_KEY=$KEY
python3 clients/canvas_sync.py
# → "Collected N assignments from Canvas"  → {"created": N, "updated": 0}
```
Re-run it any time; it **upserts** by `external_id` (no duplicates). Tune
`estimate_minutes()` in `canvas_sync.py` — those estimates are what the
Cushion weighs against your free time.

**STAGE 1 DONE when:** `/cushion` shows a semester-real number from real
assignments and real commitments.

---

# STAGE 2 — Containerize + self-host on H.I.V.E. (~20 min)

### Step 2.1 — Postgres + API under compose
```bash
cd ~/hive/hive-tasks
cp .env.example .env && $EDITOR .env      # long random HIVE_DB_PASSWORD
docker compose up -d --build hive-db hive-api
docker compose logs -f hive-api           # wait for "Uvicorn running"
```
Note: Postgres starts **empty** — your SQLite dev data doesn't migrate. Mint a
fresh key against port 8077 and re-run `canvas_sync.py`; it repopulates
everything in one shot (that's the point of idempotent ingest).

### Step 2.2 — Persistence proof
```bash
curl -s -X POST "http://localhost:8077/auth/keys?label=prod"   # save the new key
# create a task, then:
docker compose restart hive-api
curl -s http://localhost:8077/tasks -H "X-API-Key: <prod-key>"   # still there ✓
```

### Step 2.3 — Move it to the homelab
On your Docker LXC, same conventions as your arr stacks:
```bash
mkdir -p /opt/stacks/hive-tasks && cd /opt/stacks/hive-tasks
# copy the kit here (rsync/scp/git), create .env (or symlink your shared one)
docker compose up -d --build
```

### Step 2.4 — Lock the doors
- Expose **only over Tailscale** (or your reverse proxy with auth). Do not
  port-forward 8077 to WAN.
- `POST /auth/keys` is unauthenticated by design for bootstrap. Once you've
  minted your real keys, either block the route at the proxy or guard it
  (one-line dependency in `app/api.py`).
- Add the Postgres volume to your **PBS** backup job.

**STAGE 2 DONE when:** `/docs` loads from your phone on the tailnet and not
from off it, and a restart loses nothing.

---

# STAGE 3 — Super Productivity: clone, modify, skin, build (~1–2 h)

### Step 3.1 — Clone and branch
```bash
cd ~/hive
git clone https://github.com/johannesjo/super-productivity.git
cd super-productivity
git checkout -b hive-skin
npm install                      # this one takes a while
```

### Step 3.2 — Drop in the two new files
```bash
cp ../hive-tasks/sp-mods/electron/external-api-server.ts  electron/
cp ../hive-tasks/sp-mods/src/task-api.effects.ts \
   src/app/features/tasks/store/
```

### Step 3.3 — The four small edits ⚠ verify-point 2
Open **`sp-mods/PATCHES.md`** and apply §1–§4 (IPC enum member → main.ts
wire-up → preload whitelist check → effect registration). It gives exact
strings and what to grep for. ~10 minutes.

### Step 3.4 — The two VERIFY spots ⚠ verify-point 3
Both are marked inside `task-api.effects.ts`:
1. `task.model.ts` → confirm `dueDay` / `dueWithTime` (vs older `plannedAt`).
2. `task.service.ts` → confirm `add(title, isAddToBacklog, additional, ...)`.
Adjust the two marked lines if your checkout differs. Done.

### Step 3.5 — Wear the skin
```bash
cp ../hive-tasks/theme/hive.css src/styles/hive.css
```
Then at the **end** of `src/styles.scss` add:
```scss
@import './styles/hive';
```
The top half of `hive.css` is your tokens (truth); the bottom half maps them
onto SP's CSS variables — if some surface stays un-themed after build, grep
SP's SCSS for that surface's variable name and add one mapping line.

### Step 3.6 — Build and first run ⚠ verify-point 4
```bash
npm start                # web dev build at localhost:4200 — verify the skin
# then the desktop app (check package.json "scripts" for the exact name):
npm run startElectron    # or: npm run electron / dist scripts
```
On boot, the terminal should print:
```
[HIVE bridge] listening on http://127.0.0.1:39999
[HIVE bridge] token file: /home/you/.config/superProductivity/.external-api-token
```
That token path it prints is authoritative — use it in 3.7 and Stage 4.

### Step 3.7 — Bridge smoke test
```bash
TOKEN=$(cat ~/.config/superProductivity/.external-api-token)   # path from 3.6
curl -X POST http://127.0.0.1:39999/api/task \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"bridge smoke test","dueDay":"2026-06-15"}'
```
**Expected:** `202 {"status":"accepted"}` and the task appears in SP *live*,
no refresh. If 202 but no task: DevTools console in SP — usually verify-point
3's field names.

**STAGE 3 DONE when:** SP runs in amber-on-dark mono and a cURL materializes a
task in the UI.

---

# STAGE 4 — Connect brain → UI (~15 min)

### Step 4.1 — The relay
```bash
cd ~/hive/hive-tasks
export HIVE_API_URL=http://127.0.0.1:8077        # or your tailnet URL
export HIVE_API_KEY=<your key>
export SP_PROJECT_NAME=Canvas                     # optional: SP project mapping
python3 clients/relay.py
# → "relay: 12 new task(s) pushed, 12 total tracked"
```
Run it again → `0 new task(s)` — idempotent (state in `~/.hive-sp-relay.json`).

### Step 4.2 — Schedule both loops
```bash
crontab -e
# Canvas → HIVE, hourly at :05      |  HIVE → SP, hourly at :10
5  * * * *  cd /path/to/hive-tasks && /path/to/.venv/bin/python clients/canvas_sync.py >> ~/hive-sync.log 2>&1
10 * * * *  cd /path/to/hive-tasks && /path/to/.venv/bin/python clients/relay.py      >> ~/hive-sync.log 2>&1
```
(Env vars: put them in the crontab lines or a sourced env file. Windows: two
Task Scheduler jobs; the relay reads the SP token from `%APPDATA%` on its own.)

**STAGE 4 DONE when:** a new Canvas assignment appears in SP within the hour,
hands-free.

---

# STAGE 5 — The Cushion panel inside SP (~10 min) ⚠ verify-point 5

### Step 5.1 — Package the plugin
```bash
cd ~/hive/hive-tasks/sp-plugin/hive-cushion
zip -r ../hive-cushion.zip manifest.json plugin.js index.html
```

### Step 5.2 — Load it
SP → **Settings → Plugins → Load plugin from file** → pick the zip. If your SP
build wants a folder or URL instead, point it at the `hive-cushion/` directory.
⚠ The button-registration call in `plugin.js` tries the method names used
across recent releases (`registerSidePanelButton` → `registerHeaderButton` →
`showIndexHtmlAsView`); if no button appears, grep your checkout's
`packages/plugin-api/src` for the registration function and rename one call.

### Step 5.3 — Configure and watch it breathe
Open the panel → enter your HIVE URL + API key → **save & connect**.
- **Amber number** = your tightest slack across all deadlines; "on track".
- **Red** = infeasible, with the at-risk tasks listed and how short you are.

Stress test: `POST /tasks` something brutal (`time_needed_min: 6000`, due
tomorrow). Within a minute the panel flips red and names it. Delete it; amber
returns. **That flip is the whole product.**

> Panel says "cannot reach HIVE"? It's CORS or routing. The API ships with
> permissive CORS (`HIVE_CORS_ORIGINS=*`, key-based auth makes this OK on a
> tailnet); check the URL has no trailing slash, the key is the full
> `hive_...`, and the machine running SP is on the tailnet.

---

# FIRST FULL RUN — the end-to-end ritual

1. `docker compose ps` on the LXC → `hive-db`, `hive-api` healthy.
2. Phone on tailnet → `/docs` loads.
3. `python3 clients/canvas_sync.py` → real assignments land.
4. `python3 clients/relay.py` → they appear in SP, amber-on-dark.
5. Open the Cushion panel → a real number about your real semester.
6. Timebox tomorrow in SP's planner; start the timer on one task.
7. Sunday-night test: do you trust the number? Then it's shipped.

---

# Troubleshooting index

| Symptom | Cause → fix |
|---|---|
| `uvicorn` import error | deps outside venv → activate, reinstall |
| `/cushion` huge & always feasible | no commitments / estimates are 0 → Stage 1.6 |
| Cushion ignores a task | it has no `due_at` → it's in `unscheduled_task_ids` by design |
| Bridge 401 | wrong/stale token → re-read the token file (regenerated if deleted) |
| Bridge 202, no task in UI | field-name drift → verify-point 3; check SP DevTools console |
| Port 39999 in use | bridge logs it and disables itself → change `DEFAULT_PORT`, rebuild |
| Relay pushes duplicates | you deleted `~/.hive-sp-relay.json` → it's the dedupe memory |
| Canvas sync 401 | Canvas token expired → mint a new one |
| Panel CORS error | set `HIVE_CORS_ORIGINS`, restart `hive-api`; check tailnet reachability |
| Plugin button missing | API name drift → Step 5.2 grep + one rename |
| Postgres empty after Stage 2 | expected — fresh DB → re-run canvas_sync (idempotent) |

# What's deliberately NOT in v1 (so you don't chase ghosts)
- **Write-back** (SP time-spent/done → HIVE): the flow is one-way by design.
  The Cushion runs on estimates until you build the reverse bridge (course
  module M10). Mark progress via `PATCH /tasks/{id}` for now — works from
  Swagger in five seconds.
- **Multi-user / JWT** — single-user, API-key auth (mint/list/revoke). Fine
  behind Tailscale.

Since this guide was first written, Alembic migrations (`alembic/versions/`,
15 and counting), weighted grades, syllabus parsing, and past/future analytics
have all landed — they're built, not just planned. So has a whole learning/RAG
subsystem (source chunking, Qdrant semantic search, grounded lesson
generation, OKF course export/import) and the first-party `webui/` frontend
this guide doesn't otherwise mention — it's served straight off `hive-api` at
`/`, no SP checkout or plugin build required to use the app day to day.
