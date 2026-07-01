'use strict';

/**
 * browser-scrape.js
 * Eigent — Schema-Driven Structured Extraction ("The Eyes")
 */

const CDP = require('chrome-remote-interface');
const { startBrowser, stopBrowser } = require('./browser-start');
const { enableNetworkTracking, waitForNetworkIdle } = require('./browser-intercept');

const FIELD_TYPES = new Set(['text', 'html', 'attr', 'number', 'boolean', 'list', 'exists']);

function validateSchema(schema, path = 'schema') {
  if (typeof schema !== 'object' || schema === null || Array.isArray(schema)) {
    throw new TypeError(`${path} must be a plain object`);
  }
  for (const [key, field] of Object.entries(schema)) {
    const fp = `${path}.${key}`;
    if (typeof field !== 'object' || field === null) {
      throw new TypeError(`${fp} must be a field definition object`);
    }
    if (!field.selector) {
      throw new TypeError(`${fp}.selector is required`);
    }
    const type = field.type || 'text';
    if (!FIELD_TYPES.has(type)) {
      throw new TypeError(`${fp}.type "${type}" is invalid. Valid: ${[...FIELD_TYPES].join(', ')}`);
    }
    if (type === 'attr' && !field.attr) {
      throw new TypeError(`${fp}.attr is required when type is "attr"`);
    }
    if (type === 'list' && field.fields) {
      validateSchema(field.fields, `${fp}.fields`);
    }
    if (field.required !== undefined && typeof field.required !== 'boolean') {
      throw new TypeError(`${fp}.required must be a boolean`);
    }
  }
}

function buildSchemaExtractionScript(schema) {
  const schemaJson = JSON.stringify(schema);
  return `
(function extractSchema(schema, root) {
  root = root || document;
  function extractField(field, root) {
    const type     = field.type || 'text';
    const selector = field.selector;
    if (type === 'list') {
      const elements = Array.from(root.querySelectorAll(selector));
      const limit    = field.limit || 100;
      return elements.slice(0, limit).map(el =>
        field.fields ? extractSchema(field.fields, el) : (el.innerText || '').trim()
      );
    }
    if (type === 'exists') {
      return root.querySelector(selector) !== null;
    }
    const el = root.querySelector(selector);
    if (!el) return null;
    switch (type) {
      case 'html':    return el.innerHTML.trim();
      case 'attr':    return el.getAttribute(field.attr) || null;
      case 'number': {
        const raw = (el.innerText || el.textContent || '').trim();
        const cleaned = raw.replace(/[^\\d.-]/g, '');
        const n = parseFloat(cleaned);
        return isNaN(n) ? null : n;
      }
      case 'boolean': {
        const raw = (el.innerText || el.textContent || '').trim();
        if (field.pattern) return new RegExp(field.pattern, 'i').test(raw);
        return raw.length > 0;
      }
      default: return (el.innerText || el.textContent || '').trim();
    }
  }
  const result = {};
  for (const [key, field] of Object.entries(schema)) {
    result[key] = extractField(field, root);
  }
  return result;
})(${schemaJson}, document)
  `.trim();
}

function assertSchema(data, schema, path = '') {
  const errors = [];
  for (const [key, field] of Object.entries(schema)) {
    const fieldPath = path ? `${path}.${key}` : key;
    const value     = data[key];
    if (field.required) {
      if (value === null || value === undefined) {
        errors.push(`${fieldPath}: required but got null (selector "${field.selector}" matched nothing)`);
      } else if (field.type === 'list' && Array.isArray(value) && value.length === 0) {
        errors.push(`${fieldPath}: required list is empty (selector "${field.selector}" matched no elements)`);
      } else if (field.type === 'text' && typeof value === 'string' && value.trim() === '') {
        errors.push(`${fieldPath}: required text is empty`);
      }
    }
    if (field.type === 'list' && field.fields && Array.isArray(value)) {
      for (let i = 0; i < value.length; i++) {
        assertSchema(value[i], field.fields, `${fieldPath}[${i}]`);
      }
    }
  }
  if (errors.length > 0) {
    throw new Error(
      `Schema assertion failed (${errors.length} error${errors.length > 1 ? 's' : ''}):\n` +
      errors.map(e => `  • ${e}`).join('\n')
    );
  }
}

async function scrapePage(opts = {}) {
  const { url, schema, assert = true, port = null, headless = true, idleMs = 600, timeoutMs = 30_000 } = opts;
  if (!url || typeof url !== 'string') throw new Error('scrapePage: opts.url must be a non-empty string');
  if (!schema || typeof schema !== 'object') throw new Error('scrapePage: opts.schema must be a schema object');
  validateSchema(schema);
  const extractionScript = buildSchemaExtractionScript(schema);
  let browserHandle = null, client = null;
  try {
    if (port === null) browserHandle = await startBrowser({ headless, startupMs: 12_000 });
    client = await CDP({ port: port ?? browserHandle.port });
    await enableNetworkTracking(client);
    await client.Page.enable();
    await client.Page.navigate({ url });
    await waitForNetworkIdle(client, { idleMs, timeoutMs });
    const evaluation = await client.Runtime.evaluate({ expression: extractionScript, returnByValue: true, awaitPromise: false });
    if (evaluation.exceptionDetails) {
      const msg = evaluation.exceptionDetails.exception?.description || JSON.stringify(evaluation.exceptionDetails);
      throw new Error(`Schema extraction threw inside the page: ${msg}`);
    }
    const data = evaluation.result?.value ?? {};
    if (assert) assertSchema(data, schema);
    return data;
  } finally {
    if (client) { try { await client.close(); } catch (_) {} }
    if (browserHandle) stopBrowser(browserHandle);
  }
}

async function scrapeCurrentPage(client, schema, opts = {}) {
  const { assert = true } = opts;
  validateSchema(schema);
  const evaluation = await client.Runtime.evaluate({ expression: buildSchemaExtractionScript(schema), returnByValue: true, awaitPromise: false });
  if (evaluation.exceptionDetails) {
    const msg = evaluation.exceptionDetails.exception?.description || JSON.stringify(evaluation.exceptionDetails);
    throw new Error(`scrapeCurrentPage extraction error: ${msg}`);
  }
  const data = evaluation.result?.value ?? {};
  if (assert) assertSchema(data, schema);
  return data;
}

module.exports = { scrapePage, scrapeCurrentPage, validateSchema, assertSchema };
