import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, mkdir, copyFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { build, crc32, payloadFiles } from '../build.mjs';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
test('compiled archive contains only one runtime and complete standalone instructions', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'session-skill-'));
  try {
    assert.equal(crc32(Buffer.from('123456789')), 0xcbf43926);
    const built = await build(dir);
    assert.equal(built.payloadFiles, 4);
    const first = await readFile(join(dir, 'session-handoff.skill'));
    assert.deepEqual(first, await readFile(join(dir, 'session-handoff.zip')));
    assert.deepEqual(await readFile(join(dir, 'session-handoff.md')), await readFile(join(root, 'SKILL.md')));
    const names = [];
    let offset = 0;
    while (first.readUInt32LE(offset) === 0x04034b50) {
      const size = first.readUInt32LE(offset + 18);
      const n = first.readUInt16LE(offset + 26);
      const x = first.readUInt16LE(offset + 28);
      const name = first.subarray(offset + 30, offset + 30 + n).toString();
      const bytes = first.subarray(offset + 30 + n + x, offset + 30 + n + x + size);
      assert.deepEqual(bytes, await readFile(join(root, name.slice('session-handoff/'.length))));
      assert.equal(crc32(bytes), first.readUInt32LE(offset + 14));
      names.push(name);
      offset += 30 + n + x + size;
    }
    assert.deepEqual(names, payloadFiles.map(n => 'session-handoff/' + n));
    assert.equal(names.filter(n => n.endsWith('.mjs')).length, 1);
    const unzip = spawnSync('unzip', ['-t', join(dir, 'session-handoff.zip')], { encoding: 'utf8' });
    if (!unzip.error) assert.equal(unzip.status, 0, unzip.stdout + unzip.stderr);
    await build(dir);
    assert.deepEqual(first, await readFile(join(dir, 'session-handoff.skill')), 'reproducible build');
  } finally { await rm(dir, { recursive: true, force: true }); }
});

test('Gemini Spark guidance remains a manual, checkpoint-first handoff', async () => {
  const skill = await readFile(join(root, 'SKILL.md'), 'utf8');
  const readme = await readFile(join(root, 'README.md'), 'utf8');
  assert.match(skill, /### Gemini Spark: manual fresh-chat handoff/);
  assert.match(skill, /save and read back the complete checkpoint first/);
  assert.match(skill, /do not claim that a checkpoint can create a conversation automatically/);
  assert.doesNotMatch(skill, /default_api:create_conversation/);
  assert.match(readme, /Claude/, 'README names Claude support');
  assert.match(readme, /ChatGPT and Codex/, 'README names ChatGPT and Codex support');
  assert.match(readme, /Gemini Spark/, 'README names Gemini Spark support');
});

test('Engram support is optional and cannot replace handoff verification', async () => {
  const skill = await readFile(join(root, 'SKILL.md'), 'utf8');
  const readme = await readFile(join(root, 'README.md'), 'utf8');
  assert.match(skill, /### Optional Engram memory layer/);
  assert.match(skill, /user explicitly requests Engram/);
  assert.match(skill, /full checkpoint, candidate verification, ownership, or transfer gates/);
  assert.match(skill, /memory backend is unavailable in this session/);
  assert.match(readme, /## Optional Engram memory/);
});

test('engine imports in a clean process with no installed skills or companion files', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'session-clean-'));
  try {
    const home = join(dir, 'empty-home');
    await mkdir(home);
    const engine = join(dir, 'session-handoff.mjs');
    await copyFile(join(root, 'session-handoff.mjs'), engine);
    const code = `const m = await import(${JSON.stringify(pathToFileURL(engine).href)});
      const { state } = await m.run({state:null,expectedRevision:0,op:'arm',sessionId:'clean-owner',now:Date.now(),explicit:true,chainId:'clean-chain',mission:'Standalone check',environment:{}});
      const { result } = await m.run({state,expectedRevision:state.revision,op:'check',sessionId:state.owner,now:Date.now(),maxAgeMs:60000,context:null});
      if(result.decision!=='checkpoint_now') throw Error('standalone execution failed'); console.log('standalone execution passed');`;
    const result = spawnSync(process.execPath, ['--input-type=module', '-e', code], {
      cwd: dir, env: { HOME: home, USERPROFILE: home, PATH: '' }, encoding: 'utf8', timeout: 5000,
    });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /standalone execution passed/);
    const source = await readFile(engine, 'utf8');
    assert.doesNotMatch(source, /(?:from\s*['"]|require\s*\()/, 'no static or companion imports');
    assert.deepEqual([...source.matchAll(/import\(['"]([^'"]+)['"]\)/g)].map(match => match[1]).sort(),
      ['node:fs', 'node:fs/promises', 'node:path', 'node:url'], 'only CLI-scoped Node standard library imports');
  } finally { await rm(dir, { recursive: true, force: true }); }
});
