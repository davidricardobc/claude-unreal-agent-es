r"""Plantilla de smoke test para run-python.ps1. Solo lee, no guarda nada.

Uso: powershell -File run-python.ps1 -UERoot "<UE_ROOT>" -Project "<ProyectoDir>\<Proyecto>.uproject" -Script smoke_test.py
Convención: imprime KIT_OK al final si todo salió bien.
Nota: en modo commandlet (-run=pythonscript) los niveles no se cargan solos.
"""
import unreal

print("KIT_INFO motor:", unreal.SystemLibrary.get_engine_version())
print("KIT_INFO proyecto:", unreal.Paths.project_dir())

assets = unreal.EditorAssetLibrary.list_assets("/Game", recursive=True, include_folder=False)
print("KIT_INFO assets en /Game:", len(assets))

print("KIT_OK")
