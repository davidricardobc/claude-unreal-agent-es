// generate.mjs contra un servidor simulado (sin ElevenLabs real, sin clave real).
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const GEN = path.join(HERE, '..', 'generate.mjs');

function run(args, env) {
  return new Promise((res) => {
    const p = spawn(process.execPath, [GEN, ...args], {env: {...process.env, ELEVENLABS_API_KEY: 'fake', ...env}, stdio: ['ignore', 'pipe', 'pipe']});
    let out = '';
    p.stdout.on('data', (d) => (out += d));
    p.stderr.on('data', (d) => (out += d));
    p.on('close', (code) => res({code, out}));
  });
}

test('dos lotes a la vez con el mismo catalogo no pasan --cap', async () => {
  let calls = 0;
  const srv = http.createServer((req, res) => {
    if (req.url.startsWith('/v1/user/subscription')) {
      res.setHeader('content-type', 'application/json');
      return res.end(JSON.stringify({character_count: 0, character_limit: 1000000, next_character_count_reset_unix: 1}));
    }
    calls++;
    req.resume();
    req.on('end', () => res.end(Buffer.from('FAKEAUDIO')));
  });
  await new Promise((r) => srv.listen(0, '127.0.0.1', r));
  const base = `http://127.0.0.1:${srv.address().port}/v1`;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sfxe2e-'));
  const rows = ['id,categoria,prompt,segundos'];
  for (const id of ['A1', 'A2', 'A3', 'B1', 'B2', 'B3']) rows.push(`${id},UI,A short click,2`);
  const csv = path.join(dir, 'm.csv');
  fs.writeFileSync(csv, rows.join('\n'));
  const env = {ELEVENLABS_API_BASE: base, KIT_START: '2020-01-01T00:00:00Z'};
  // 2 s a 10 créditos/s = 20 por toma. Tope 70 = 3 tomas en total (6 pedidas).
  const common = [csv, '--cap', '70', '--rate', '10', '--format', 'mp3_44100_192'];
  const [a, b] = await Promise.all([
    run([...common, '--only', 'A1,A2,A3'], env),
    run([...common, '--only', 'B1,B2,B3'], env),
  ]);
  srv.close();
  const cat = JSON.parse(fs.readFileSync(path.join(dir, 'audio-work', 'catalog.json'), 'utf8'));
  const ok = cat.entries.filter((e) => e.status === 'ok');
  assert.equal(ok.length, 3, a.out + b.out);
  assert.equal(calls, 3);
  assert.ok(ok.reduce((s, e) => s + e.credits_est, 0) <= 70);
  assert.ok(a.code === 2 || b.code === 2, 'al menos uno debe salir con codigo 2 por el tope');
});

test('antes del inicio oficial el lote sale con codigo 3', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sfxe2e-'));
  const csv = path.join(dir, 'm.csv');
  fs.writeFileSync(csv, 'id,categoria,prompt,segundos\nA,UI,click,1\n');
  const r = await run([csv, '--cap', '100', '--rate', '10'], {KIT_START: '2999-01-01T00:00:00Z', ELEVENLABS_API_BASE: 'http://127.0.0.1:9/v1'});
  assert.equal(r.code, 3, r.out);
  assert.ok(!fs.existsSync(path.join(dir, 'audio-work', 'raw')));
});

test('--dry no escribe nada', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sfxe2e-'));
  const csv = path.join(dir, 'm.csv');
  fs.writeFileSync(csv, 'id,categoria,prompt,segundos\nA,UI,click,1\n');
  const r = await run([csv, '--dry']);
  assert.equal(r.code, 0, r.out);
  assert.ok(!fs.existsSync(path.join(dir, 'audio-work')));
});
