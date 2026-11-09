"""Logger de telemetría en Python (para bots, scripts de editor o simulaciones). Mismo CSV que el C++.

Uso:
  from telemetry_logger import TelemetryLogger
  log = TelemetryLogger("Saved/Telemetry", build="0.1.0")
  log.event("spawn", player_id="p1"); log.event("death", player_id="p1", subject="storm", value=1)
  log.close()
Dentro de Unreal sin verificar: usar unreal.Paths.project_saved_dir() para la carpeta.
"""
import csv
import os
import time
import uuid

FIELDS = ["ts", "session", "build", "round", "player_id", "event", "subject", "value"]


class TelemetryLogger:
    def __init__(self, folder, build="dev", session=None, clock=time.monotonic):
        os.makedirs(folder, exist_ok=True)
        self.session = session or time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
        self.build, self.round, self._clock, self._t0 = build, 0, clock, clock()
        self.path = os.path.join(folder, "telemetry_%s.csv" % self.session)
        self._f = open(self.path, "w", encoding="utf-8", newline="")
        self._w = csv.writer(self._f, lineterminator="\n")
        self._w.writerow(FIELDS)

    def event(self, event, player_id="", subject="", value=0, round=None):
        if round is not None:
            self.round = round
        self._w.writerow(["%.3f" % (self._clock() - self._t0), self.session, self.build, self.round,
                          player_id, event, subject, value])
        self._f.flush()  # un cierre brusco no pierde la sesión

    def close(self):
        self._f.close()
