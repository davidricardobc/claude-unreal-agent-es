// lib.mjs: partes puras y de disco de generate.mjs (se pueden probar sin red ni claves).
// CSV, validación, compuerta de inicio opcional y ledger con bloqueo para el tope de créditos entre procesos.
import fs from 'node:fs';
import path from 'node:path';

// Compuerta de inicio opcional (apagada por defecto): define KIT_START con una fecha ISO con zona (por ejemplo 2030-01-01T00:00:00-05:00)
// para bloquear la generación de audio del juego antes de ese momento (útil para concursos o hitos con hora de inicio).

export function parseCsv(text) {
  const rows = [];
  let row = [];
  let cur = '';
  let q = false;
  text = text.replace(/^\uFEFF/, '');
  const push = () => {
    row.push(cur);
    cur = '';
    if (row.some((c) => c.trim() !== '') && !row[0].trim().startsWith('#')) rows.push(row);
    row = [];
  };
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cur += '"';
          i++;
        } else q = false;
      } else cur += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') {
      row.push(cur);
      cur = '';
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      push();
    } else cur += ch;
  }
  if (cur !== '' || row.length) push();
  return rows;
}

const norm = (s) => s.trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
const ALIAS = {
  id: 'id', categoria: 'categoria', category: 'categoria', cat: 'categoria', prompt: 'prompt', text: 'prompt',
  segundos: 'segundos', seconds: 'segundos', duracion: 'segundos', duration: 'segundos', loop: 'loop',
  prompt_influence: 'influence', influence: 'influence', influencia: 'influence', tomas: 'tomas', takes: 'tomas',
};

export function validateManifest(text) {
  const errors = [];
  const warnings = [];
  const items = [];
  const rows = parseCsv(text);
  if (!rows.length) return {items, errors: ['CSV vacio'], warnings};
  const cols = {};
  rows[0].forEach((h, i) => {
    const k = ALIAS[norm(h)];
    if (k) cols[k] = i;
  });
  for (const need of ['id', 'categoria', 'prompt', 'segundos']) if (cols[need] === undefined) errors.push(`falta la columna "${need}"`);
  if (errors.length) return {items, errors, warnings};
  const seen = new Set();
  rows.slice(1).forEach((r, idx) => {
    const n = idx + 2; // número de fila contando el encabezado
    const g = (k) => (cols[k] === undefined ? '' : (r[cols[k]] ?? '').trim());
    const id = g('id');
    const cat = g('categoria');
    const prompt = g('prompt');
    const seg = Number(g('segundos'));
    const loopRaw = norm(g('loop'));
    const infRaw = g('influence');
    const takesRaw = g('tomas');
    const err = (m) => errors.push(`fila ${n} (${id || '?'}): ${m}`);
    const warn = (m) => warnings.push(`fila ${n} (${id || '?'}): ${m}`);
    if (!/^[A-Za-z0-9][A-Za-z0-9_]*$/.test(id)) err('id invalido (solo letras, numeros y guion bajo; sirve para el nombre del asset)');
    if (seen.has(id.toLowerCase())) err('id repetido');
    seen.add(id.toLowerCase());
    if (!/^[A-Za-z][A-Za-z0-9]*$/.test(cat)) err('categoria invalida (una palabra, ej. Mat, Wpn, Amb, UI, Eng)');
    if (!prompt) err('prompt vacio');
    else {
      if (/[^\x20-\x7E]/.test(prompt)) warn('el prompt tiene caracteres que no son ASCII: debe ir en ingles');
      if (prompt.length > 300) warn('prompt largo: la guia pide una frase concreta por sonido');
    }
    if (!Number.isFinite(seg) || seg < 0.5 || seg > 30) err(`segundos fuera de 0.5 a 30 (${g('segundos')})`);
    let loop = false;
    if (['1', 'true', 'si', 'yes', 'y', 's'].includes(loopRaw)) loop = true;
    else if (!['', '0', 'false', 'no', 'n'].includes(loopRaw)) err(`loop debe ser 0 o 1 (${g('loop')})`);
    if (loop && seg < 2) warn('bucle de menos de 2 s: el crossfade lo deja casi sin cuerpo');
    let influence = 0.3;
    if (infRaw !== '') {
      influence = Number(infRaw);
      if (!Number.isFinite(influence) || influence < 0 || influence > 1) err(`prompt_influence fuera de 0 a 1 (${infRaw})`);
    }
    let takes = 1;
    if (takesRaw !== '') {
      takes = Number(takesRaw);
      if (!Number.isInteger(takes) || takes < 1 || takes > 5) err(`tomas debe ser un entero de 1 a 5 (${takesRaw})`);
      else if (takes > 3) warn('mas de 3 tomas gasta creditos de mas');
    }
    items.push({id, categoria: cat, prompt, seconds: seg, loop, influence, takes});
  });
  return {items, errors, warnings};
}


// ---------- compuerta de inicio opcional ----------
// Acepta solo fechas ISO con zona explícita (Z o +-HH:MM): sin ella, Date.parse usaría la hora local.
// Sin valor (KIT_START sin definir o vacío) = sin compuerta: devuelve null.
export function parseStart(value) {
  if (value === undefined || value === null || value === '') return null;
  const v = value;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:\d{2})$/.test(v)) {
    throw new Error(`KIT_START "${v}" invalido: usa ISO con zona, por ejemplo 2030-01-01T00:00:00-05:00`);
  }
  const ms = Date.parse(v);
  if (!Number.isFinite(ms)) throw new Error(`KIT_START "${v}" no es una fecha`);
  return ms;
}
export const isBeforeStart = (nowMs, startMs) => startMs !== null && nowMs < startMs;
export const spentOf = (c) => c.entries.reduce((a, e) => a + (e.credits_real ?? e.credits_est ?? 0), 0);

// ---------- ledger con bloqueo (tope entre procesos) ----------
// catalog.json es la verdad de lo gastado. ledger.json guarda solo las reservas en vuelo de cada proceso.
// Toda lectura-modificación-escritura va bajo un archivo de bloqueo (mkdir atómico), así dos procesos
// no pasan el tope a la vez ni se pisan el catálogo.
const sleepSync = (ms) => Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);

export function createLedger(workDir, opts = {}) {
  const catalogPath = path.join(workDir, 'catalog.json');
  const ledgerPath = path.join(workDir, 'ledger.json');
  const lockPath = path.join(workDir, '.lock');
  const staleMs = opts.staleMs ?? 30 * 60 * 1000; // reserva de un proceso caído
  const lockStaleMs = 15000;
  fs.mkdirSync(workDir, {recursive: true});

  const readJson = (p, dflt) => (fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, 'utf8')) : dflt);
  const writeJson = (p, o) => {
    fs.writeFileSync(`${p}.tmp`, JSON.stringify(o, null, 2) + '\n');
    fs.renameSync(`${p}.tmp`, p);
  };
  const alive = (pid) => {
    try { process.kill(pid, 0); return true; } catch (e) { return e.code === 'EPERM'; }
  };

  function withLock(fn) {
    const t0 = Date.now();
    for (;;) {
      try { fs.mkdirSync(lockPath); break; } catch (e) {
        if (e.code !== 'EEXIST') throw e;
        try { if (Date.now() - fs.statSync(lockPath).mtimeMs > lockStaleMs) fs.rmdirSync(lockPath); } catch { /* otro la liberó */ }
        if (Date.now() - t0 > 30000) throw new Error(`No pude tomar el bloqueo ${lockPath} en 30 s`);
        sleepSync(5 + Math.floor(Math.random() * 15));
      }
    }
    try { return fn(); } finally { try { fs.rmdirSync(lockPath); } catch { /* ya no está */ } }
  }

  const loadCatalogRaw = (dflt) => readJson(catalogPath, dflt);
  function pendingSum(ledger) {
    let n = 0;
    for (const [tok, r] of Object.entries(ledger.pending)) {
      if (Date.now() - r.t > staleMs || !alive(r.pid)) delete ledger.pending[tok];
      else n += r.est;
    }
    return n;
  }

  return {
    catalogPath,
    withLock,
    // Reserva est créditos. Devuelve {ok, token, spent} o {ok:false, spent, reason}.
    reserve(est, cap, label = '') {
      return withLock(() => {
        const cat = loadCatalogRaw({entries: []});
        const led = readJson(ledgerPath, {pending: {}});
        const spent = spentOf(cat) + pendingSum(led);
        if (spent + est > cap) { writeJson(ledgerPath, led); return {ok: false, spent, reason: `TOPE ${cap}: llevo ${spent} y ${label} costaria ${est}`}; }
        const token = `${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        led.pending[token] = {pid: process.pid, est, t: Date.now(), label};
        writeJson(ledgerPath, led);
        return {ok: true, token, spent: spent + est};
      });
    },
    release(token) {
      withLock(() => {
        const led = readJson(ledgerPath, {pending: {}});
        delete led.pending[token];
        writeJson(ledgerPath, led);
      });
    },
    // Suma una entrada al catálogo fresco (sin pisar lo de otros procesos) y cierra la reserva.
    commit(token, entry, mutate, dflt) {
      return withLock(() => {
        const cat = loadCatalogRaw(dflt ?? {version: 1, entries: []});
        if (mutate) mutate(cat);
        if (entry) cat.entries.push(entry);
        writeJson(catalogPath, cat);
        if (token) {
          const led = readJson(ledgerPath, {pending: {}});
          delete led.pending[token];
          writeJson(ledgerPath, led);
        }
        return cat;
      });
    },
    // Cambia el catálogo bajo bloqueo (tarifa, etc.).
    update(mutate, dflt) {
      return this.commit(null, null, mutate, dflt);
    },
    spent() {
      return withLock(() => spentOf(loadCatalogRaw({entries: []})) + pendingSum(readJson(ledgerPath, {pending: {}})));
    },
  };
}
