/**
 * HIVE bridge — loopback HTTP listener inside Super Productivity's Electron
 * main process. External scripts POST a task; we forward it over IPC to the
 * renderer, where TaskApiEffects commits it via TaskService.add().
 *
 * NEW FILE → place at:  electron/external-api-server.ts
 * Wire-up (2 lines in main.ts) and channel constant: see PATCHES.md.
 *
 * Security model: binds 127.0.0.1 only + bearer token (random, 0600, stored
 * in userData). Never bind 0.0.0.0.
 */
import * as http from 'http';
import * as path from 'path';
import * as fs from 'fs';
import { randomBytes } from 'crypto';
import { app } from 'electron';

export interface ExternalTaskPayload {
  title: string;
  notes?: string;
  projectId?: string;
  projectName?: string;
  tagNames?: string[];
  dueDay?: string; // 'YYYY-MM-DD'
  dueWithTime?: number; // epoch ms
  timeEstimate?: number; // ms
  externalId?: string; // pass-through for HIVE id mapping
}

type ForwardFn = (payload: ExternalTaskPayload) => void;

const DEFAULT_PORT = 39999;
const MAX_BODY_BYTES = 1_000_000;
let server: http.Server | null = null;

const tokenPath = (): string =>
  path.join(app.getPath('userData'), '.external-api-token');

export const getOrCreateToken = (): string => {
  const p = tokenPath();
  try {
    if (fs.existsSync(p)) {
      return fs.readFileSync(p, 'utf8').trim();
    }
  } catch {
    /* fall through and regenerate */
  }
  const token = randomBytes(24).toString('hex');
  fs.writeFileSync(p, token, { mode: 0o600 });
  return token;
};

export const startExternalApiServer = (
  forwardToRenderer: ForwardFn,
  port: number = DEFAULT_PORT,
): void => {
  if (server) {
    return;
  }
  const token = getOrCreateToken();

  server = http.createServer((req, res) => {
    const json = (code: number, body: object): void => {
      res.writeHead(code, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(body));
    };

    if (req.method !== 'POST' || req.url !== '/api/task') {
      return json(404, { error: 'not_found' });
    }
    if (req.headers['authorization'] !== `Bearer ${token}`) {
      return json(401, { error: 'unauthorized' });
    }

    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
      if (body.length > MAX_BODY_BYTES) {
        req.destroy();
      }
    });
    req.on('end', () => {
      try {
        const parsed = JSON.parse(body) as ExternalTaskPayload;
        if (!parsed || typeof parsed.title !== 'string' || !parsed.title.trim()) {
          return json(400, { error: 'title_required' });
        }
        forwardToRenderer(parsed);
        return json(202, { status: 'accepted' });
      } catch {
        return json(400, { error: 'invalid_json' });
      }
    });
  });

  server.on('error', (err: NodeJS.ErrnoException) => {
    if (err.code === 'EADDRINUSE') {
      console.warn(`[HIVE bridge] Port ${port} in use — bridge disabled.`);
    } else {
      console.error('[HIVE bridge] server error', err);
    }
    server = null;
  });

  server.listen(port, '127.0.0.1', () => {
    console.log(`[HIVE bridge] listening on http://127.0.0.1:${port}`);
    console.log(`[HIVE bridge] token file: ${tokenPath()}`);
  });
};

export const stopExternalApiServer = (): void => {
  if (server) {
    server.close();
    server = null;
  }
};
