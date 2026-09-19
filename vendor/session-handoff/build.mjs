#!/usr/bin/env node
// Build one self-contained installable archive. No package manager required.
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';
import { createHash } from 'node:crypto';

export const payloadFiles = ['SKILL.md', 'session-handoff.mjs', 'README.md', 'LICENSE'];
const root = dirname(fileURLToPath(import.meta.url));

export function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

// ZIP stored entries: a small skill does not need a compression dependency.
export function archive(entries) {
  const locals = [], central = [];
  let offset = 0;
  for (const { name, bytes } of entries) {
    if (!/^session-handoff\/[A-Za-z0-9.-]+$/.test(name)) throw Error('Unsafe package path');
    const path = Buffer.from(name);
    const crc = crc32(bytes);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(33, 12); // Stable 1980-01-01 ZIP date.
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(bytes.length, 18);
    local.writeUInt32LE(bytes.length, 22);
    local.writeUInt16LE(path.length, 26);
    locals.push(local, path, bytes);
    const header = Buffer.alloc(46);
    header.writeUInt32LE(0x02014b50);
    header.writeUInt16LE(20, 4);
    header.writeUInt16LE(20, 6);
    header.writeUInt16LE(33, 14);
    header.writeUInt32LE(crc, 16);
    header.writeUInt32LE(bytes.length, 20);
    header.writeUInt32LE(bytes.length, 24);
    header.writeUInt16LE(path.length, 28);
    header.writeUInt32LE(offset, 42);
    central.push(header, path);
    offset += local.length + path.length + bytes.length;
  }
  const directory = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(directory.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, directory, end]);
}

export async function build(output = join(root, 'dist')) {
  const entries = await Promise.all(payloadFiles.map(async name => ({
    name: 'session-handoff/' + name, bytes: await readFile(join(root, name)),
  })));
  const skill = entries[0].bytes.toString('utf8');
  if (!/^---\nname: session-handoff\n/.test(skill)) throw Error('Invalid skill identity');
  if (skill.split('\n').length > 500) throw Error('Keep the complete skill under 500 lines');
  if (entries.some(e => e.bytes.toString('utf8').includes(['terminal','handoff'].join('-')))) {
    throw Error('Package contains an obsolete companion-skill reference');
  }
  const zip = archive(entries);
  await mkdir(output, { recursive: true });
  const artifacts = [
    ['session-handoff.skill', zip], ['session-handoff.zip', zip],
    ['session-handoff.md', entries[0].bytes],
  ];
  for (const [name, bytes] of artifacts) await writeFile(join(output, name), bytes);
  const hashes = artifacts.map(([name, bytes]) =>
    createHash('sha256').update(bytes).digest('hex') + '  ' + name).join('\n') + '\n';
  await writeFile(join(output, 'SHA256SUMS'), hashes);
  return { files: artifacts.map(([name]) => join(output, name)), payloadFiles: payloadFiles.length };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = await build(process.argv[2] ? resolve(process.argv[2]) : undefined);
  console.log(JSON.stringify(result, null, 2));
}
