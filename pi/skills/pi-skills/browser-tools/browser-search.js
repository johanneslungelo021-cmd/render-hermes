'use strict';

/**
 * browser-search.js
 * Eigent — Web Search via Real Browser (Connection-Leak-Free)
 */

const CDP = require('chrome-remote-interface');
const { startBrowser, stopBrowser } = require('./browser-start');
const { enableNetworkTracking, waitForNetworkIdle } = require('./browser-intercept');

const SEARCH_ENGINES = {
  duckduckgo: {
    buildUrl: q => 'https://html.duckduckgo.com/html/?q=' + encodeURIComponent(q),
    containerSel: '.result',
    titleSel: '.result__title a',
    snippetSel: '.result__snippet',
    linkSel: '.result__title a',
    linkAttr: 'href',
  },
  google: {
    buildUrl: q => 'https://www.google.com/search?q=' + encodeURIComponent(q) + '&hl=en&num=20',
    containerSel: 'div.g, div[data-sokoban-container]',
    titleSel: 'h3',
    snippetSel: '.VwiC3b, .lEBKkf, span[data-sncf="1"]',
    linkSel: 'a[href]',
    linkAttr: 'href',
  },
  bing: {
    buildUrl: q => 'https://www.bing.com/search?q=' + encodeURIComponent(q) + '&count=20',
    containerSel: 'li.b_algo',
    titleSel: 'h2 a',
    snippetSel: '.b_caption p, .b_algoSlug',
    linkSel: 'h2 a',
    linkAttr: 'href',
  },
};

function buildExtractionScript(engineCfg, maxResults) {
  var c = JSON.stringify;
  return '(function extractResults() { var containers = Array.from(document.querySelectorAll(' + c(engineCfg.containerSel) + ')); var results = []; for (var el of containers) { if (results.length >= ' + maxResults + ') break; var titleEl = el.querySelector(' + c(engineCfg.titleSel) + '); var snippetEl = el.querySelector(' + c(engineCfg.snippetSel) + '); var linkEl = el.querySelector(' + c(engineCfg.linkSel) + '); var rawHref = linkEl ? (linkEl.getAttribute(' + c(engineCfg.linkAttr) + ') || linkEl.href || "") : ""; var url = rawHref.trim(); try { if (url.startsWith("/url?")) { var p = new URLSearchParams(url.slice(5)); url = p.get("q") || url; } else if (url.startsWith("//")) { url = "https:" + url; } else if (url && !url.startsWith("http")) { url = new URL(url, location.href).href; } } catch(_) {} var title = (titleEl?.innerText || titleEl?.textContent || "").trim(); var snippet = (snippetEl?.innerText || snippetEl?.textContent || "").trim(); if (title && url && url.startsWith("http")) { results.push({ title: title, snippet: snippet, url: url }); } } return results; }())';
}

async function browserSearch(opts = {}) {
  var query = opts.query, engine = (opts.engine || 'duckduckgo').toLowerCase().trim(), maxResults = opts.maxResults || 10, port = opts.port || null, headless = opts.headless !== false, idleMs = opts.idleMs || 700, timeoutMs = opts.timeoutMs || 30000;
  if (!query || typeof query !== 'string' || !query.trim()) throw new Error('browserSearch: query required');
  if (!SEARCH_ENGINES[engine]) throw new Error('browserSearch: unknown engine "' + engine + '". Valid: ' + Object.keys(SEARCH_ENGINES).join(', '));
  var engineCfg = SEARCH_ENGINES[engine];
  var searchUrl = engineCfg.buildUrl(query.trim());
  var browserHandle = null, client = null;
  try {
    if (port === null) browserHandle = await startBrowser({ headless: headless, startupMs: 12000 });
    var cdpPort = port || browserHandle.port;
    client = await CDP({ port: cdpPort });
    var Network = client.Network, Page = client.Page, Runtime = client.Runtime;
    await enableNetworkTracking(client);
    await Page.enable();
    await Page.navigate({ url: searchUrl });
    await waitForNetworkIdle(client, { idleMs: idleMs, timeoutMs: timeoutMs });
    var evaluation = await Runtime.evaluate({ expression: buildExtractionScript(engineCfg, maxResults), returnByValue: true, awaitPromise: false });
    if (evaluation.exceptionDetails) throw new Error('DOM extraction threw: ' + (evaluation.exceptionDetails.exception?.description || JSON.stringify(evaluation.exceptionDetails)));
    var raw = evaluation.result?.value || [];
    return raw.filter(function(r) { return r.title && r.url; }).slice(0, maxResults).map(function(r, i) { return { position: i + 1, title: r.title, url: r.url, snippet: r.snippet || '' }; });
  } finally {
    if (client) { try { await client.close(); } catch (_) {} }
    if (browserHandle) stopBrowser(browserHandle);
  }
}

module.exports = { browserSearch, SEARCH_ENGINES };
