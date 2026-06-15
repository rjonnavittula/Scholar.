# PATCHES.md — the four small edits to Super Productivity core

The two big pieces are drop-in **new files** (no merge conflicts ever):

| New file in this kit                  | Goes to (in your SP checkout)                        |
| ------------------------------------- | ---------------------------------------------------- |
| `sp-mods/electron/external-api-server.ts` | `electron/external-api-server.ts`                |
| `sp-mods/src/task-api.effects.ts`         | `src/app/features/tasks/store/task-api.effects.ts` |

Then four tiny edits to existing files. Exact strings below — but **search by
pattern, not line number**; SP moves fast.

---

## §1 — `electron/shared-with-frontend/ipc-events.const.ts`
Add one member to the `IPC` enum (anywhere inside it):

```ts
  ADD_TASK_FROM_API = 'ADD_TASK_FROM_API',
```

## §2 — `electron/main.ts`
(a) Imports, top of file with the other local imports:

```ts
import { startExternalApiServer, stopExternalApiServer } from './external-api-server';
```
(`IPC` is almost certainly already imported in main.ts; if not, add it from
`./shared-with-frontend/ipc-events.const`.)

(b) After the main window is created (find where `createWindow(...)` is called
and a reference to the created BrowserWindow is kept — the variable name in
current source is `mainWin`):

```ts
startExternalApiServer((payload) => {
  if (mainWin && !mainWin.isDestroyed()) {
    mainWin.webContents.send(IPC.ADD_TASK_FROM_API, payload);
  }
});
```

(c) In the existing `app.on('before-quit', ...)` handler (or add one):

```ts
stopExternalApiServer();
```

## §3 — `electron/preload.ts` + `electron/electronAPI.d.ts`
Open `preload.ts` and look at how `ea.on` is implemented:

- **If** it whitelists channels (an array/set of allowed channel names, or a
  per-channel `on` map): add `IPC.ADD_TASK_FROM_API` to that list.
- **If** it's a generic passthrough (`on: (channel, cb) => ipcRenderer.on(channel, cb)`):
  nothing to do here.

Either way, if `electronAPI.d.ts` types the channel names as a union, add the
new channel so TypeScript stays strict.

## §4 — register the effect
Find where `TaskElectronEffects` is registered (grep for it — it'll be in the
tasks feature's `provideEffects([...])` array or an `EffectsModule.forFeature`).
Add `TaskApiEffects` next to it:

```ts
import { TaskApiEffects } from './store/task-api.effects';
// ...
provideEffects([ /* existing */, TaskElectronEffects, TaskApiEffects ])
```

---

## VERIFY before building (2 spots, both marked in task-api.effects.ts)

1. **Due-date fields** — open `src/app/features/tasks/task.model.ts`, search
   `due`. Current: `dueDay` (string) / `dueWithTime` (ms) / `hasPlannedTime`.
   If your checkout shows `plannedAt` instead, swap the two spread lines.
2. **`TaskService.add` signature** — open `task.service.ts`, find `add(`.
   Expected `(title, isAddToBacklog, additional, isAddToBottom)`. If the
   params moved, adjust the one call site.

## Build & smoke-test

```bash
npm run build           # or: npm start for dev
# desktop dev run:
npm run startElectron   # check package.json scripts; name may differ slightly
```

On boot the console prints the bridge port and token path. Then:

```bash
TOKEN=$(cat "$HOME/.config/superProductivity/.external-api-token")  # Linux
# Windows: %APPDATA%\superProductivity\.external-api-token
# macOS:   ~/Library/Application Support/superProductivity/.external-api-token
# (exact folder name = Electron app name; ls the parent dir if unsure)

curl -X POST http://127.0.0.1:39999/api/task \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"bridge smoke test","dueDay":"2026-06-15"}'
```

`202 {"status":"accepted"}` + task appears in Today view = bridge is live.
