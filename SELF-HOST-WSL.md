# SELF-HOST GUIDE — Docker + Ubuntu (WSL2) on Windows 11
### From a bare Windows 11 machine to scholar. running at http://localhost:8077

What you're hosting: **scholar.** — the Shovel-style HIVE study planner.
One container stack = Postgres + the FastAPI brain, which serves the ma.-dark
web UI at `/`, Swagger at `/docs`, and the Cushion at `/cushion`. Super
Productivity stays your timeboxing client (optional, Part 6).

---

## Part 1 — WSL2 + Ubuntu (~10 min, one reboot)

1. **PowerShell as Administrator:**
```powershell
wsl --install -d Ubuntu
```
Reboot when asked. On first launch Ubuntu asks for a username/password —
use `rk` to match your other systems.

2. **Make sure you're on WSL2 with systemd** (Docker needs it). In Ubuntu:
```bash
cat /etc/wsl.conf
```
If there's no `[boot] systemd=true`, add it:
```bash
sudo tee /etc/wsl.conf > /dev/null << 'EOF'
[boot]
systemd=true
EOF
```
Then in PowerShell: `wsl --shutdown`, reopen Ubuntu, and verify:
```bash
systemctl is-system-running   # "running" or "degraded" both fine
```

3. **(Recommended on Win11) mirrored networking** — makes `localhost` shared
between Windows and WSL in *both* directions (you'll want this for the SP
bridge later). Create/edit `C:\Users\<you>\.wslconfig`:
```ini
[wsl2]
networkingMode=mirrored
```
Then `wsl --shutdown` and reopen. If this mode misbehaves on your build,
remove it — WSL2's default already forwards WSL→Windows-localhost for
*inbound* browsing, which covers Parts 2–5.

## Part 2 — Docker Engine inside Ubuntu (~5 min)

Docker Desktop also works, but Engine-in-WSL is closer to your LXC muscle
memory and license-free:
```bash
sudo apt update && sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc > /dev/null
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
| sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER
```
Close and reopen Ubuntu (group change), then:
```bash
docker run --rm hello-world      # must print "Hello from Docker!"
```

## Part 3 — Deploy the stack (~5 min)

1. **Unzip the kit into WSL's own filesystem** (not `/mnt/c` — much faster I/O):
```bash
mkdir -p ~/stacks && cd ~/stacks
# from Windows, the easy copy: \\wsl.localhost\Ubuntu\home\rk\stacks in Explorer,
# drop hive-study-kit.zip there, then:
sudo apt install -y unzip && unzip hive-study-kit.zip && cd hive-tasks
```

2. **Secrets:**
```bash
cp .env.example .env
nano .env        # set HIVE_DB_PASSWORD to something long and random
```

3. **Up:**
```bash
docker compose up -d --build hive-db hive-api
docker compose logs -f hive-api   # wait for "Uvicorn running on http://0.0.0.0:8077"
```

## Part 4 — First run of scholar. (~5 min)

1. In a **Windows browser**: **http://localhost:8077** → the ma.-dark gate.
2. Mint your key (Ubuntu terminal):
```bash
curl -s -X POST "http://localhost:8077/auth/keys?label=main"
```
Copy the `hive_...` value — **it's shown exactly once.**
3. Paste it into the gate → you're in. Then, in the UI itself:
   - **week shape**: add every lecture/work block (this is what makes the
     Cushion honest);
   - **tasks**: add one with a due date and minutes-needed;
   - watch the hero number and the week bars react.
4. Wire Canvas (optional now, recommended):
```bash
sudo apt install -y python3-pip python3-venv
cd ~/stacks/hive-tasks && python3 -m venv .venv && source .venv/bin/activate
pip install canvasapi
export CANVAS_URL=https://psu.instructure.com CANVAS_TOKEN=<token>
export HIVE_API_URL=http://localhost:8077 HIVE_API_KEY=<your key>
python3 clients/canvas_sync.py
```
Reload scholar. — your real assignments are grouped by course, and the
Cushion is now about your actual semester.

## Part 5 — Make it survive reboots + reach it anywhere (~10 min)

- **Autostart**: containers have `restart: unless-stopped`, but WSL itself
  must be awake. Task Scheduler → Create Task → trigger *At log on* →
  action: program `wsl.exe`, arguments `-d Ubuntu -e true`. That boots the
  distro; Docker (systemd) and the stack follow on their own.
- **Tailscale** (your pattern): simplest is the **Windows** Tailscale app —
  with mirrored networking, your tailnet can reach `:8077` via the Windows
  node. Per-port `tailscale serve` or installing tailscaled inside WSL also
  work; pick one, not both.
- **Backups**: the data is the `hive-db-data` volume.
```bash
docker run --rm -v hive-tasks_hive-db-data:/data -v ~/backups:/backup \
  alpine tar czf /backup/hive-db-$(date +%F).tgz -C /data .
```
Cron it weekly; pull the tarballs into PBS when you're home. (Volume name
prefix = compose project dir; `docker volume ls` to confirm.)
- **Updates**: `docker compose up -d --build` after editing code; the DB
  volume persists.

## Part 6 — Optional: Super Productivity as the timeboxing client

scholar. is the brain and the Shovel-style face; SP adds drag-drop
timeboxing, timers, and focus mode. Two tiers:

- **Zero-effort**: run stock SP (web `docker compose up -d superproductivity`
  → :8080, or the Windows desktop app) and let it be a plain timer/planner
  beside scholar. No integration, still useful.
- **Full bridge** (tasks auto-flow HIVE → SP): follow **BUILD-GUIDE.md
  Stage 3** to clone SP on Windows or WSL, drop in `sp-mods/`, apply
  `PATCHES.md`, build the desktop app, then schedule `clients/relay.py`.
  With mirrored networking the relay can run in WSL and reach the SP bridge
  on Windows `localhost:39999`; without it, run the relay on Windows
  (it's stdlib-only Python). The `sp-plugin/hive-cushion/` panel puts the
  Cushion inside SP too.

---

## Troubleshooting (WSL-specific first)

| Symptom | Fix |
|---|---|
| `docker: command not found` after install | close/reopen Ubuntu (group membership) |
| `Cannot connect to the Docker daemon` | systemd not on → Part 1 step 2, `wsl --shutdown`, retry |
| Windows browser can't reach :8077 | `docker compose ps` first; then `wsl --shutdown` + reopen (port forwarding resets); check no VPN is grabbing localhost |
| Tailnet can't reach it | mirrored networking not active, or Tailscale serving from the wrong side — pick Windows *or* WSL |
| Everything slow | kit is on `/mnt/c` → move to `~/stacks` (Part 3.1) |
| WSL clock drift after sleep (cron fires oddly) | `sudo hwclock -s` or `wsl --shutdown`; known WSL quirk |
| UI loads but every action 401s | stale key in browser → "change key" at the page footer, paste a fresh one |
| Forgot the API key | mint another: `curl -X POST "http://localhost:8077/auth/keys?label=second"` |
| Need a clean slate | `docker compose down -v` (⚠ deletes the DB volume) |

**Security note, same as always:** nothing here is exposed beyond your
machine + tailnet. Don't port-forward 8077 on your router; gate or disable
`POST /auth/keys` once your keys are minted.
