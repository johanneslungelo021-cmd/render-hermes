async function cdpRequest(method, params) {
  const tabs = await (await fetch('http://127.0.0.1:9222/json')).json();
  const tab = tabs[0];
  if (!tab) throw new Error('No tab available');
  const ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  const result = await new Promise((resolve, reject) => {
    const id = Math.random();
    const timer = setTimeout(() => reject(new Error('CDP timeout')), 30000);
    ws.send(JSON.stringify({ id, method, params: params || {} }));
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.id === id) { clearTimeout(timer); resolve(msg); ws.close(); }
    };
  });
  return result;
}

const NATIVE_REACT_SETTER = `
(target, value) => {
  const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
  nativeSetter.set.call(target, value);
  target.dispatchEvent(new Event('input', { bubbles: true }));
  target.dispatchEvent(new Event('change', { bubbles: true }));
}
`;

export async function runActions(actions, opts = {}) {
  const results = [];
  for (let i = 0; i < actions.length; i++) {
    const action = actions[i];
    const { type, selector, value, url, text, timeout } = action;
    try {
      switch (type) {
        case 'navigate':
          await cdpRequest('Page.navigate', { url: url || value });
          await new Promise(r => setTimeout(r, 2000));
          results.push({ index: i, type, status: 'ok' });
          break;

        case 'click':
          await cdpRequest('Input.dispatchMouseEvent', {
            type: 'mousePressed',
            x: 0, y: 0,
            clickCount: 1,
            button: 'left',
          });
          await cdpRequest('Input.dispatchMouseEvent', {
            type: 'mouseReleased',
            x: 0, y: 0,
            clickCount: 1,
            button: 'left',
          });
          results.push({ index: i, type, status: 'ok' });
          break;

        case 'type':
        case 'fill':
          await cdpRequest('Runtime.evaluate', {
            expression: `(() => { const el = document.querySelector('${(selector || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'); if (!el) return 'NOT_FOUND'; el.focus(); const s = ${NATIVE_REACT_SETTER}; s(el, ${JSON.stringify(value || '')}); return 'OK'; })()`,
          });
          results.push({ index: i, type, status: 'ok' });
          break;

        case 'assertExists':
        case 'assertText': {
          const r = await cdpRequest('Runtime.evaluate', {
            expression: `(() => { const el = document.querySelector('${(selector || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'); if (!el) return JSON.stringify({ found: false }); const text = el.textContent.trim(); ${type === 'assertText' ? `return JSON.stringify({ found: true, text, match: text.includes(${JSON.stringify(text || '')}) });` : 'return JSON.stringify({ found: true });'}})()`,
            awaitPromise: true,
          });
          const state = JSON.parse(r.result?.result?.value || '{}');
          if (!state.found) throw new Error(`assertExists failed: selector "${selector}" not found`);
          if (type === 'assertText' && !state.match) throw new Error(`assertText failed: "${text}" not found in "${state.text}"`);
          results.push({ index: i, type, status: 'ok', data: state });
          break;
        }

        case 'wait':
          await new Promise(r => setTimeout(r, timeout || value || 2000));
          results.push({ index: i, type, status: 'ok' });
          break;

        case 'screenshot': {
          const r = await cdpRequest('Page.captureScreenshot', { format: 'png' });
          const path = `/tmp/publish-ss-${Date.now()}-${i}.png`;
          await require('fs').promises.writeFile(path, Buffer.from(r.result?.data || '', 'base64'));
          results.push({ index: i, type, status: 'ok', path });
          break;
        }

        case 'evaluate': {
          const r = await cdpRequest('Runtime.evaluate', {
            expression: value || action.code,
            awaitPromise: true,
          });
          results.push({ index: i, type, status: 'ok', value: r.result?.result?.value });
          break;
        }

        default:
          results.push({ index: i, type, status: 'error', error: `Unknown action type: ${type}` });
      }
    } catch (e) {
      results.push({ index: i, type, status: 'error', error: e.message });
      if (opts.verbose) console.error(`Action ${i} (${type}) failed:`, e.message);
    }
  }
  return { results, total: actions.length, passed: results.filter(r => r.status === 'ok').length };
}
