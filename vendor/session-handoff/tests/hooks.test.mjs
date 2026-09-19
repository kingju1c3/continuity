import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, realpath, mkdir, writeFile, readFile, rm, symlink, chmod } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { evaluateCodexHook } from '../session-handoff.mjs';

const runtime = fileURLToPath(new URL('../session-handoff.mjs', import.meta.url));
const NOW = Date.now();
const control = { schema: 1, sessionId: 'root-session', cwd: '/workspace', armed: true, checkpointPath: '/workspace/checkpoint.md',
  boundaryTokens: 900, handoffReserveTokens: 100, maxNextStepTokens: 100 };
const event = { session_id: control.sessionId, cwd: control.cwd, hook_event_name: 'PreToolUse', turn_id: 'turn-1', tool_name: 'exec_command' };
const telemetry = { sessionId: control.sessionId, rootIdentityVerified: true, observedAt: NOW, usedTokens: 700, windowTokens: 1000 };
const evaluate = (extra = {}) => evaluateCodexHook({ event, control, telemetry, now: NOW, ...extra });

test('hook denies a risky ordinary tool once per turn and keeps native handoff calls available', () => {
  const first = evaluate();
  assert.equal(first.output.hookSpecificOutput.permissionDecision, 'deny');
  assert.deepEqual(evaluate({ marker: first.marker }).output, {});
  assert.equal(evaluate({ event: { ...event, turn_id: 'turn-2' }, marker: first.marker }).output.hookSpecificOutput.permissionDecision, 'deny');
  const native = evaluate({ event: { ...event, tool_name: 'mcp__codex_app__create_thread' } });
  assert.equal(native.output.hookSpecificOutput.permissionDecision, undefined);
  assert.match(native.output.hookSpecificOutput.additionalContext, /create_thread/);
  assert.deepEqual(evaluate({ telemetry: { ...telemetry, usedTokens: 699 } }).output, {});
});

test('unknown telemetry and boundary request early handoff; exact armed PreCompact stops', () => {
  const { boundaryTokens, ...unknown } = control;
  for (const extra of [{ control: unknown }, { telemetry: { ...telemetry, error: true } }, { telemetry: { ...telemetry, observedAt: NOW - 60001 } },
    { telemetry: { ...telemetry, observedAt: NOW + 1 } }, { telemetry: { ...telemetry, usedTokens: '700' } }]) {
    assert.equal(evaluate(extra).output.hookSpecificOutput.permissionDecision, 'deny');
  }
  const compact = evaluate({ event: { ...event, hook_event_name: 'PreCompact' }, telemetry: { ...telemetry, error: true } });
  assert.equal(compact.output.continue, false);
  assert.match(compact.output.stopReason, /Compaction stopped/);
  for (const extra of [{ control: null }, { control: { ...control, armed: false } }, { event: { ...event, session_id: 'other' } },
    { event: { ...event, cwd: '/different' } }, { telemetry: { unrelated: true } }]) assert.deepEqual(evaluate(extra).output, {});
  const missingTurn = { ...event }; delete missingTurn.turn_id;
  assert.equal(evaluate({ event: missingTurn }).output.hookSpecificOutput.permissionDecision, undefined);
  for (const hook_event_name of ['PreToolUse', 'PreCompact']) {
    const unknownIdentity = evaluate({ event: { ...event, hook_event_name }, telemetry: { error: true } });
    assert.equal(unknownIdentity.marker, null);
    assert.equal(unknownIdentity.output.continue, undefined);
    assert.equal(unknownIdentity.output.hookSpecificOutput, undefined);
    assert.ok(!JSON.stringify(unknownIdentity.output).includes('create_thread'));
  }
});

async function fixture() {
  const dir = await realpath(await mkdtemp(join(tmpdir(), 'handoff-hook-')));
  const home = join(dir, 'home'), cwd = join(dir, 'work');
  await mkdir(join(home, '.codex', 'session-handoff'), { recursive: true, mode: 0o700 });
  await mkdir(cwd);
  const checkpointPath = join(cwd, 'checkpoint.md'), transcriptPath = join(dir, 'exact.jsonl');
  const controlPath = join(home, '.codex', 'session-handoff', control.sessionId + '.json');
  const armed = { ...control, cwd, checkpointPath };
  await writeFile(checkpointPath, 'Exact checkpoint fixture.', { mode: 0o600 });
  const token = (input = 700, timestamp = new Date().toISOString()) => ({ timestamp, type: 'event_msg', payload: {
    type: 'token_count', info: { last_token_usage: { input_tokens: input, output_tokens: 0 }, model_context_window: 1000 } } });
  const saveTranscript = async (id = control.sessionId, source = 'cli', rows = [token()]) => writeFile(transcriptPath,
    [{ type: 'session_meta', payload: { id, source } }, ...rows].map(JSON.stringify).join('\n') + '\n');
  const saveControl = async (value = armed) => writeFile(controlPath, JSON.stringify(value), { mode: 0o600 });
  await saveControl(); await saveTranscript();
  const call = (changes = {}, entry = runtime) => {
    const result = spawnSync(process.execPath, [entry, '--codex-hook'], { cwd, env: { HOME: home, PATH: '' },
      input: JSON.stringify({ ...event, cwd, transcript_path: transcriptPath, ...changes }), encoding: 'utf8', timeout: 5000 });
    assert.equal(result.status, 0, result.stderr); assert.equal(result.stderr, '');
    return JSON.parse(result.stdout);
  };
  return { dir, home, cwd, controlPath, checkpointPath, transcriptPath, armed, token, saveControl, saveTranscript, call };
}

test('actual CLI reads only the exact transcript and persists a private per-turn feedback marker', async () => {
  const f = await fixture();
  try {
    assert.equal(f.call().hookSpecificOutput.permissionDecision, 'deny');
    assert.deepEqual(f.call(), {});
    assert.equal(f.call({ hook_event_name: 'PreCompact' }).continue, false);
    const marker = JSON.parse(await readFile(join(f.home, '.codex', 'session-handoff', control.sessionId + '.marker.json'), 'utf8'));
    assert.equal(marker.lastNotifiedTurn, 'turn-1');
    await f.saveTranscript('different-session');
    assert.deepEqual(f.call({ turn_id: 'turn-2' }), {});
    await f.saveTranscript(control.sessionId, { subagent: { parent_thread_id: control.sessionId } });
    assert.deepEqual(f.call({ hook_event_name: 'PreCompact' }), {});
    await f.saveTranscript(control.sessionId, 'cli', [f.token(100), { ...f.token(), payload: { type: 'token_count', info: null } }]);
    assert.equal(f.call({ turn_id: 'turn-3' }).hookSpecificOutput.permissionDecision, 'deny', 'invalid newest reading cannot fall back to older low usage');
    await f.saveControl({ ...f.armed, boundaryTokens: undefined });
    await f.saveTranscript(control.sessionId, 'cli', [f.token(100)]);
    assert.equal(f.call({ turn_id: 'turn-4' }).hookSpecificOutput.permissionDecision, 'deny');
  } finally { await rm(f.dir, { recursive: true, force: true }); }
});

test('actual CLI isolates unarmed sessions, refuses traversal and links, and emits safe structured faults', async () => {
  const f = await fixture();
  try {
    const runtimeLink = join(f.dir, 'installed-runtime.mjs'); await symlink(runtime, runtimeLink);
    assert.equal(f.call({ turn_id: 'symlink-entry' }, runtimeLink).hookSpecificOutput.permissionDecision, 'deny');
    assert.deepEqual(f.call({ session_id: '../other' }), {});
    assert.deepEqual(f.call({ session_id: 'unarmed-session' }), {});
    await f.saveControl({ ...f.armed, armed: false });
    assert.deepEqual(f.call({ hook_event_name: 'PreCompact' }), {});
    await f.saveControl();
    const link = join(f.dir, 'transcript-link'); await symlink(f.transcriptPath, link);
    assert.equal(f.call({ transcript_path: link }).hookSpecificOutput, undefined);
    for (const hook_event_name of ['PreToolUse', 'PreCompact']) {
      for (const transcript_path of [null, join(f.dir, 'unreadable-child-transcript'), link]) {
        const child = f.call({ hook_event_name, transcript_path, turn_id: 'child-turn' });
        assert.equal(child.continue, undefined);
        assert.equal(child.hookSpecificOutput, undefined);
        assert.ok(!JSON.stringify(child).includes('create_thread'));
      }
    }
    await chmod(f.controlPath, 0o644);
    assert.equal(f.call({ hook_event_name: 'PreCompact' }).continue, undefined);
    await chmod(f.controlPath, 0o600);
    await writeFile(f.controlPath, '{"armed":true,"secret":"DO-NOT-PRINT"');
    const fault = f.call({ hook_event_name: 'PreCompact' });
    assert.equal(fault.continue, undefined);
    assert.ok(!JSON.stringify(fault).includes('DO-NOT-PRINT'));
  } finally { await rm(f.dir, { recursive: true, force: true }); }
});
