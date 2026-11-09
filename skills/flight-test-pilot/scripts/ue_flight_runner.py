"""Corre maniobras guionadas en PIE y guarda un CSV por maniobra. Se ejecuta DENTRO de Unreal (Python de editor).
Verificado en UE 5.8.4 (9-nov-2026): corrió de punta a punta en un proyecto C++ en blanco con
references/FlightTestPawn (4/4 maniobras, KIT_OK) y en TableFlyer (5/5). Las llamadas que antes llevaban la marca SV quedaron confirmadas.

KIT_OK solo sale cuando TODAS las maniobras corrieron y pasaron sus criterios. Todo lo demás imprime
KIT_FAIL <motivo> (pawn sin SetVirtualStick, setup imposible, criterios fallidos, tiempo agotado).
Si no llega ni KIT_OK ni KIT_FAIL (por ejemplo, el commandlet termina sin ticks), el wrapper lo cuenta como falla.

Se necesita el bucle de ticks del editor: usar run-python.ps1 -Mode ExecutePythonScript con un -TimeoutSec razonable
(con -run=pythonscript no hay ticks tras el script, sin verificar).
  powershell -File .claude/skills/ue-headless/scripts/run-python.ps1 -UERoot "<UE_ROOT>" -Project "<ProyectoDir>\\<Proyecto>.uproject" -Script ".claude/skills/flight-test-pilot/scripts/ue_flight_runner.py" -Mode ExecutePythonScript -TimeoutSec 900 -Force
Variables de entorno:
  KIT_FLIGHT_MANEUVERS  ruta del JSON/CSV de maniobras (obligatoria)
  KIT_FLIGHT_MAP        mapa de pruebas, por ejemplo /Game/Maps/FlightTestRange
  KIT_FLIGHT_PAWN_TAG   tag del pawn a probar (por defecto FlightTestPawn)
  KIT_FLIGHT_OUT        carpeta de salida (por defecto <Proyecto>/Saved/FlightTests)
  KIT_FLIGHT_MAX_S      tope de tiempo real en segundos (por defecto 900)
  KIT_FLIGHT_KEEP_EDITOR=1  no cerrar el editor al final (para correrlo en un editor abierto con upy.py; verificado 9-nov)
  Pawn: si ningún actor tiene el tag (o el tag es "*"), se usa el pawn del jugador 0 (el que crea el GameMode).

Contrato con el pawn (cualquier pawn con movimiento propio):
  SetVirtualStick(Throttle, Pitch, Roll, Yaw) como UFUNCTION(BlueprintCallable) -> set_virtual_stick en Python.
  SetInitialSpeed(CmPerSecond) -> set_initial_speed. Obligatoria si algún setup pide speed_mps > 0.
Después: python analyze_flight.py --maneuvers <json> --dir <salida> (también revisa que los CSV sean de esta corrida).
Alternativa en CI: prueba C++ de Automation (references/automation_test_template.md).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from maneuver_script import load_maneuvers, validate  # noqa: E402
from flight_session import CSV_HEADER, PawnError, Session, sample_row  # noqa: E402,F401


def get_world(unreal):
    """Mundo de juego (PIE). Subsistema vigente con respaldo a la clase deprecada."""
    sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    return sub.get_game_world()


def load_level(unreal, path):
    sub = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    return sub.load_level(path)


class UePawn:
    """Adaptador entre Session y un pawn de Unreal."""

    def __init__(self, unreal, actor):
        self.u, self.a = unreal, actor
        self.home = actor.get_actor_location()

    def reset(self, setup):
        if not hasattr(self.a, "set_virtual_stick"):
            raise PawnError("el pawn no expone SetVirtualStick (set_virtual_stick); marcar la función BlueprintCallable")
        speed = float(setup.get("speed_mps", 0.0))
        if speed > 0 and not hasattr(self.a, "set_initial_speed"):
            raise PawnError("el setup pide %.0f m/s y el pawn no expone SetInitialSpeed (set_initial_speed)" % speed)
        u = self.u
        loc = u.Vector(self.home.x, self.home.y, float(setup.get("altitude_m", self.home.z / 100.0)) * 100.0)
        rot = u.Rotator(0.0, 0.0, float(setup.get("heading_deg", 0.0)))  # Rotator(roll, pitch, yaw): orden de argumentos (verificado en 5.8.4)
        self.a.set_actor_location_and_rotation(loc, rot, False, True)  # sweep False, teleport True
        if hasattr(self.a, "set_initial_speed"):
            self.a.set_initial_speed(speed * 100.0)  # también pone a 0 si speed es 0

    def set_stick(self, throttle, pitch, roll, yaw):
        self.a.set_virtual_stick(throttle, pitch, roll, yaw)

    def sample(self):
        loc, rot, vel = self.a.get_actor_location(), self.a.get_actor_rotation(), self.a.get_velocity()
        return (loc.x, loc.y, loc.z), (rot.pitch, rot.roll, rot.yaw), (vel.x, vel.y, vel.z)


def main():
    try:
        import unreal
    except ImportError:
        print("KIT_FAIL este script corre dentro de Unreal")
        return 1
    mpath = os.environ.get("KIT_FLIGHT_MANEUVERS")
    if not mpath or not os.path.exists(mpath):
        print("KIT_FAIL falta KIT_FLIGHT_MANEUVERS")
        return 1
    maneuvers = load_maneuvers(mpath)
    for m in maneuvers:
        errs = validate(m)
        if errs:
            print("KIT_FAIL maniobra %s: %s" % (m.get("id"), "; ".join(errs)))
            return 1
    out_dir = os.environ.get("KIT_FLIGHT_OUT") or os.path.join(unreal.Paths.project_saved_dir(), "FlightTests")
    tag = os.environ.get("KIT_FLIGHT_PAWN_TAG", "FlightTestPawn")
    if os.environ.get("KIT_FLIGHT_MAP"):
        load_level(unreal, os.environ["KIT_FLIGHT_MAP"])

    session = Session(maneuvers, out_dir, max_wall_s=float(os.environ.get("KIT_FLIGHT_MAX_S", "900")))
    session.start()
    box = {"pawn": None, "handle": None, "closed": False}

    def close():
        if box["closed"]:
            return
        box["closed"] = True
        print("\n".join("KIT_INFO " + line for line in session.report))
        print(session.final_line())  # única salida de KIT_OK
        try:
            unreal.unregister_slate_post_tick_callback(box["handle"])
            unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_end_play()
            if os.environ.get("KIT_FLIGHT_KEEP_EDITOR") != "1":
                unreal.SystemLibrary.quit_editor()
        except Exception as e:  # el cierre no cambia el veredicto
            print("KIT_INFO cierre incompleto: %s" % e)

    def on_tick(delta):
        if box["closed"]:
            return
        if box["pawn"] is None:
            world = get_world(unreal)
            actors = unreal.GameplayStatics.get_all_actors_with_tag(world, tag) if (world and tag != "*") else []
            if not actors and world:
                # Pawn creado por el GameMode (sin tag): el del jugador 0.
                pp = unreal.GameplayStatics.get_player_pawn(world, 0)
                actors = [pp] if pp else []
            if not actors:
                if session.clock() - session.started > session.max_wall_s:
                    session.fail("no apareció ningún pawn con el tag %s" % tag)
                    close()
                return  # esperar a que PIE cree el pawn
            box["pawn"] = UePawn(unreal, actors[0])
        if session.tick(delta, box["pawn"]) != "running":
            close()

    box["handle"] = unreal.register_slate_post_tick_callback(on_tick)
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_request_begin_play()
    print("KIT_INFO PIE pedido; maniobras: %s (el resultado sale al final)" % ", ".join(m["id"] for m in maneuvers))
    return 0  # sin KIT_OK: el veredicto lo da close()


if __name__ == "__main__":
    sys.exit(main())
