// generate.mjs: de un audio-manifest.csv a efectos de ElevenLabs (v3) con tope de créditos.
// Adaptado de <AUDIO_LIBRARY>/scripts\generar.mjs (idempotente, tope, concurrencia, reintento en 429).
//
// Uso (desde la raíz del proyecto):
//   node .claude/skills/elevenlabs-sfx-batch/generate.mjs <manifest.csv> --dry
//   node .../generate.mjs <manifest.csv> --probe
//   node .../generate.mjs <manifest.csv> --cap 6000 [--only Id,Id] [--regen Id] [--c 2] [--format wav_48000]
//   node .../generate.mjs <manifest.csv> --set-rate 12      (tarifa en créditos por segundo, a mano)
//
// - --dry no usa red, no pide clave y no escribe nada: valida el CSV y estima el costo.
// - Siempre manda model_id eleven_text_to_sound_v3 (el valor por defecto de la API es v2, que se retira el 1-mar-2027).
// - Nunca repite lo ya pagado: catalog.json (fecha, créditos, prompt, formato por archivo) y el archivo en disco.
// - Compuerta de inicio opcional (apagada por defecto): con KIT_START definido, antes de ese momento solo --probe y hasta 10 pruebas con --allow-early.
// - Clave: variable ELEVENLABS_API_KEY, o si no existe la función readKey() del harness
//   (<HARNESS_DIR>, carpeta cambiable con HARNESS_DIR). Aquí nunca se lee un .env ni se imprime la clave.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {parseStart, isBeforeStart, spentOf, createLedger, validateManifest} from './lib.mjs';
export {parseCsv, validateManifest} from './lib.mjs';

const API = process.env.ELEVENLABS_API_BASE ?? 'https://api.elevenlabs.io/v1'; // la variable solo sirve para pruebas con un servidor falso
const MODEL = 'eleven_text_to_sound_v3';
let KIT_START;
try { KIT_START = parseStart(process.env.KIT_START); } catch (e) { console.error(e.message); process.exit(1); }
const EARLY_MAX = 10;
const RATE_LOW = 12; // medido el 1-nov (probablemente v2)
const RATE_HIGH = 40; // documentación oficial, duración fija
const BALANCE_RESERVE = 2000;
const FORMATS = ['wav_48000', 'mp3_44100_192'];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const nowIso = () => new Date().toISOString();

// ---------- argumentos ----------
const BOOL = new Set(['dry', 'probe', 'allow-early', 'help']);
const args = process.argv.slice(2);
const flags = {};
const pos = [];
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a.startsWith('--')) {
    const k = a.slice(2);
    if (BOOL.has(k)) flags[k] = true;
    else flags[k] = args[++i];
  } else pos.push(a);
}
if (flags.help || !pos[0]) {
  console.log('Uso: node generate.mjs <manifest.csv> [--dry | --probe | --cap N] [--only a,b] [--regen a,b] [--c 2] [--format wav_48000|mp3_44100_192] [--rate N] [--set-rate N] [--work DIR] [--plan Creator] [--allow-early]');
  process.exit(flags.help ? 0 : 1);
}
const manifestPath = path.resolve(pos[0]);
const workDir = path.resolve(flags.work ?? path.join(path.dirname(manifestPath), 'audio-work'));
const catalogPath = path.join(workDir, 'catalog.json');
const onlySet = flags.only ? new Set(flags.only.split(',').map((s) => s.trim())) : null;
const regenSet = flags.regen ? new Set(flags.regen.split(',').map((s) => s.trim())) : new Set();
const conc = Math.max(1, Math.min(4, Number(flags.c ?? 2)));
const plan = flags.plan ?? 'Creator';

// ---------- catálogo ----------
function loadCatalog() {
  if (fs.existsSync(catalogPath)) return JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
  return {version: 1, model: MODEL, plan, rates: null, entries: []};
}
let ledgerCache;
const ledger = () => (ledgerCache ??= createLedger(workDir)); // crea la carpeta de trabajo solo cuando hace falta escribir
const catalogDefault = () => ({version: 1, model: MODEL, plan, rates: null, entries: []});
const nn = (t) => String(t).padStart(2, '0');
const extOf = (fmt) => (fmt.startsWith('wav') ? 'wav' : 'mp3');
const rawFile = (it, take, fmt) => path.join(workDir, 'raw', it.categoria, `${it.id}_${nn(take)}.${extOf(fmt)}`);
const existingFile = (it, take) => ['wav', 'mp3'].map((e) => rawFile(it, take, e)).find((f) => fs.existsSync(f));

// ---------- clave y API ----------
let keyCache;
async function getKey() {
  if (keyCache) return keyCache;
  if (process.env.ELEVENLABS_API_KEY) return (keyCache = process.env.ELEVENLABS_API_KEY);
  const harness = process.env.HARNESS_DIR ?? '<HARNESS_DIR>';
  const mod = await import(pathToFileURL(path.join(harness, 'scripts/lib/elevenlabs.mjs')).href);
  return (keyCache = mod.readKey());
}
async function subscription() {
  const res = await fetch(`${API}/user/subscription`, {headers: {'xi-api-key': await getKey()}});
  if (!res.ok) throw new Error(`ElevenLabs ${res.status}: ${(await res.text()).slice(0, 200)}`);
  const s = await res.json();
  return {used: s.character_count, limit: s.character_limit, reset: s.next_character_count_reset_unix};
}
// Un fallo no cobra. Reintenta solo 429 y 5xx, respetando retry-after.
async function postSfx(body, format, tries = 6) {
  let last;
  for (let i = 0; i < tries; i++) {
    const res = await fetch(`${API}/sound-generation?output_format=${format}`, {
      method: 'POST',
      headers: {'xi-api-key': await getKey(), 'content-type': 'application/json'},
      body: JSON.stringify(body),
    });
    if (res.ok) {
      const buf = Buffer.from(await res.arrayBuffer());
      const h = res.headers.get('character-cost'); // la doc no lo lista; si llega, es el costo real
      buf.cost = h !== null && Number.isFinite(Number(h)) ? Number(h) : null;
      return buf;
    }
    last = new Error(`ElevenLabs ${res.status}: ${(await res.text()).slice(0, 300)}`);
    last.status = res.status;
    if (res.status !== 429 && res.status < 500) throw last;
    const ra = Number(res.headers.get('retry-after'));
    await sleep(Number.isFinite(ra) && ra > 0 ? ra * 1000 : Math.min(60000, 5000 * 2 ** i));
  }
  throw last;
}
function writeNew(file, buf) {
  fs.mkdirSync(path.dirname(file), {recursive: true});
  if (fs.existsSync(file)) throw new Error(`Ya existe ${file}; no se sobrescribe.`);
  fs.writeFileSync(`${file}.tmp`, buf);
  fs.renameSync(`${file}.tmp`, file);
}

// ---------- plan de trabajo ----------
const manifest = validateManifest(fs.readFileSync(manifestPath, 'utf8'));
manifest.warnings.forEach((w) => console.log(`aviso ${w}`));
if (manifest.errors.length) {
  manifest.errors.forEach((e) => console.error(`ERROR ${e}`));
  console.error(`CSV invalido: ${manifest.errors.length} error(es). No se llamo a la API.`);
  process.exit(1);
}
const catalog = loadCatalog();
const active = (id, take) => catalog.entries.find((e) => e.id === id && e.take === take && e.status === 'ok');
const items = manifest.items.filter((it) => !onlySet || onlySet.has(it.id));
const jobs = [];
let already = 0;
for (const it of items) {
  for (let take = 1; take <= it.takes; take++) {
    const done = active(it.id, take);
    const file = existingFile(it, take);
    if (regenSet.has(it.id)) {
      jobs.push({it, take, regen: true});
      continue;
    }
    if (done || file) {
      already++;
      if (done && done.prompt !== it.prompt) console.log(`aviso ${it.id}_${nn(take)}: el prompt cambio despues de pagarlo. No se regenera; usa --regen ${it.id} si lo quieres de nuevo.`);
      if (!done && file) console.log(`aviso ${it.id}_${nn(take)}: el archivo existe sin catalogo; se trata como pagado.`);
      continue;
    }
    jobs.push({it, take});
  }
}
const sum = (list, f) => list.reduce((a, j) => a + f(j), 0);
const secs = sum(jobs, (j) => j.it.seconds);
const measured = catalog.rates?.per_second ?? null;
const planRate = flags.rate ? Number(flags.rate) : measured ?? RATE_HIGH;

console.log(`Manifiesto: ${manifest.items.length} filas. Tomas ya pagadas: ${already}. Por generar: ${jobs.length} tomas, ${secs.toFixed(1)} s.`);
const byCat = {};
for (const j of jobs) {
  const b = (byCat[j.it.categoria] ??= {n: 0, s: 0});
  b.n++;
  b.s += j.it.seconds;
}
for (const [c, v] of Object.entries(byCat)) console.log(`  ${c.padEnd(8)} ${String(v.n).padStart(3)} tomas  ${v.s.toFixed(1).padStart(6)} s`);
console.log(`Costo estimado: a ${RATE_LOW}/s = ${Math.ceil(secs * RATE_LOW)}; a ${RATE_HIGH}/s = ${Math.ceil(secs * RATE_HIGH)}${measured ? `; a la tarifa medida ${measured}/s = ${Math.ceil(secs * measured)}` : '; sin tarifa medida (corre --probe)'}. Gastado segun catalog.json: ${spentOf(catalog)}.`);
if (flags.cap) console.log(`Tope --cap ${flags.cap}: ${spentOf(catalog) + Math.ceil(secs * planRate) > Number(flags.cap) ? 'NO alcanza con la tarifa de planeacion, el lote se detendra solo' : 'alcanza'}.`);
if (flags.dry) {
  console.log('Modo --dry: no se llamo a la API ni se escribio nada.');
  process.exit(0);
}

if (flags['set-rate']) {
  ledger().update((c) => {
    c.rates = {...(c.rates ?? {}), per_second: Number(flags['set-rate']), model: MODEL, format: c.rates?.format ?? FORMATS[0], measured_at: nowIso(), source: 'manual'};
  }, catalogDefault());
  console.log(`Tarifa guardada: ${flags['set-rate']} creditos por segundo.`);
  process.exit(0);
}

// ---------- regla de fechas ----------
const early = isBeforeStart(Date.now(), KIT_START);
const earlyUsed = catalog.entries.filter((e) => e.early).length;
if (early && !flags.probe) {
  if (!flags['allow-early']) {
    console.error(`Antes de ${new Date(KIT_START).toISOString()} no se genera audio del juego. Usa --dry, o --allow-early con --only para una prueba de herramienta (maximo ${EARLY_MAX}, se declaran).`);
    process.exit(3);
  }
  if (earlyUsed + jobs.length > EARLY_MAX) {
    console.error(`Pruebas antes del inicio: ${earlyUsed} hechas, ${jobs.length} pedidas, maximo ${EARLY_MAX}.`);
    process.exit(3);
  }
}

// ---------- prueba de 1 s: mide la tarifa real de v3 ----------
// Sin process.exit al final: en Windows cerrar de golpe los sockets de fetch tumba Node.
async function runProbe() {
  if (early && earlyUsed >= EARLY_MAX) {
    console.error('Ya se hicieron las 10 pruebas previas permitidas.');
    process.exitCode = 3;
    return;
  }
  const body = {text: 'A single short plastic click, close, dry, no music', duration_seconds: 1, prompt_influence: 0.6, model_id: MODEL};
  const before = await subscription();
  let fmt = flags.format ?? FORMATS[0];
  let buf;
  try {
    buf = await postSfx(body, fmt);
  } catch (e) {
    if (flags.format || ![400, 402, 403, 422].includes(e.status)) throw e;
    console.log(`${fmt} no se acepto en este plan (${e.status}); pruebo ${FORMATS[1]}.`);
    fmt = FORMATS[1];
    buf = await postSfx(body, fmt);
  }
  const f = path.join(workDir, 'raw', '_probe', `probe_${Date.now()}.${extOf(fmt)}`);
  writeNew(f, buf);
  let newRates;
  let credits = buf.cost;
  let source = 'header';
  if (credits === null) {
    source = 'subscription';
    for (let i = 0; i < 9 && credits === null; i++) {
      await sleep(20000); // el contador de la cuenta tarda en reflejarse
      const after = await subscription();
      if (after.used > before.used && after.reset === before.reset) credits = after.used - before.used;
    }
  }
  if (credits === null) {
    console.log('El saldo no cambio en 3 minutos. Lee el saldo en la pagina de ElevenLabs y guardalo con --set-rate N (creditos por segundo).');
    newRates = {...(catalog.rates ?? {}), model: MODEL, format: fmt, per_second: null, source: 'sin medir'};
  } else {
    newRates = {per_second: credits / 1, probe_credits: credits, probe_seconds: 1, model: MODEL, format: fmt, measured_at: nowIso(), source};
    console.log(`Tarifa medida con v3: ${credits} creditos por la prueba de 1 s (${source}). Formato que acepta el plan: ${fmt}. Si el minimo por llamada domina, la tarifa real por segundo es menor: es un tope prudente.`);
  }
  const entry = ({id: '_probe', take: 1, file: path.relative(workDir, f).replaceAll('\\', '/'), prompt: body.text, seconds: 1, model: MODEL, format: fmt, plan, date: nowIso(), credits_est: credits ?? 0, credits_real: credits, status: 'probe', early});
  ledger().commit(null, entry, (c) => { c.rates = newRates; }, catalogDefault());
}

// ---------- lote ----------
async function runBatch() {
  if (!flags.cap || !(Number(flags.cap) > 0)) {
    console.error('Falta --cap N (tope de creditos acumulado de este catalogo). Sin tope no se genera.');
    process.exit(1);
  }
  if (!measured && !flags.rate) {
    console.error('No hay tarifa medida: corre --probe primero (o pasa --rate N para presupuestar a ojo).');
    process.exit(1);
  }
  const cap = Number(flags.cap);
  const format = flags.format ?? catalog.rates?.format ?? FORMATS[0];
  if (!FORMATS.includes(format)) {
    console.error(`Formato ${format} no soportado por este script (usa ${FORMATS.join(' o ')}).`);
    process.exit(1);
  }
  const L = ledger();
  let spent = L.spent();
  let stop = null;
  let ok = 0;
  let count = 0;
  const regenIds = new Set();
  const queue = [...jobs];

  async function worker() {
    while (queue.length && !stop) {
      const {it, take, regen} = queue.shift();
      const est = Math.ceil(it.seconds * planRate);
      // Reserva atómica entre procesos (ledger con archivo de bloqueo) ANTES de cualquier await.
      const r = L.reserve(est, cap, `${it.id}_${nn(take)}`);
      if (!r.ok) {
        stop = new Error(`${r.reason}. Me detengo.`);
        break;
      }
      const token = r.token;
      spent = r.spent;
      if (count++ % 10 === 0) {
        try {
          const s = await subscription();
          if (s.limit - s.used < est + BALANCE_RESERVE) {
            L.release(token);
            stop = new Error(`Saldo de la cuenta bajo (${s.limit - s.used}). Me detengo.`);
            break;
          }
        } catch (e) {
          console.log(`aviso: no pude leer el saldo (${e.message.slice(0, 80)}); sigo con el tope local.`);
        }
      }
      try {
        if (regen) {
          const old = existingFile(it, take);
          if (old) {
            const dest = path.join(workDir, 'raw', '_replaced', `${path.basename(old, path.extname(old))}_${Date.now()}${path.extname(old)}`);
            fs.mkdirSync(path.dirname(dest), {recursive: true});
            fs.renameSync(old, dest);
          }
          regenIds.add(`${it.id}#${take}`);
        }
        const body = {text: it.prompt, duration_seconds: it.seconds, prompt_influence: it.influence, model_id: MODEL};
        if (it.loop) body.loop = true;
        let buf;
        try {
          buf = await postSfx(body, format);
        } catch (e) {
          if (it.loop && (e.status === 400 || e.status === 422)) {
            delete body.loop; // si v3 no acepta loop, el bucle lo arma postprocess.mjs
            console.log(`aviso ${it.id}: loop no aceptado, se genera sin loop y el bucle se arma con crossfade`);
            buf = await postSfx(body, format);
          } else throw e;
        }
        const file = rawFile(it, take, format);
        writeNew(file, buf);
        const entry = ({
          id: it.id, take, categoria: it.categoria, file: path.relative(workDir, file).replaceAll('\\', '/'), prompt: it.prompt,
          seconds: it.seconds, loop: it.loop, prompt_influence: it.influence, model: MODEL, format, plan, date: nowIso(),
          credits_est: est, credits_real: buf.cost, status: 'ok', early,
        });
        const wasRegen = regenIds.delete(`${it.id}#${take}`);
        L.commit(token, entry, wasRegen ? (c) => c.entries.filter((e) => e.id === it.id && e.take === take && e.status === 'ok').forEach((e) => (e.status = 'replaced')) : null, catalogDefault());
        spent += (buf.cost ?? est) - est;
        ok++;
        console.log(`+ ${it.id}_${nn(take)} (${it.seconds} s, est ${est}${buf.cost !== null ? `, real ${buf.cost}` : ''}; acumulado ${spent}/${cap})`);
      } catch (e) {
        L.release(token);
        spent -= est;
        console.error(`x ${it.id}_${nn(take)}: ${e.message}`);
        if (e.status === 401 || e.status === 402) stop = e;
      }
      await sleep(1500);
    }
  }
  await Promise.all(Array.from({length: conc}, worker));
  console.log(`Listo: ${ok} de ${jobs.length} generadas. Acumulado ${spent}/${cap}.${stop ? ' DETENIDO: ' + stop.message : ''}`);
  if (stop) process.exitCode = 2;
}

if (flags.probe) await runProbe();
else await runBatch();
