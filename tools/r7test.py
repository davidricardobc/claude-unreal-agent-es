"""Pruebas de la ronda 7 en PIE sobre PracticeMap: loop del piloto, blancos, aros, cambio de avión en el hangar, capturas con HUD.
Uso: python r7test.py [pasos...]   pasos: loop target slalom tunnel gaps hangar views   (sin pasos = todos)
Capturas con HUD -> TableFlyer/Saved/Capturas/r7_<nombre>.png ; después se revisan las líneas de log 'TF: ...'."""
import time, sys
import pie
from pie import start, stop, setp, xform

pie.PIE = "/Game/Maps/UEDPIE_0_PracticeMap.PracticeMap:PersistentLevel."
P = "TFPlanePawn_0"
steps = sys.argv[1:]
def on(n): return not steps or n in steps

def tp(loc, yaw=0.0, pitch=0.0):
    setp(P, {"DebugTeleport": dict(zip("XYZ", loc)), "DebugTeleportYaw": yaw, "DebugTeleportPitch": pitch})
    time.sleep(0.3)

def cap(name, wait=0.0):
    time.sleep(wait)
    setp(P, {"DebugScreenshotName": "r7_" + name})
    time.sleep(1.2)
    print("cap", name)

def pos():
    x = xform(P)
    try:
        l = x["location"] if "location" in x else x["transform"]["location"]
        return round(l["x"]), round(l["y"]), round(l["z"])
    except Exception:
        return str(x)[:120]

start(3.0); time.sleep(3)
print("start", pos())
cap("00_inicio_practica", 0.5)

if on("loop"):
    tp((-6000, 0, 6500), 0)
    setp(P, {"DebugPilot": 1, "bDebugLogPilot": True}); time.sleep(0.6)
    cap("01_piloto_antes")
    setp(P, {"DebugPilotPitchRate": 140.0})
    time.sleep(1.25); cap("02_piloto_arriba_del_loop")
    time.sleep(1.2)
    setp(P, {"DebugPilotPitchRate": 0.0}); time.sleep(1.5)
    cap("03_piloto_salida")
    setp(P, {"bDebugLogPilot": False, "DebugPilot": 2}); time.sleep(0.8)
    print("after loop", pos())

if on("target"):
    tp((12500, 500, 1250), 0)
    setp(P, {"bDebugFire": True}); time.sleep(0.9)
    setp(P, {"bDebugFire": False}); time.sleep(0.1)
    cap("04_blanco_derribado")
    time.sleep(3.0); cap("05_blanco_de_pie")
    tp((0, -15000, -4000), -90, -5)
    setp(P, {"bDebugFire": True}); time.sleep(1.5); setp(P, {"bDebugFire": False})
    cap("06_campo_de_tiro", 0.2)

if on("slalom"):
    tp((-15500, 1580, -4700), 0); time.sleep(0.2)
    cap("07_slalom", 0.6)
    time.sleep(2.5)

if on("tunnel"):
    tp((25500, -9500, -5900), 90); time.sleep(0.2)
    cap("08_tunel_entrada", 0.4)
    time.sleep(3.0)
    cap("09_tunel_dentro")
    time.sleep(3.0)

if on("gaps"):
    tp((-16500, -18500, -6100), 0); time.sleep(0.2)
    cap("10_hueco", 1.2)
    time.sleep(2.5)

if on("hangar"):
    setp(P, {"DebugPlaneType": 1}); time.sleep(0.3)
    # Por el puesto 3 (STUNT): el puesto i está en x = -15500 + 1100 * (i + 0.5), z = 380.
    tp((-15500 + 1100 * 5.5, 6800, 470), 90)
    time.sleep(2.6)
    cap("11_hangar_cambio")
    tp((-11100, 5200, 1000), 90, -8); setp(P, {"bDebugFreeze": True})
    cap("12_hangar_vista", 1.0)
    setp(P, {"bDebugFreeze": False})

stop()
print("done")
