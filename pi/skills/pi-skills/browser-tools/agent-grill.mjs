const QUESTIONS = [
  { key: 'intent', question: 'What exactly are you trying to do on this page?', required: true },
  { key: 'actionType', question: 'Is this a scrape, publish, monitor, or search?', required: true },
  { key: 'targetUrl', question: 'What is the exact URL (not "the dashboard" — the real URL)?', required: true },
  { key: 'idleMs', question: 'How long should we wait for the page to load before extracting? (ms)', default: 2000 },
  { key: 'successCriteria', question: 'What specific conditions prove the task succeeded? (array of strings)', required: true },
  { key: 'failureModes', question: 'What could go wrong? Rate limiting, missing elements, auth walls?', default: ['network timeout', 'element not found'] },
  { key: 'schema', question: 'What data to extract? JSON schema with selectors.', required: false },
  { key: 'actions', question: 'What UI actions to perform? Array of typed action objects.', required: false },
];

export function getQuestions() {
  return QUESTIONS;
}

export function validateTaskSpec(spec) {
  const errors = [];
  for (const q of QUESTIONS) {
    if (q.required && (spec[q.key] === undefined || spec[q.key] === null || spec[q.key] === '')) {
      errors.push(`${q.key}: ${q.question}`);
    }
  }
  if (spec.targetUrl && !spec.targetUrl.startsWith('http')) {
    errors.push('targetUrl must start with http:// or https://');
  }
  if (spec.successCriteria && !Array.isArray(spec.successCriteria)) {
    errors.push('successCriteria must be an array');
  }
  if (spec.failureModes && !Array.isArray(spec.failureModes)) {
    errors.push('failureModes must be an array');
  }
  return { valid: errors.length === 0, errors };
}

export async function grillTask(args) {
  if (args?.questions) {
    return { questions: QUESTIONS };
  }
  if (args?.validate) {
    return validateTaskSpec(JSON.parse(args.validate));
  }
  if (args?.answers) {
    const spec = {
      intent: args.answers.intent || '',
      actionType: args.answers.actionType || 'scrape',
      targetUrl: args.answers.targetUrl || '',
      idleMs: args.answers.idleMs || 2000,
      successCriteria: args.answers.successCriteria || [],
      failureModes: args.answers.failureModes || ['network timeout', 'element not found'],
      schema: args.answers.schema || null,
      actions: args.answers.actions || null,
      createdAt: new Date().toISOString(),
    };
    const validation = validateTaskSpec(spec);
    return { spec, validation };
  }
  return { questions: QUESTIONS, hint: 'Call with answers={...} to build a TaskSpec' };
}
