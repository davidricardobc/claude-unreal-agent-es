"""Hornea el PCG de una loseta en el editor y suelta la salida como actores normales.

Entorno: KIT_TILE_MANIFEST (JSON con tile_id, level y pcg.mode=baked).
Busca el actor con la etiqueta `PCG_<tile_id>` en el nivel de la loseta, fija la semilla
desde el ID (no desde la posición), exige que el componente NO sea particionado, genera
en el editor, suelta el enlace PCG y guarda el nivel. Idempotente: limpia antes de generar.
Imprime KIT_OK solo si quedaron actores generados; si no, KIT_FAIL con el motivo.
Verificado contra PCGComponent.h de UE 5.8: generate_local, cleanup_local y clear_pcg_link
son UFUNCTION (se llaman); is_component_partitioned y seed son UPROPERTY (bIsComponentPartitioned,
Seed): se leen y escriben con get/set_editor_property, NUNCA con paréntesis. Ver api.txt.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import validate_tile_manifest as vtm  # noqa: E402


def run():
    import unreal

    with open(os.environ["KIT_TILE_MANIFEST"], encoding="utf-8") as f:
        m = json.load(f)
    if (m.get("pcg") or {}).get("mode") != "baked":
        print("KIT_FAIL el manifiesto no pide pcg.mode=baked")
        return False
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not les.load_level(m["level"]):
        print("KIT_FAIL no se pudo cargar " + m["level"])
        return False
    label = "PCG_" + m["tile_id"]
    holder = next((a for a in actors.get_all_level_actors() if a.get_actor_label() == label), None)
    if holder is None:
        print("KIT_FAIL no hay actor con etiqueta " + label)
        return False
    comp = holder.get_component_by_class(unreal.PCGComponent)
    if comp is None:
        print("KIT_FAIL el actor no tiene PCGComponent")
        return False
    # Propiedad, no función: llamarla con () da TypeError (bool no es callable).
    if comp.get_editor_property("is_component_partitioned"):
        print("KIT_FAIL el componente es particionado: usar uno no particionado")
        return False
    before = len(actors.get_all_level_actors())
    comp.set_editor_property("seed", vtm.tile_seed(m["tile_id"]))
    comp.cleanup_local(True)
    comp.generate_local(True)  # puede ser asíncrono: ver SKILL.md si no aparecen actores
    comp.clear_pcg_link()  # la salida queda como actores/ISM normales, sin runtime PCG
    after = len(actors.get_all_level_actors())
    print("actores antes=%d despues=%d semilla=%d" % (before, after, vtm.tile_seed(m["tile_id"])))
    if after <= before:
        print("KIT_FAIL no aparecieron actores generados (generacion asincrona o grafo vacio)")
        return False
    les.save_current_level()
    return True


if __name__ == "__main__":
    try:
        ok = run()
    except Exception as e:
        print("KIT_FAIL excepcion: %r" % (e,))
        ok = False
    if ok:
        print("KIT_OK")
    sys.exit(0 if ok else 1)
