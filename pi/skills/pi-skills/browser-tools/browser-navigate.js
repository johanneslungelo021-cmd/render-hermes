'use strict';

/**
 * browser-navigate.js
 * Eigent — Navigate and Capture a Page
 */

const CDP = require('chrome-remote-interface');
const { startBrowser, stopBrowser } = require('./browser-start');
const { enableNetworkTracking, waitForNetworkIdle } = require('./browser-intercept');

async function navigatePage(opts = {}) {
  var url = opts.url, port = opts.port || null, headless = opts.headless !== false, idleMs = opts.idleMs || 600, timeoutMs = opts.timeoutMs || 30000, extractMode = opts.extractMode || 'text';
  if (!url || typeof url !== 'string') throw new Error('navigatePage: url required');
  var validModes = ['text', 'html', 'both'];
  if (validModes.indexOf(extractMode) === -1) throw new Error('navigatePage: extractMode must be one of: ' + validModes.join(', '));
  var browserHandle = null, client = null;
  try {
    if (port === null) browserHandle = await startBrowser({ headless: headless, startupMs: 12000 });
    var cdpPort = port || browserHandle.port;
    client = await CDP({ port: cdpPort });
    var Network = client.Network, Page = client.Page, Runtime = client.Runtime;
    await enableNetworkTracking(client);
    await Page.enable();
    var navStart = Date.now();
    await Page.navigate({ url: url });
    var idle = await waitForNetworkIdle(client, { idleMs: idleMs, timeoutMs: timeoutMs });
    var titleResult = await Runtime.evaluate({ expression: 'document.title', returnByValue: true });
    var hrefResult = await Runtime.evaluate({ expression: 'location.href', returnByValue: true });
    var finalUrl = hrefResult.result?.value || url;
    var title = titleResult.result?.value || '';
    var text = '', html = '';
    if (extractMode === 'text' || extractMode === 'both') {
      var textResult = await Runtime.evaluate({ expression: 'document.body ? document.body.innerText : ""', returnByValue: true });
      text = (textResult.result?.value || '').trim();
    }
    if (extractMode === 'html' || extractMode === 'both') {
      var htmlResult = await Runtime.evaluate({ expression: 'document.documentElement.outerHTML', returnByValue: true });
      html = (htmlResult.result?.value || '').trim();
    }
    return { url: finalUrl, title: title, text: text, html: html, requestCount: idle.requestCount, loadMs: Date.now() - navStart };
  } finally {
    if (client) { try { await client.close(); } catch (_) {} }
    if (browserHandle) stopBrowser(browserHandle);
  }
}

module.exports = { navigatePage };
