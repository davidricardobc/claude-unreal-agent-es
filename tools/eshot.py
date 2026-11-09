"""Renders desde el visor del editor, sin PIE (corre dentro del editor con upy.py).
Uso: python upy.py eshot.py nombre x y z pitch yaw [AnchoxAlto]
Mueve la cámara del visor del nivel y ejecuta HighResShot; el archivo queda en Saved/Screenshots/WindowsEditor/<nombre>.png"""
import unreal, sys
name = sys.argv[1]
x, y, z, p, yw = map(float, sys.argv[2:7])
res = sys.argv[7] if len(sys.argv) > 7 else "1920x1080"
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
ues.set_level_viewport_camera_info(unreal.Vector(x, y, z), unreal.Rotator(roll=0, pitch=p, yaw=yw))
world = ues.get_editor_world()
unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).editor_set_game_view(True)
unreal.SystemLibrary.execute_console_command(world, "HighResShot %s filename=%s" % (res, name))
print("shot requested", name)
