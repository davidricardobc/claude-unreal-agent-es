// postprocess.mjs: de raw/ (WAV o MP3 de ElevenLabs) a final/ (WAV 48 kHz listo para Unreal) y QC.
// Adaptado de <AUDIO_LIBRARY>/scripts\normalizar.mjs y qc.mjs (ffmpeg, loudnorm de dos pasadas, pico real).
// Gratis y local: no usa la API ni la clave. Idempotente: no rehace lo que ya está (usa --force para rehacer).
//
// Uso:
//   node .claude/skills/elevenlabs-sfx-batch/postprocess.mjs <manifest.csv|carpeta audio-work> [--only Id,Id] [--force] [--dry] [--rules reglas.json]
//
// Pasos por toma: decodifica a WAV 48 kHz (mono o estéreo según la categoría) -> quita silencios de inicio y cola
// (los bucles no) -> bucles: crossfade de potencia constante entre el final y el inicio -> nivela por categoría
// (loudnorm de dos pasadas con pico real máximo -1 dBTP, o pico de muestra en efectos cortos) -> QC.
// Salida: final/<Categoria>/<id>_<NN>.wav, final/import-list.json (lo lee import_audio.py) y final/qc.json.
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const MAX_TP = -1.0; // pico real máximo en dBTP
// Valores de partida (criterio propio del autor, ajustar de oído con Audio Insights).
// modo 'peak': pico de muestra a "peak" dBFS (efectos cortos; la ganancia fina se pone en el motor).
// modo 'lufs': loudnorm de dos pasadas a "lufs" (largos); si dura menos de 1 s cae a pico.
const DEFAULT_RULES = {
  default: {modo: 'peak', peak: -3, canales: 1},
  ui: {modo: 'peak', peak: -6, canales: 1},
  amb: {modo: 'lufs', lufs: -28, canales: 2},
  mus: {modo: 'lufs', lufs: -22, canales: 2},
  vo: {modo: 'lufs', lufs: -20, canales: 1},
};
const CAT_ALIAS = {ambient: 'amb', ambiente: 'amb', ambientes: 'amb', music: 'mus', musica: 'mus', voz: 'vo', voice: 'vo', locutor: 'vo', interfaz: 'ui'};

const args = process.argv.slice(2);
const flags = {};
const pos = [];
for (let i = 0; i < args.length; i++) {
  if (args[i].startsWith('--')) flags[args[i].slice(2)] = ['force', 'dry'].includes(args[i].slice(2)) ? true : args[++i];
  else pos.push(args[i]);
}
if (!pos[0]) {
  console.error('Uso: node postprocess.mjs <manifest.csv|carpeta audio-work> [--only a,b] [--force] [--dry] [--rules reglas.json]');
  process.exit(1);
}
const given = path.resolve(pos[0]);
const workDir = flags.work ? path.resolve(flags.work) : given.endsWith('.csv') ? path.join(path.dirname(given), 'audio-work') : given;
const finalDir = path.join(workDir, 'final');
const catalogPath = path.join(workDir, 'catalog.json');
const only = flags.only ? new Set(flags.only.split(',').map((s) => s.trim())) : null;
if (!fs.existsSync(catalogPath)) {
  console.error(`No hay ${catalogPath}: primero corre generate.mjs.`);
  process.exit(1);
}
const rules = {...DEFAULT_RULES, ...(flags.rules ? JSON.parse(fs.readFileSync(flags.rules, 'utf8')) : {})};
const ruleOf = (cat) => {
  const k = cat.toLowerCase();
  return {...rules.default, ...(rules[CAT_ALIAS[k] ?? k] ?? {})};
};

// ---------- ffmpeg ----------
const run = (cmd, a) => spawnSync(cmd, a, {encoding: 'utf8', maxBuffer: 256 * 1024 * 1024});
function ff(a) {
  const r = run('ffmpeg', ['-v', 'error', '-y', ...a]);
  if (r.status !== 0) throw new Error(`ffmpeg fallo: ${(r.stderr || '').slice(0, 300)}`);
}
function probe(file) {
  const r = run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration:stream=sample_rate,channels', '-of', 'json', file]);
  const j = JSON.parse(r.stdout || '{}');
  return {dur: j.format?.duration ? +(+j.format.duration).toFixed(3) : 0, hz: +(j.streams?.[0]?.sample_rate ?? 0), ch: j.streams?.[0]?.channels ?? 0};
}
// LUFS integrado, pico real, silencios, clipping (como measure() de la biblioteca).
function measure(file, silenceSec) {
  const ebu = run('ffmpeg', ['-hide_banner', '-nostats', '-i', file, '-af', 'ebur128=peak=true', '-f', 'null', '-']).stderr;
  const summary = ebu.slice(ebu.lastIndexOf('Summary:'));
  const lufs = summary.match(/I:\s+(-?[\d.]+|-inf)\s+LUFS/)?.[1];
  const tp = summary.match(/Peak:\s+(-?[\d.]+|-inf)\s+dBFS/)?.[1];
  const sil = run('ffmpeg', ['-hide_banner', '-nostats', '-i', file, '-af', `silencedetect=noise=-50dB:d=${silenceSec}`, '-f', 'null', '-']).stderr;
  const starts = [...sil.matchAll(/silence_start: (-?[\d.]+)/g)].map((m) => +m[1]);
  const ends = [...sil.matchAll(/silence_end: ([\d.]+) \| silence_duration: ([\d.]+)/g)].map((m) => ({dur: +m[2]}));
  const st = run('ffmpeg', ['-hide_banner', '-nostats', '-i', file, '-af', 'astats=metadata=0:reset=0', '-f', 'null', '-']).stderr;
  const overall = st.slice(st.lastIndexOf('Overall'));
  const num = (re) => {
    const v = overall.match(re)?.[1];
    return v === undefined ? null : v === '-inf' ? -99 : +v;
  };
  const n = (v) => (v === undefined ? null : v === '-inf' ? -99 : +v);
  return {
    lufs: n(lufs), tp: n(tp), sampleDb: num(/Peak level dB:\s+(-?[\d.]+|-inf)/), peakCount: num(/Peak count:\s+([\d.]+)/), flat: num(/Flat factor:\s+([\d.]+)/),
    silences: starts.map((s, i) => ({start: +Math.max(0, s).toFixed(2), dur: ends[i]?.dur ?? null})),
  };
}
// Salto entre la última y la primera muestra frente al cambio típico entre muestras vecinas (costura del bucle).
function seamRatio(file) {
  const r = spawnSync('ffmpeg', ['-v', 'error', '-i', file, '-ac', '1', '-f', 's16le', '-'], {maxBuffer: 256 * 1024 * 1024});
  const b = r.stdout;
  const n = Math.floor(b.length / 2);
  if (n < 100) return null;
  let sum = 0;
  for (let i = 0; i < n - 1; i++) sum += Math.abs(b.readInt16LE((i + 1) * 2) - b.readInt16LE(i * 2));
  const typical = Math.max(sum / (n - 1), 1);
  return +(Math.abs(b.readInt16LE(0) - b.readInt16LE((n - 1) * 2)) / typical).toFixed(1);
}

// ---------- una toma ----------
function processTake(e, rule, outFile) {
  const tmp = path.join(workDir, '_tmp');
  fs.mkdirSync(tmp, {recursive: true});
  const src = path.join(workDir, e.file);
  const dec = path.join(tmp, 'dec.wav');
  const shaped = path.join(tmp, 'shaped.wav');
  ff(['-i', src, '-ar', '48000', '-ac', String(rule.canales), '-af', 'highpass=f=20', '-c:a', 'pcm_f32le', dec]);
  let pre = '';
  if (e.loop) {
    // El final se funde con el inicio: el bucle dura X s menos y la costura queda dentro del audio.
    const D = probe(dec).dur;
    const X = Math.max(0.05, Math.min(1.0, +(D * 0.2).toFixed(3)));
    ff(['-i', dec, '-filter_complex', `[0:a]atrim=start=${X},asetpts=PTS-STARTPTS[a];[0:a]atrim=end=${X},asetpts=PTS-STARTPTS[b];[a][b]acrossfade=d=${X}:c1=qsin:c2=qsin[o]`, '-map', '[o]', '-c:a', 'pcm_f32le', shaped]);
  } else {
    const head = 'silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.005:detection=peak';
    const tail = 'silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.08:detection=peak';
    ff(['-i', dec, '-af', `${head},areverse,${tail},areverse`, '-c:a', 'pcm_f32le', shaped]);
    const d = probe(shaped).dur;
    if (d > 0.1) pre = `afade=t=in:d=0.003,afade=t=out:st=${(d - 0.03).toFixed(3)}:d=0.03,`;
  }
  const dur = probe(shaped).dur;
  const out = ['-ar', '48000', '-ac', String(rule.canales), '-c:a', 'pcm_s16le'];
  let how;
  if (rule.modo === 'lufs' && dur >= 1.0) {
    const first = run('ffmpeg', ['-hide_banner', '-i', shaped, '-af', `${pre}loudnorm=I=${rule.lufs}:TP=${MAX_TP}:LRA=11:print_format=json`, '-f', 'null', '-']).stderr;
    const m = JSON.parse(first.match(/\{[^{}]*"input_i"[^{}]*\}/)[0]);
    if (m.input_i === '-inf' || +m.input_i < -69) throw new Error('casi en silencio: no se puede nivelar');
    const f2 = `${pre}loudnorm=I=${rule.lufs}:TP=${MAX_TP}:LRA=11:measured_I=${m.input_i}:measured_TP=${m.input_tp}:measured_LRA=${m.input_lra}:measured_thresh=${m.input_thresh}:offset=${m.target_offset}:linear=true:print_format=json`;
    const second = run('ffmpeg', ['-hide_banner', '-y', '-i', shaped, '-af', f2, ...out, outFile]);
    if (second.status !== 0) throw new Error(`ffmpeg fallo: ${second.stderr.slice(-300)}`);
    const j2 = second.stderr.match(/\{[^{}]*"output_i"[^{}]*\}/);
    how = `lufs ${rule.lufs} (entrada ${m.input_i}${j2 && JSON.parse(j2[0]).normalization_type === 'dynamic' ? ', cayo a modo dinamico' : ''})`;
  } else {
    const target = rule.peak ?? -3;
    const vd = run('ffmpeg', ['-hide_banner', '-i', shaped, '-af', `${pre}volumedetect`, '-f', 'null', '-']).stderr.match(/max_volume: (-?[\d.]+|-inf)/)?.[1];
    if (!vd || vd === '-inf' || +vd < -60) throw new Error('casi en silencio: no se puede nivelar');
    ff(['-i', shaped, '-af', `${pre}volume=${(target - +vd).toFixed(2)}dB`, ...out, outFile]);
    how = `pico ${target} dBFS${rule.modo === 'lufs' ? ' (menos de 1 s)' : ''}`;
  }
  // Si el pico real pasa de -1 dBTP, se baja lo justo y se vuelve a medir (hasta 2 veces).
  for (let k = 0; k < 2; k++) {
    const tp = measure(outFile, 0.5).tp;
    if (tp === null || tp <= MAX_TP) break;
    const fixed = `${outFile}.fix.wav`;
    ff(['-i', outFile, '-af', `volume=${(MAX_TP - tp - 0.1).toFixed(2)}dB`, ...out, fixed]);
    fs.renameSync(fixed, outFile);
    how += `; bajado ${(tp - MAX_TP + 0.1).toFixed(1)} dB por pico real`;
  }
  return {how, loopSeconds: dur};
}

// ---------- QC ----------
function qc(e, rule, file, extra) {
  const long = rule.modo === 'lufs';
  const p = probe(file);
  const m = measure(file, long ? 1.0 : 0.5);
  const defects = [];
  const warns = [];
  if (!p.dur || p.dur < 0.05) defects.push('archivo vacio');
  if (p.hz !== 48000 || p.ch !== rule.canales) defects.push(`formato ${p.hz} Hz ${p.ch} canales (se esperaba 48000 y ${rule.canales})`);
  if (m.lufs !== null && m.lufs !== -99 && p.dur >= 0.45 && m.lufs < -45) defects.push(`casi en silencio (${m.lufs} LUFS)`);
  if (e.seconds && p.dur < e.seconds * 0.5) defects.push(`dura ${p.dur} s y se pidieron ${e.seconds} s`);
  if (m.tp !== null && m.tp > MAX_TP + 0.05) defects.push(`pico real ${m.tp} dBTP, pasa de ${MAX_TP}`);
  if (m.sampleDb !== null && m.sampleDb >= -0.1 && ((m.flat ?? 0) > 0.5 || (m.peakCount ?? 0) >= 6)) defects.push('clipping');
  let start = 0;
  let tail = 0;
  for (const s of m.silences) {
    const end = s.dur === null ? p.dur : s.start + s.dur;
    if (s.start <= 0.05) start = s.dur ?? p.dur;
    else if (end >= p.dur - 0.08) tail = s.dur ?? p.dur - s.start;
    else defects.push(`hueco de silencio de ${s.dur?.toFixed(1)} s en ${s.start} s`);
  }
  if (!e.loop && (start > 0.3 || tail > 0.3)) warns.push(`silencio sobrante (inicio ${start.toFixed(2)} s, cola ${tail.toFixed(2)} s)`);
  if (rule.modo === 'lufs' && p.dur >= 1 && m.lufs !== null && Math.abs(m.lufs - rule.lufs) > 2) warns.push(`LUFS ${m.lufs} lejos del objetivo ${rule.lufs} (el limite de pico pudo impedir la ganancia)`);
  let seam = null;
  if (e.loop) {
    seam = seamRatio(file);
    if (seam !== null && seam > 6) warns.push(`costura del bucle posiblemente audible (salto x${seam})`);
  }
  return {estado: defects.length ? 'danado' : warns.length ? 'revisar' : 'ok', defects, warns, dur: p.dur, lufs: m.lufs, tp: m.tp, seam, how: extra};
}

// ---------- lote ----------
const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
const takes = catalog.entries.filter((e) => e.status === 'ok' && (!only || only.has(e.id)) && fs.existsSync(path.join(workDir, e.file)));
const nn = (t) => String(t).padStart(2, '0');
const qcPath = path.join(finalDir, 'qc.json');
const prevQc = fs.existsSync(qcPath) ? JSON.parse(fs.readFileSync(qcPath, 'utf8')) : {};
const qcAll = {...prevQc};
const importList = [];
let made = 0;
let skipped = 0;
console.log(`${takes.length} tomas en el catalogo. Reglas: ${Object.keys(rules).map((k) => { const v = ruleOf(k); return `${k}=${v.modo === 'lufs' ? 'lufs ' + v.lufs : 'pico ' + v.peak}`; }).join(', ')}`);
if (flags.dry) process.exit(0);
for (const e of takes) {
  const rule = ruleOf(e.categoria);
  const rel = `${e.categoria}/${e.id}_${nn(e.take)}.wav`;
  const outFile = path.join(finalDir, rel);
  const srcM = fs.statSync(path.join(workDir, e.file)).mtimeMs;
  if (fs.existsSync(outFile) && !flags.force && fs.statSync(outFile).mtimeMs >= srcM && prevQc[rel]) {
    skipped++;
    continue;
  }
  fs.mkdirSync(path.dirname(outFile), {recursive: true});
  try {
    const r = processTake(e, rule, outFile);
    const q = qc(e, rule, outFile, r.how);
    q.sha1 = createHash('sha1').update(fs.readFileSync(outFile)).digest('hex');
    q.fecha = new Date().toISOString();
    qcAll[rel] = q;
    made++;
    console.log(`${q.estado.padEnd(7)} ${rel}  ${q.dur}s  ${q.lufs} LUFS  ${q.tp} dBTP  [${r.how}]${q.defects.length ? '  DEFECTOS: ' + q.defects.join('; ') : ''}${q.warns.length ? '  avisos: ' + q.warns.join('; ') : ''}`);
  } catch (err) {
    qcAll[rel] = {estado: 'danado', defects: [err.message.slice(0, 200)], warns: [], fecha: new Date().toISOString()};
    console.error(`danado  ${rel}: ${err.message.slice(0, 200)}`);
    fs.rmSync(outFile, {force: true});
  }
}
fs.rmSync(path.join(workDir, '_tmp'), {recursive: true, force: true});
fs.mkdirSync(finalDir, {recursive: true});
// La lista de importación cubre TODAS las tomas con archivo final, aunque esta corrida use --only.
for (const e of catalog.entries.filter((x) => x.status === 'ok')) {
  const rel = `${e.categoria}/${e.id}_${nn(e.take)}.wav`;
  if (!fs.existsSync(path.join(finalDir, rel)) || qcAll[rel]?.estado === 'danado') continue;
  importList.push({asset: `SW_${e.categoria}_${e.id}_${nn(e.take)}`, file: rel, categoria: e.categoria, id: e.id, take: e.take, loop: !!e.loop, canales: ruleOf(e.categoria).canales, seconds: e.seconds, prompt: e.prompt});
}
fs.writeFileSync(qcPath, JSON.stringify(qcAll, null, 2) + '\n');
fs.writeFileSync(path.join(finalDir, 'import-list.json'), JSON.stringify(importList, null, 2) + '\n');

// Resumen por categoría: los niveles de una categoría deben quedar parejos.
const stats = {};
for (const it of importList) {
  const q = qcAll[it.file];
  if (!q || q.lufs == null || q.lufs === -99) continue;
  (stats[it.categoria] ??= []).push(q.lufs);
}
for (const [c, v] of Object.entries(stats)) {
  v.sort((a, b) => a - b);
  console.log(`  ${c.padEnd(8)} ${v.length} archivos, LUFS de ${v[0]} a ${v[v.length - 1]} (mediana ${v[Math.floor(v.length / 2)]})`);
}
const count = {};
for (const e of catalog.entries.filter((x) => x.status === 'ok')) {
  const st = qcAll[`${e.categoria}/${e.id}_${nn(e.take)}.wav`]?.estado ?? 'sin procesar';
  count[st] = (count[st] ?? 0) + 1;
}
console.log(`Listo: ${made} procesadas, ${skipped} ya estaban. Estado:`, count);
if (count.danado) process.exitCode = 4;
