#!/usr/bin/env node
'use strict';

const CDP = require('chrome-remote-interface');
const { startBrowser, stopBrowser } = require('./browser-start');
const { enableNetworkTracking, waitForNetworkIdle } = require('./browser-intercept');
const { browserSearch } = require('./browser-search');
const { navigatePage } = require('./browser-navigate');

let browserHandle = null;
let client = null;

async function getClient(port, headless) {
  if (client) return client;
  browserHandle = await startBrowser({ headless: headless !== false, startupMs: 12000, port: port || undefined });
  client = await CDP({ port: browserHandle.port });
  await client.Network.enable();
  await client.Page.enable();
  return client;
}

async function ensurePage(url) {
  const c = await getClient();
  if (url) {
    await c.Page.navigate({ url });
    await new Promise(r => setTimeout(r, 2000));
  }
  return c;
}

async function cdpEval(expr) {
  const c = await getClient();
  const r = await c.Runtime.evaluate({ expression: expr, awaitPromise: true, returnByValue: false });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || 'CDP eval error');
  return r.result;
}

const TOOLS = [
  {
    name: 'browser_start',
    description: 'Launch/attach Chrome on CDP port',
    inputSchema: {
      type: 'object',
      properties: {
        port: { type: 'number', description: 'CDP port (random if omitted)' },
        headless: { type: 'boolean', default: true },
        profile: { type: 'string', description: 'Chrome profile name (e.g. "Default")' },
      },
    },
  },
  {
    name: 'browser_nav',
    description: 'Navigate to URL',
    inputSchema: {
      type: 'object',
      properties: { url: { type: 'string' }, new_tab: { type: 'boolean' } },
      required: ['url'],
    },
  },
  {
    name: 'browser_content',
    description: 'Extract readable text from current page or specified URL',
    inputSchema: {
      type: 'object',
      properties: { url: { type: 'string' } },
    },
  },
  {
    name: 'browser_eval',
    description: 'Execute JS in page context',
    inputSchema: {
      type: 'object',
      properties: { code: { type: 'string' } },
      required: ['code'],
    },
  },
  {
    name: 'browser_cookies',
    description: 'Dump cookies as JSON',
    inputSchema: { type: 'object', properties: {} },
  },
  {
    name: 'browser_screenshot',
    description: 'Save PNG screenshot',
    inputSchema: {
      type: 'object',
      properties: { selector: { type: 'string' } },
    },
  },
  {
    name: 'browser_select',
    description: 'CSS selector query — returns text content of matches',
    inputSchema: {
      type: 'object',
      properties: { selector: { type: 'string' } },
      required: ['selector'],
    },
  },
  {
    name: 'browser_intercept',
    description: 'Capture JSON API responses matching URL filter',
    inputSchema: {
      type: 'object',
      properties: {
        url: { type: 'string' },
        filter: { type: 'string' },
        timeout_ms: { type: 'number', default: 10000 },
      },
    },
  },
  {
    name: 'browser_watch',
    description: 'Watch DOM mutations on selector for duration',
    inputSchema: {
      type: 'object',
      properties: {
        url: { type: 'string' },
        selector: { type: 'string' },
        duration_ms: { type: 'number', default: 5000 },
      },
    },
  },
  {
    name: 'browser_search',
    description: 'Web search via real browser (DuckDuckGo, Google, Bing)',
    inputSchema: {
      type: 'object',
      properties: {
        query: { type: 'string' },
        engine: { type: 'string', enum: ['duckduckgo', 'google', 'bing'], default: 'duckduckgo' },
        maxResults: { type: 'number', default: 10 },
      },
      required: ['query'],
    },
  },
  {
    name: 'browser_hn_scraper',
    description: 'Scrape Hacker News front page',
    inputSchema: {
      type: 'object',
      properties: { limit: { type: 'number', default: 30 } },
    },
  },
  {
    name: 'browser_scrape',
    description: 'Schema-driven extraction from a page',
    inputSchema: {
      type: 'object',
      properties: {
        url: { type: 'string' },
        schema: { type: 'object', description: 'Extraction schema mapping field names to { selector, type?, attr?, schema? }' },
        assert: { type: 'boolean', description: 'Validate required fields after extraction' },
      },
      required: ['schema'],
    },
  },
  {
    name: 'browser_publish',
    description: 'Run an action sequence (typed action objects) on a page',
    inputSchema: {
      type: 'object',
      properties: {
        url: { type: 'string' },
        actions: { type: 'array', items: { type: 'object' } },
        verbose: { type: 'boolean' },
      },
      required: ['actions'],
    },
  },
];

async function handleTool(name, args) {
  switch (name) {
    case 'browser_start': {
      if (browserHandle) stopBrowser(browserHandle);
      client = null;
      const c = await getClient(args?.port, args?.headless);
      return { content: [{ type: 'text', text: 'Chrome ready on port ' + browserHandle.port }] };
    }
    case 'browser_nav': {
      await ensurePage();
      await client.Page.navigate({ url: args.url });
      await new Promise(r => setTimeout(r, 2000));
      return { content: [{ type: 'text', text: 'Navigated to ' + args.url }] };
    }
    case 'browser_content': {
      if (args?.url) {
        if (browserHandle) { stopBrowser(browserHandle); browserHandle = null; client = null; }
        const page = await navigatePage({ url: args.url, extractMode: 'text' });
        return { content: [{ type: 'text', text: page.title + '\n---\n' + page.text }] };
      }
      await ensurePage();
      const r = await cdpEval('document.title + "\\n---\\n" + (document.body?.innerText || "").slice(0, 50000)');
      return { content: [{ type: 'text', text: r.value || 'No content' }] };
    }
    case 'browser_eval': {
      await ensurePage();
      const r = await cdpEval(args.code);
      return { content: [{ type: 'text', text: JSON.stringify(r.value ?? r.description ?? '(void)') }] };
    }
    case 'browser_cookies': {
      const c = await getClient();
      const r = await c.Network.getAllCookies();
      return { content: [{ type: 'text', text: JSON.stringify(r.cookies || [], null, 2) }] };
    }
    case 'browser_screenshot': {
      await ensurePage();
      const r = await client.Page.captureScreenshot({ format: 'png' });
      if (!r.data) return { content: [{ type: 'text', text: 'Screenshot failed' }] };
      const path = '/tmp/browser-ss-' + Date.now() + '.png';
      require('fs').writeFileSync(path, Buffer.from(r.data, 'base64'));
      return { content: [{ type: 'text', text: 'Screenshot: ' + path + ' (' + Math.round(r.data.length * 3 / 4 / 1024) + ' KB)' }] };
    }
    case 'browser_select': {
      await ensurePage();
      const r = await cdpEval('JSON.stringify(Array.from(document.querySelectorAll(' + JSON.stringify(args.selector) + ')).map(function(el) { return el.textContent.trim(); }).slice(0, 100))');
      const items = JSON.parse(r.value || '[]');
      return { content: [{ type: 'text', text: items.length ? items.join('\n---\n') : 'No matches' }] };
    }
    case 'browser_search': {
      const results = await browserSearch({ query: args.query, engine: args.engine, maxResults: args.maxResults || 10 });
      return { content: [{ type: 'text', text: results.map(function(r) { return r.position + '. ' + r.title + '\n   ' + r.url + '\n   ' + r.snippet; }).join('\n\n') }] };
    }
    case 'browser_hn_scraper': {
      const results = await browserSearch({ query: 'site:news.ycombinator.com', engine: 'duckduckgo', maxResults: args?.limit || 30 });
      return { content: [{ type: 'text', text: results.map(function(r) { return r.title + '\n  ' + r.url; }).join('\n') }] };
    }
    default:
      return { content: [{ type: 'text', text: 'Unknown tool: ' + name }], isError: true };
  }
}

// Stdio MCP transport
let buffer = '';
let msgLen = 0;

process.stdin.on('data', function(chunk) {
  buffer += chunk.toString();
  processMessages();
});

function processMessages() {
  while (true) {
    if (msgLen === 0) {
      var sep = buffer.indexOf('\n');
      if (sep === -1) return;
      var header = buffer.slice(0, sep).replace(/\r$/, '');
      buffer = buffer.slice(sep + 1);
      if (header.indexOf('Content-Length: ') !== 0) continue;
      msgLen = parseInt(header.slice(16));
      // Skip blank lines (CRLF after headers)
      while (buffer.length > 0 && (buffer[0] === '\r' || buffer[0] === '\n')) {
        buffer = buffer.slice(1);
      }
    }
    if (buffer.length < msgLen) return;
    var raw = buffer.slice(0, msgLen);
    buffer = buffer.slice(msgLen);
    msgLen = 0;
    try {
      var msg = JSON.parse(raw);
      handleMessage(msg);
    } catch (e) {
      // JSON parse failed — likely split chunk, put it back
      buffer = raw + buffer;
    }
  }
}

async function handleMessage(msg) {
  function respond(data) {
    var body = JSON.stringify(Object.assign({ jsonrpc: '2.0', id: msg.id }, data));
    process.stdout.write('Content-Length: ' + Buffer.byteLength(body, 'utf-8') + '\r\n\r\n' + body);
  }

  switch (msg.method) {
    case 'initialize':
      respond({ result: { protocolVersion: '2024-11-05', capabilities: { tools: {} }, serverInfo: { name: 'pi-browser-tools', version: '1.0.0' } } });
      break;
    case 'tools/list':
      respond({ result: { tools: TOOLS } });
      break;
    case 'tools/call':
      try {
        var result = await handleTool(msg.params.name, msg.params.arguments);
        respond({ result: result });
      } catch (e) {
        respond({ error: { code: -32000, message: e.message } });
      }
      break;
    case 'notifications/initialized':
      break;
    default:
      respond({ error: { code: -32601, message: 'Unknown method: ' + msg.method } });
  }
}
