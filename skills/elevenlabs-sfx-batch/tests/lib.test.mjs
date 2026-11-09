// Pruebas de las partes puras. Sin red ni claves. Correr: node --test .claude/skills/elevenlabs-sfx-batch/tests
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {parseCsv, validateManifest, parseStart, isBeforeStart, createLedger, spentOf} from '../lib.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'sfx-'));

// ---------- CSV y manifiesto ----------
test('parseCsv: comillas, comas, BOM, CRLF y comentarios', () => {
  const rows = parseCsv('﻿id,prompt\r\n# comentario\r\nA,"hit, hard ""x"""\r\n\r\nB,plain');
  assert.deepEqual(rows, [['id', 'prompt'], ['A', 'hit, hard "x"'], ['B', 'plain']]);
});

test('validateManifest: fila buena con valores por defecto', () => {
  const m = validateManifest('id,categoria,prompt,segundos\nClick,UI,A short click,1.5\n');
  assert.equal(m.errors.length, 0);
  assert.deepEqual(m.items[0], {id: 'Click', categoria: 'UI', prompt: 'A short click', seconds: 1.5, loop: false, influence: 0.3, takes: 1});
});

test('validateManifest: filas malas', () => {
  const csv = [
    'id,categoria,prompt,segundos,loop,prompt_influence,tomas',
    'bad id,UI,x,1,0,,1',
    'A,UI,,1,0,,1',
    'B,UI,x,31,0,,1',
    'C,UI,x,1,quizas,,1',
    'D,UI,x,1,0,1.5,1',
    'E,UI,x,1,0,,9',
    'E,UI,x,1,0,,1',
  ].join('\n');
  const e = validateManifest(csv).errors.join('\n');
  for (const frag of ['id invalido', 'prompt vacio', 'segundos fuera', 'loop debe ser', 'prompt_influence fuera', 'tomas debe ser', 'id repetido']) assert.match(e, new RegExp(frag));
});

test('validateManifest: falta columna y avisos', () => {
  assert.match(validateManifest('id,prompt\nA,x').errors.join(), /falta la columna/);
  const w = validateManifest('id,categoria,prompt,segundos,loop\nA,UI,sonido en espaÃ±ol,1,1\n').warnings.join();
  assert.match(w, /ASCII/);
  assert.match(w, /bucle de menos de 2 s/);
});

test('el CSV de ejemplo valida sin errores', () => {
  const m = validateManifest(fs.readFileSync(path.join(HERE, '..', 'audio-manifest.example.csv'), 'utf8'));
  assert.deepEqual(m.errors, []);
  assert.ok(m.items.length >= 10);
});

// ---------- compuerta de inicio opcional ----------
test('without KIT_START there is no gate', () => {
  assert.equal(parseStart(undefined), null);
  assert.equal(parseStart(''), null);
  assert.equal(isBeforeStart(Date.parse('2001-01-01T00:00:00Z'), null), false);
});

test('isBeforeStart: before and after a configured start', () => {
  const s = parseStart('2030-01-01T00:00:00-05:00');
  assert.equal(new Date(s).toISOString(), '2030-01-01T05:00:00.000Z');
  assert.equal(isBeforeStart(Date.parse('2029-12-31T23:59:59-05:00'), s), true);
  assert.equal(isBeforeStart(Date.parse('2030-01-01T00:00:00-05:00'), s), false);
  assert.equal(isBeforeStart(Date.parse('2030-01-01T04:59:59Z'), s), true); // aún es 31-dic en UTC-5
});

test('parseStart rejects dates without zone or garbage', () => {
  assert.throws(() => parseStart('2030-01-01T00:00:00'), /invalido/);
  assert.throws(() => parseStart('ayer'), /invalido/);
  assert.throws(() => parseStart('2030-13-45T00:00:00Z'), /no es una fecha/);
});

// ---------- tope de créditos ----------
test('spentOf: real manda sobre estimado', () => {
  assert.equal(spentOf({entries: [{credits_real: 10, credits_est: 99}, {credits_est: 5}, {}]}), 15);
});

test('ledger: reserva, tope, liberacion y commit', () => {
  const L = createLedger(tmp());
  const a = L.reserve(40, 100, 'a');
  const b = L.reserve(40, 100, 'b');
  const c = L.reserve(40, 100, 'c');
  assert.equal(a.ok && b.ok, true);
  assert.equal(c.ok, false);
  assert.match(c.reason, /TOPE 100/);
  L.release(b.token);
  assert.equal(L.reserve(40, 100, 'c').ok, true);
  L.commit(a.token, {id: 'a', take: 1, status: 'ok', credits_est: 40});
  assert.equal(L.spent(), 80); // 40 en catálogo + 40 reservados de c
});

test('ledger: reserva de un proceso caido no bloquea para siempre', () => {
  const dir = tmp();
  const L = createLedger(dir, {staleMs: 1});
  assert.equal(L.reserve(90, 100, 'x').ok, true);
  const t0 = Date.now();
  while (Date.now() - t0 < 5);
  assert.equal(L.reserve(90, 100, 'y').ok, true);
});

test('ledger: dos procesos a la vez no pasan el tope', async () => {
  const dir = tmp();
  const worker = path.join(HERE, 'reserve-worker.mjs');
  const run = () => new Promise((res) => {
    const p = spawn(process.execPath, [worker, dir, '100', '10', '30'], {stdio: ['ignore', 'pipe', 'inherit']});
    let out = '';
    p.stdout.on('data', (d) => (out += d));
    p.on('close', () => res(Number(out.trim())));
  });
  const got = (await Promise.all([run(), run(), run()])).reduce((a, b) => a + b, 0);
  assert.equal(got, 10); // cap 100 / est 10 = 10 pagos en total entre 3 procesos, sin pasarse
  const cat = JSON.parse(fs.readFileSync(path.join(dir, 'catalog.json'), 'utf8'));
  assert.equal(cat.entries.length, 10); // nadie pisó el catálogo de otro
  assert.equal(spentOf(cat), 100);
});
