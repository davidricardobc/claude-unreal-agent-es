"""Inspecciona los objetos del hangar en tiempo de ejecución dentro del mundo de PIE (correr con upy.py mientras PIE está activo)."""
import unreal
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
print("world", w.get_name() if w else None)
for d in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.TFPlaneDisplay):
    o, e = d.get_actor_bounds(False)
    print("display", d.get_name(), "hidden", d.is_hidden_ed(), d.get_editor_property("hidden"), "loc", d.get_actor_location(), "ext", e, "model", d.get_editor_property("model"))
for h in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.TFHangar):
    for c in h.get_components_by_class(unreal.TextRenderComponent):
        print("text", c.get_name(), c.get_world_location(), c.is_visible(), c.get_editor_property("text"))
