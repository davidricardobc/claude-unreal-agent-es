# Errores

- Ronda 1 · `Script must define a callable run() function` en `execute_tool_script` · el sandbox del MCP llama a `run()` y espera un dict · `def run(): ... return {"r": ...}`.
- Ronda 1 · `LogAutomatedImport: Error: Invalid Destination Path (/Game/C:/Program Files/Git/Game/Audio)` · Git Bash reescribió `-dest=/Game/Audio` · correr el commandlet desde PowerShell o con `MSYS_NO_PATHCONV=1`.
- Ronda 4 · `Assertion failed: IsInAudioThread()` en AudioDevice.cpp, pantalla negra en el juego empaquetado · se leía `GetSoundClassCurrentProperties` desde el hilo de juego · quitar la lectura. Lección: probar siempre el exe con sonido.
- Ronda 7 · `Fatal error: [EditorServer.cpp] World Memory Leaks` al cargar un mapa recién duplicado · Python seguía reteniendo el World duplicado · duplicar y guardar en una llamada, `collect_garbage()` y cargar en otra.
- Ronda 8 · `Failed to add new node by class name 'UE.Biquad Filter.Audio' and major version '1': Class not found` · ese nodo de MetaSound es la versión mayor 2 en 5.8.4 · probar las versiones 1, 0, 2.
- Ronda 8 · `'MovieScene3DTransformSection' object has no attribute 'get_channels'` · la API cambió en 5.8 · `get_all_channels()`.
- Rondas 1 a 8 (5 veces) · `SyntaxError: (unicode error) 'unicodeescape'` · rutas de Windows dentro de un heredoc · escribir el script en un archivo; usar `/` o cadenas crudas.
