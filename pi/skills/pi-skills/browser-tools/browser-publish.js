'use strict';

/**
 * browser-publish.js
 * Eigent — Content Publishing via Real Browser ("The Hands")
 */

const CDP  = require('chrome-remote-interface');
const fs   = require('fs');
const path = require('path');
const { startBrowser, stopBrowser } = require('./browser-start');
const { enableNetworkTracking, waitForNetworkIdle } = require('./browser-intercept');

async function waitForElement(client, selector, timeoutMs = 10_000) {
  const deadline = Date.now() + timeoutMs;
  const poll     = 150;
  while (Date.now() < deadline) {
    const result = await client.Runtime.evaluate({
      expression:    `document.querySelector(${JSON.stringify(selector)}) !== null`,
      returnByValue: true,
    });
    if (result.result?.value === true) return;
    await new Promise(r => setTimeout(r, poll));
  }
  throw new Error(`waitForElement: "${selector}" not found within ${timeoutMs} ms`);
}

async function getElementCenter(client, selector) {
  const result = await client.Runtime.evaluate({
    expression: `
(function() {
  const el = document.querySelector(${JSON.stringify(selector)});
  if (!el) return null;
  el.scrollIntoView({ block: 'center', inline: 'center' });
  const r = el.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
})()
    `.trim(),
    returnByValue: true,
  });
  return result.result?.value ?? null;
}

async function clickElement(client, selector, opts = {}) {
  const { waitMs = 0, timeoutMs = 8_000 } = opts;
  await waitForElement(client, selector, timeoutMs);
  const center = await getElementCenter(client, selector);
  if (!center) throw new Error(`clickElement: "${selector}" exists but has no bounding rect`);
  const { Input } = client;
  const { x, y } = center;
  await Input.dispatchMouseEvent({ type: 'mousePressed',  x, y, button: 'left', clickCount: 1 });
  await Input.dispatchMouseEvent({ type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
  if (waitMs > 0) await new Promise(r => setTimeout(r, waitMs));
}

async function fillField(client, selector, value, opts = {}) {
  const { clear = true, timeoutMs = 8_000 } = opts;
  await waitForElement(client, selector, timeoutMs);
  const result = await client.Runtime.evaluate({
    expression: `
(function() {
  const el = document.querySelector(${JSON.stringify(selector)});
  if (!el) return { ok: false, reason: 'not found' };
  el.focus();
  const tag     = el.tagName.toLowerCase();
  const isInput = (tag === 'input' || tag === 'textarea');
  const proto   = isInput ? (tag === 'textarea' ? HTMLTextAreaElement : HTMLInputElement) : null;
  if (proto && ${clear}) {
    const nativeSetter = Object.getOwnPropertyDescriptor(proto.prototype, 'value')?.set;
    if (nativeSetter) { nativeSetter.call(el, ''); el.dispatchEvent(new Event('input', { bubbles: true })); }
  }
  const nativeSetter = isInput
    ? Object.getOwnPropertyDescriptor(
        (tag === 'textarea' ? HTMLTextAreaElement : HTMLInputElement).prototype, 'value'
      )?.set
    : null;
  if (nativeSetter) {
    nativeSetter.call(el, ${JSON.stringify(value)});
  } else if (el.isContentEditable) {
    el.textContent = ${JSON.stringify(value)};
  } else {
    el.value = ${JSON.stringify(value)};
  }
  el.dispatchEvent(new Event('input',  { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${JSON.stringify(value)} }));
  return { ok: true, tag };
})()
    `.trim(),
    returnByValue: true,
    awaitPromise: false,
  });
  const res = result.result?.value;
  if (!res?.ok) throw new Error(`fillField: "${selector}" — ${res?.reason || 'unknown error'}`);
}

async function runActions(client, actions, opts = {}) {
  const { verbose = false } = opts;
  if (!Array.isArray(actions) || actions.length === 0) throw new Error('runActions: actions must be a non-empty array');
  const screenshots = [];
  let completed = 0;
  for (const action of actions) {
    if (verbose) process.stdout.write(`  → ${action.type}${action.selector ? ` "${action.selector}"` : ''} ... `);
    switch (action.type) {
      case 'navigate':
        await client.Page.navigate({ url: action.url });
        await waitForNetworkIdle(client, { idleMs: action.idleMs ?? 600, timeoutMs: action.timeoutMs ?? 30_000 });
        break;
      case 'fill':
        await fillField(client, action.selector, action.value ?? '', { clear: action.clear ?? true, timeoutMs: action.timeoutMs ?? 8_000 });
        break;
      case 'click':
        await clickElement(client, action.selector, { waitMs: action.waitMs ?? 0, timeoutMs: action.timeoutMs ?? 8_000 });
        break;
      case 'wait':
        await new Promise(r => setTimeout(r, action.ms ?? 1000));
        break;
      case 'waitFor':
        await waitForElement(client, action.selector, action.timeoutMs ?? 10_000);
        break;
      case 'assertExists': {
        const r = await client.Runtime.evaluate({ expression: `document.querySelector(${JSON.stringify(action.selector)}) !== null`, returnByValue: true });
        if (r.result?.value !== true) throw new Error(`assertExists failed: "${action.label || action.selector}" not found in DOM`);
        break;
      }
      case 'assertText': {
        const r = await client.Runtime.evaluate({ expression: `(function(){var el=document.querySelector(${JSON.stringify(action.selector)});return el?(el.innerText||el.textContent||'').trim():null})()`, returnByValue: true });
        const actual = r.result?.value;
        if (actual === null) throw new Error(`assertText: "${action.selector}" not found`);
        const expected = action.pattern ? new RegExp(action.pattern, action.flags ?? 'i') : action.expected;
        const matches = expected instanceof RegExp ? expected.test(actual) : actual.includes(expected);
        if (!matches) throw new Error(`assertText failed for "${action.selector}"\n  Expected: ${expected}\n  Actual: "${actual.slice(0, 200)}"`);
        break;
      }
      case 'screenshot': {
        const { data } = await client.Page.captureScreenshot({ format: 'png' });
        const ssPath = action.path ?? `/tmp/eigent-screenshot-${Date.now()}.png`;
        const dir = path.dirname(ssPath); if (dir) fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(ssPath, Buffer.from(data, 'base64'));
        screenshots.push(ssPath);
        break;
      }
      default:
        throw new Error(`runActions: unknown action type "${action.type}"`);
    }
    completed++;
    if (verbose) console.log('✓');
  }
  return { completed, screenshots };
}

async function publishActions(opts = {}) {
  const { actions, port = null, profile = null, headless = true, verbose = false } = opts;
  if (!actions?.length) throw new Error('publishActions: opts.actions must be a non-empty array');
  let browserHandle = null, client = null;
  try {
    if (port === null) browserHandle = await startBrowser({ headless, profile, startupMs: 12_000 });
    client = await CDP({ port: port ?? browserHandle.port });
    await enableNetworkTracking(client);
    await client.Page.enable();
    return await runActions(client, actions, { verbose });
  } finally {
    if (client) { try { await client.close(); } catch (_) {} }
    if (browserHandle) stopBrowser(browserHandle);
  }
}

module.exports = { publishActions, runActions, clickElement, fillField, waitForElement, assertExists: () => {}, assertText: () => {}, takeScreenshot: () => {} };
