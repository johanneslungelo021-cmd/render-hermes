'use strict';

/**
 * browser-intercept.js
 * Eigent — Network Idle Detection (Race-Condition-Free)
 */

async function enableNetworkTracking(client, opts = {}) {
  const { maxTotalBuffer = 10485760, maxResourceBuffer = 5242880 } = opts;
  await client.Network.enable({
    maxTotalBufferSize: maxTotalBuffer,
    maxResourceBufferSize: maxResourceBuffer,
  });
}

async function waitForNetworkIdle(client, opts = {}) {
  const { idleMs = 500, timeoutMs = 30000, maxInflight = 0 } = opts;
  return new Promise((resolve, reject) => {
    let inflight = 0, requestCount = 0, settled = false, idleTimer = null, hardTimer = null;
    const startedAt = Date.now();

    function cleanup() {
      clearTimeout(idleTimer);
      clearTimeout(hardTimer);
      client.removeListener('Network.requestWillBeSent', onRequest);
      client.removeListener('Network.loadingFinished', onFinished);
      client.removeListener('Network.loadingFailed', onFailed);
    }

    function settle(fn, value) {
      if (settled) return;
      settled = true;
      cleanup();
      fn(value);
    }

    function armIdleTimer() {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => {
        if (inflight > maxInflight) return;
        settle(resolve, { requestCount, durationMs: Date.now() - startedAt });
      }, idleMs);
    }

    function onRequest() {
      requestCount++;
      inflight++;
      clearTimeout(idleTimer);
      idleTimer = null;
    }

    function onFinished() {
      if (inflight > 0) inflight--;
      if (inflight <= maxInflight) armIdleTimer();
    }

    function onFailed() {
      if (inflight > 0) inflight--;
      if (inflight <= maxInflight) armIdleTimer();
    }

    client.Network.on('requestWillBeSent', onRequest);
    client.Network.on('loadingFinished', onFinished);
    client.Network.on('loadingFailed', onFailed);

    hardTimer = setTimeout(() => {
      settle(reject, new Error('waitForNetworkIdle timed out after ' + timeoutMs + 'ms. (' + inflight + ' in-flight, ' + requestCount + ' total)'));
    }, timeoutMs);

    if (inflight <= maxInflight) armIdleTimer();
  });
}

async function navigateAndWait(client, url, idleOpts = {}) {
  await client.Page.navigate({ url });
  return waitForNetworkIdle(client, idleOpts);
}

module.exports = { enableNetworkTracking, waitForNetworkIdle, navigateAndWait };
