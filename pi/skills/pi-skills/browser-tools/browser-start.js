'use strict';

/**
 * browser-start.js
 * Eigent — Hands & Eyes on the Raw Web
 *
 * Launches a Chromium instance via CDP with optional user profile support.
 * The --profile flag is fully wired: it copies the real Chrome/Chromium user
 * data directory into an isolated temp dir, so automation runs authenticated
 * sessions without corrupting your live profile.
 */

const { spawn, execSync } = require('child_process');
const fs   = require('fs');
const path = require('path');
const os   = require('os');
const crypto = require('crypto');

const CHROME_CANDIDATES = [
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
  // Playwright-managed Chromium (direct binary, no snap dependency)
  path.join(os.homedir(), '.cache', 'ms-playwright', 'chromium-1228', 'chrome-linux', 'chrome'),
  '/opt/google/chrome/chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/snap/bin/chromium',
  path.join(os.homedir(), '.cache', 'puppeteer', 'chrome',
    'linux-131.0.6778.204', 'chrome-linux64', 'chrome'),
];

function findChromeBinary() {
  for (const candidate of CHROME_CANDIDATES) {
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch (_) {}
  }
  for (const name of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']) {
    try {
      const resolved = execSync(`command -v ${name} 2>/dev/null`, { encoding: 'utf8' }).trim();
      if (resolved) return resolved;
    } catch (_) {}
  }
  throw new Error('No Chrome/Chromium binary found.\nCandidates:\n' + CHROME_CANDIDATES.map(c => '  ' + c).join('\n'));
}

const PROFILE_ROOTS = [
  path.join(os.homedir(), '.config', 'google-chrome'),
  path.join(os.homedir(), '.config', 'chromium'),
  path.join(os.homedir(), 'snap', 'chromium', 'current', '.config', 'chromium'),
];

function resolveProfileSource(profileName) {
  const name = profileName || 'Default';
  for (const root of PROFILE_ROOTS) {
    const profilePath = path.join(root, name);
    if (fs.existsSync(profilePath)) {
      return { userDataDir: root, profile: name };
    }
  }
  throw new Error('Chrome profile "' + name + '" not found.\nSearched:\n' + PROFILE_ROOTS.map(r => '  ' + path.join(r, name)).join('\n'));
}

function copyProfile(sourceRoot, profileName, destRoot) {
  const ESSENTIAL = [profileName, 'Local State'];
  for (const entry of ESSENTIAL) {
    const src = path.join(sourceRoot, entry);
    if (!fs.existsSync(src)) continue;
    const dst = path.join(destRoot, entry);
    const stat = fs.statSync(src);
    if (stat.isDirectory()) {
      fs.mkdirSync(dst, { recursive: true });
      try { execSync('rsync -a --delete "' + src + '/" "' + dst + '/" 2>/dev/null', { stdio: 'pipe' }); }
      catch (_) { execSync('cp -r "' + src + '/." "' + dst + '/"', { stdio: 'pipe' }); }
    } else {
      fs.copyFileSync(src, dst);
    }
  }
}

async function waitForCDP(port, maxMs) {
  const deadline = Date.now() + maxMs;
  let lastErr;
  while (Date.now() < deadline) {
    try {
      const res = await fetch('http://127.0.0.1:' + port + '/json/version');
      if (res.ok) return;
    } catch (err) { lastErr = err; }
    await new Promise(r => setTimeout(r, 150));
  }
  throw new Error('Chrome CDP did not respond on port ' + port + ' within ' + maxMs + 'ms.\nLast error: ' + (lastErr?.message || 'unknown'));
}

async function startBrowser(opts = {}) {
  const { profile = null, port = Math.floor(Math.random() * (9999 - 9222 + 1)) + 9222, headless = true, url = null, startupMs = 10000, binary = null, extraFlags = [] } = opts;
  const bin = binary || findChromeBinary();
  let tempProfileDir = null;
  const flags = [
    '--remote-debugging-port=' + port,
    '--remote-debugging-address=127.0.0.1',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-background-networking',
    '--disable-sync',
    '--disable-translate',
    '--disable-extensions',
    '--disable-popup-blocking',
    '--metrics-recording-only',
    '--safebrowsing-disable-auto-update',
    '--password-store=basic',
    '--use-mock-keychain',
  ];
  if (headless) {
    flags.push('--headless=new', '--disable-gpu', '--no-sandbox', '--disable-dev-shm-usage');
  }
  if (profile !== null) {
    const src = resolveProfileSource(profile);
    tempProfileDir = path.join(os.tmpdir(), 'eigent-' + crypto.randomBytes(6).toString('hex'));
    fs.mkdirSync(tempProfileDir, { recursive: true });
    copyProfile(src.userDataDir, src.profile, tempProfileDir);
    flags.push('--user-data-dir=' + tempProfileDir, '--profile-directory=' + src.profile);
  }
  for (const f of extraFlags) flags.push(f);
  if (url) flags.push(url);
  const proc = spawn(bin, flags, { detached: false, stdio: ['ignore', 'pipe', 'pipe'] });
  proc.stdout.resume();
  proc.stderr.resume();
  const earlyExit = await Promise.race([
    new Promise(resolve => proc.once('exit', code => resolve(code))),
    new Promise(resolve => setTimeout(() => resolve(null), 500)),
  ]);
  if (earlyExit !== null) {
    if (tempProfileDir) fs.rmSync(tempProfileDir, { recursive: true, force: true });
    throw new Error('Chrome exited immediately with code ' + earlyExit);
  }
  try {
    await waitForCDP(port, startupMs);
  } catch (err) {
    proc.kill('SIGTERM');
    if (tempProfileDir) fs.rmSync(tempProfileDir, { recursive: true, force: true });
    throw err;
  }
  return { pid: proc.pid, port, binary: bin, profileDir: tempProfileDir, proc };
}

function stopBrowser({ proc, profileDir } = {}) {
  if (proc && !proc.killed) proc.kill('SIGTERM');
  if (profileDir && fs.existsSync(profileDir)) fs.rmSync(profileDir, { recursive: true, force: true });
}

module.exports = { startBrowser, stopBrowser, findChromeBinary, CHROME_CANDIDATES };
