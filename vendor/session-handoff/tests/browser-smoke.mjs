// Development-only check. Pass an already installed Playwright module path.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const { chromium } = await import(pathToFileURL(process.argv[2]).href);
const source = await readFile(new URL('../session-handoff.mjs', import.meta.url));
const server = createServer((req, res) => {
  if (req.url === '/session-handoff.mjs') {
    res.writeHead(200, { 'Content-Type': 'text/javascript' }); res.end(source);
  } else { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end('<title>Session Handoff verification</title>'); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const result = await page.evaluate(async () => {
    const { run, resumePrompt, continuationBundle } = await import('/session-handoff.mjs');
    const now = Date.now();
    const environment = { workspaceId: 'browser-fixture', permissions: { mode: 'read-write' } };
    const snapshot = { workspace: { revision: 'fixture-v1' }, artifacts: [] };
    const evidence = fields => ({ source: 'synthetic host fixture', observedAt: now, independent: true, ...fields });
    const context = (sessionId, fields = {}) => ({ sessionId, source: 'synthetic context fixture', observedAt: now,
      effectiveWindowTokens: 100000, compactionBoundariesTokens: [60000], usedTokens: 10000,
      nextStepTokens: 14000, handoffReserveTokens: 6000, ...fields });
    let state = null;
    const step = async (op, fields = {}) => {
      const next = await run({ state, expectedRevision: state?.revision ?? 0, op, sessionId: state?.owner ?? 'browser-owner',
        now, maxAgeMs: 60000, ...fields });
      state = next.state; return next.result;
    };
    await step('arm', { explicit: true, chainId: 'browser-chain', mission: 'Preserve this browser mission.',
      goal: { objective: 'Complete the browser fixture', token_budget: 12000 }, goalBudgetExplicit: true, environment });
    const unknown = await step('check', { context: null });
    const projected = await step('check', { context: context(state.owner, { usedTokens: 42000 }) });
    await step('wind_down', { reason: 'Projected context crosses the host boundary.' });
    await step('checkpoint', { body: 'Synthetic browser checkpoint with goal and next action.', snapshot,
      continuation: { nextActions: [{ id: 'read-tracker', action: 'Read the live tracker.', reason: 'Verify current scope.' }],
        requiredArtifactIds: [], decisions: [], failedApproaches: [], openQuestions: [] } });
    await step('readback', { evidence: evidence({ kind: 'storage_readback', checkpointHash: state.checkpoint.hash,
      content: JSON.parse(JSON.stringify(state.checkpoint.content)) }) });
    const nonce = [...crypto.getRandomValues(new Uint8Array(16))].map(b => b.toString(16).padStart(2, '0')).join('');
    await step('reserve', { mode: 'new', nonce, snapshot, writersQuiesced: true, reviewSkipReason: 'No external reviewer in fixture.' });
    await step('launch_outcome', { outcome: 'created', nonce,
      evidence: evidence({ kind: 'host_session', sessionId: 'browser-candidate', status: 'starting', nonce }) });
    const bound = { sessionId: 'browser-candidate', nonce, checkpointHash: state.checkpoint.hash, environment, snapshot };
    const hostEvidence = evidence({ ...bound, kind: 'host_session', status: 'ready', checkpointReadAt: now,
      artifactsRead: [], firstActionId: 'read-tracker',
      goalEvidence: { sessionId: 'browser-candidate', status: 'active', goal: state.goal, createdAt: now, inspectedAt: now } });
    const acknowledgment = evidence({ ...bound, readComplete: true, firstAction: 'Read the live tracker.',
      artifactsRead: [], firstActionId: 'read-tracker', unresolvedPrerequisites: [],
      mission: state.mission, goal: state.goal, goalBudgetExplicit: true });
    const prompt = await resumePrompt({ state, checkpointLocation: 'synthetic-checkpoint' });
    const bundle = await continuationBundle({ state, checkpointLocation: 'synthetic-checkpoint', maxBytes: 4096 });
    await step('attest', { acknowledgment, hostEvidence, context: context('browser-candidate') });
    await step('transfer', { candidateId: 'browser-candidate', nonce, checkpointHash: state.checkpoint.hash,
      writersQuiesced: true, snapshot, hostEvidence, context: context('browser-candidate') });
    let predecessorRejected = false;
    try { await step('wind_down', { sessionId: 'browser-owner', reason: 'stale actor' }); }
    catch { predecessorRejected = true; }
    return { owner: state.owner, budget: state.goal.token_budget, unknown: unknown.decision,
      projected: projected.decision, predecessorRejected, promptHasDigest: /[a-f0-9]{64}/.test(prompt),
      bundleRequiresFullRead: bundle.requiresFullRead, bundleAction: bundle.firstAction.id };
  });
  assert.deepEqual(errors, []);
  assert.deepEqual(result, { owner: 'browser-candidate', budget: 12000, unknown: 'checkpoint_now',
    projected: 'handoff', predecessorRejected: true, promptHasDigest: true,
    bundleRequiresFullRead: true, bundleAction: 'read-tracker' });
  console.log(JSON.stringify({ browser: browser.version(), result, scope: 'Real Chromium execution; synthetic host evidence, no vendor session integration.' }));
} finally { await browser?.close(); await new Promise(resolve => server.close(resolve)); }
