export function validateSchema(schema, path = '') {
  if (!schema || typeof schema !== 'object') throw new Error(`Schema at ${path || 'root'} must be an object`);
  for (const [key, val] of Object.entries(schema)) {
    const p = path ? `${path}.${key}` : key;
    if (!val || typeof val !== 'object') throw new Error(`${p}: must be an object with selector or type`);
    if (val.type === 'nested') {
      if (!val.schema) throw new Error(`${p}: nested type requires schema`);
      validateSchema(val.schema, p);
    } else if (val.type === 'array') {
      if (!val.selector) throw new Error(`${p}: array type requires selector`);
      if (val.schema) validateSchema(val.schema, p);
    } else if (val.type === 'attr') {
      if (!val.selector) throw new Error(`${p}: attr type requires selector`);
      if (!val.attr) throw new Error(`${p}: attr type requires attr name`);
    } else {
      if (!val.selector && !val.type) throw new Error(`${p}: must have a selector`);
    }
  }
}

export function assertSchema(schema, data, path = '') {
  for (const [key, val] of Object.entries(schema)) {
    const p = path ? `${path}.${key}` : key;
    const d = data?.[key];
    if (val.required !== false && (d === null || d === undefined || d === '')) {
      const hint = val.selector ? ` (selector \`${val.selector}\` matched nothing)` : '';
      throw new Error(`${p}: required but got ${JSON.stringify(d)}${hint}`);
    }
    if (val.type === 'nested' && d && typeof d === 'object') {
      assertSchema(val.schema, d, p);
    }
    if (val.type === 'array' && Array.isArray(d)) {
      for (let i = 0; i < d.length; i++) {
        if (val.schema) assertSchema(val.schema, d[i], `${p}[${i}]`);
      }
    }
  }
}

async function cdpRequest(method, params) {
  const tabs = await (await fetch('http://127.0.0.1:9222/json')).json();
  const tab = tabs[0];
  if (!tab) throw new Error('No tab available');
  const wsUrl = tab.webSocketDebuggerUrl;
  const ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });
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

export async function scrapeSchema(schema) {
  const result = {};
  for (const [key, val] of Object.entries(schema)) {
    if (val.type === 'nested') {
      if (val.schema) result[key] = await scrapeSchema(val.schema);
      else result[key] = null;
    } else if (val.type === 'array') {
      const sel = val.selector;
      const items = await cdpRequest('Runtime.evaluate', {
        expression: `JSON.stringify(Array.from(document.querySelectorAll('${sel.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}')).map(el => el.textContent.trim()))`,
      });
      const texts = JSON.parse(items.result?.result?.value || '[]');
      if (val.schema) {
        result[key] = texts.map(t => ({ _text: t }));
      } else {
        result[key] = texts;
      }
    } else if (val.type === 'attr') {
      const r = await cdpRequest('Runtime.evaluate', {
        expression: `(() => { const el = document.querySelector('${val.selector.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'); return el ? el.getAttribute('${val.attr}') : null; })()`,
      });
      result[key] = r.result?.result?.value ?? null;
    } else {
      const r = await cdpRequest('Runtime.evaluate', {
        expression: `(() => { const el = document.querySelector('${(val.selector || val).replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'); return el ? el.textContent.trim() : null; })()`,
      });
      result[key] = r.result?.result?.value ?? null;
    }
  }
  return result;
}

export async function extractMarkdown(url) {
  if (url) {
    await cdpRequest('Page.navigate', { url });
    await new Promise(r => setTimeout(r, 2000));
  }
  const r = await cdpRequest('Runtime.evaluate', {
    expression: `(() => { const t = document.title; const b = document.body; if (!b) return t; const clone = b.cloneNode(true); clone.querySelectorAll('script,style,nav,footer,header,aside').forEach(el => el.remove()); return t + '\\n---\\n' + clone.innerText.slice(0, 50000); })()`,
  });
  return r.result?.result?.value || '';
}
