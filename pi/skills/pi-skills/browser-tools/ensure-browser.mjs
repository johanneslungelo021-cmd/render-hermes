import { spawn } from 'child_process';
import { existsSync } from 'fs';

const CDP_PORT = 9222;
const CHROME_PATHS = [
  process.env.CHROMIUM_PATH,
  '/data/data/com.termux/files/usr/bin/chromium',
  '/root/.cache/ms-playwright/chromium-1228/chrome-linux/chrome',
  '/root/.cache/ms-playwright/chromium-1520/chrome-linux/chrome',
  '/root/.cache/ms-playwright/chromium-latest/chrome-linux/chrome',
];

async function cdpAlive() {
  try {
    const res = await fetch(`http://127.0.0.1:${CDP_PORT}/json/version`, { signal: AbortSignal.timeout(2000) });
    return res.ok;
  } catch { return false; }
}

function findChrome() {
  for (const p of CHROME_PATHS) {
    if (p && existsSync(p)) return p;
  }
  return null;
}

let chromeProc = null;

export async function ensureBrowser(xvfb = false) {
  if (await cdpAlive()) return { ok: true, port: CDP_PORT };

  const chrome = findChrome();
  if (!chrome) return { ok: false, error: 'No Chrome binary found' };

  const args = [
    `--remote-debugging-port=${CDP_PORT}`,
    '--no-sandbox',
    '--disable-gpu',
    '--disable-dev-shm-usage',
    '--disable-setuid-sandbox',
  ];
  if (!xvfb) args.push('--headless');

  const env = { ...process.env };
  if (xvfb) {
    env.DISPLAY = env.DISPLAY || ':99';
    const xvfb = spawn('Xvfb', [':99', '-screen', '0', '1920x1080x24'], { stdio: 'ignore' });
    xvfb.unref();
  }

  chromeProc = spawn(chrome, args, { stdio: 'ignore', env });
  chromeProc.unref();
  chromeProc.on('exit', () => { chromeProc = null; });

  for (let i = 0; i < 15; i++) {
    await new Promise(r => setTimeout(r, 1000));
    if (await cdpAlive()) return { ok: true, port: CDP_PORT };
  }
  return { ok: false, error: 'Chrome failed to start' };
}

export async function getCDPEndpoint() {
  const tabs = await (await fetch(`http://127.0.0.1:${CDP_PORT}/json`)).json();
  return tabs[0]?.webSocketDebuggerUrl || `ws://127.0.0.1:${CDP_PORT}/devtools/page/${tabs[0]?.id || '1'}`;
}
