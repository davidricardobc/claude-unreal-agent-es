// Proceso auxiliar: intenta N reservas contra el mismo ledger y imprime cuántas logró.
import {createLedger} from '../lib.mjs';
const [dir, cap, est, tries] = process.argv.slice(2);
const L = createLedger(dir);
let ok = 0;
for (let i = 0; i < Number(tries); i++) {
  const r = L.reserve(Number(est), Number(cap), `w${process.pid}-${i}`);
  if (r.ok) { ok++; L.commit(r.token, {id: `w${process.pid}`, take: i, status: 'ok', credits_est: Number(est)}); } // como un pago real
}
process.stdout.write(String(ok));
