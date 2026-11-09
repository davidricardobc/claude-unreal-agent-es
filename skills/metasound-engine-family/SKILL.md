---
name: metasound-engine-family
description: Arma en Unreal Engine 5.8 un MetaSound maestro sintetizado para cualquier familia de motores o vehículos (eléctricos, de combustión, turbinas, coches, drones), con entradas RPM, Size, Load, Heat, AirSpeed, Vibration y DopplerPitch y un preset por familia. Incluye el tono en semitonos (BaseHz por 2^(st/12)), el Doppler calculado en C++ o Blueprint (el Delay de MetaSound falla en 5.7 y 5.8, UE-393204), la concurrencia, la atenuación, stat audio y la prueba de rendimiento con 16 instancias. Úsala para "sonido de motor", "engine sound", RPM en audio, Doppler, MetaSound de motor o vehículo, "audio concurrency", "stat audio" o rendimiento de audio con muchos motores.
---

# MetaSound maestro de motores: 1 grafo, N presets

Genérica: sirve en cualquier proyecto. Los valores por familia viven en un archivo del proyecto; ejemplo ficticio en `references/familias-ejemplo.md`. Cálculos puros (tono, Doppler, pulsos) en `scripts/engine_math.py`, con pruebas en `tests/`.

## Reglas previas

- El motor continuo se SINTETIZA (osciladores, pulsos, ruido, filtros). Un bucle generado por IA deriva de tono y no mantiene RPM constante. Arranques, cortes y texturas sí pueden venir de muestras.
- Respetar las reglas del proyecto sobre audio generado o previo (concursos, clientes).
- Claude no oye. Las pruebas son mediciones y la persona decide de oído. No prometer "suena bien".

## Entradas del maestro (`MS_Eng_Master`)

Nombres exactos: el código los usa con `SetFloatParameter` y `SetTriggerParameter`.

| Entrada | Tipo y rango | Para qué |
|---|---|---|
| `RPM` | float 0 a 1 | RPM normalizada que sale del modelo de movimiento |
| `Size` | float 0 a 1 | Tamaño dentro de la familia: más grande, más grave |
| `Load` | float 0 a 1 | Carga o acelerador; dispara petardeos o aspereza al cortar |
| `Heat` | float 0 a 1 | Calor o desgaste: ensucia el tono |
| `AirSpeed` | float 0 a 1 | Velocidad del aire sobre el motor (ventiladores, turbinas) |
| `Vibration` | float 0 a 1 | Jitter de amplitud y tono (combustión) |
| `DopplerPitch` | float 0.8 a 1.2, por defecto 1 | Multiplicador de tono calculado fuera |
| `Start`, `Stop` | Trigger | Arranque y corte |

Constantes por familia (van en el preset): `BaseHz`, `SpanSt`, `SizeSt`, pesos de capa (T tono, P pulsos, A aire, R aspereza) y `RpmLag`. Fórmulas de partida: pulsos de bujía 2T = RPM/60 por segundo; 4T = RPM/120; hélice = RPM/60 x palas; motor eléctrico = RPM/60 x pares de polos (`pulse_rate`).

## Armar el grafo a mano

1. Crear `MS_Eng_Master` (MetaSound Source, mono) en `/Game/Audio/Eng/` con las entradas.
2. Suavizar `RPM` con `InterpTo` (tiempo = `RpmLag`) para evitar clics.
3. Tono. No usar `Semitone to Frequency Multiplier`: no está en la referencia de nodos de 5.8.
   - `semitonos = SpanSt * RPM - SizeSt * Size`
   - `Hz = BaseHz * 2^(semitonos/12) * DopplerPitch`
   - Con nodos: `Multiply` (semitonos por 1/12), `Power` (base 2), `Multiply` por `BaseHz` y por `DopplerPitch`. O `MIDI To Frequency` con nota base + semitonos.
   - Alternativa simple: calcular `2^(st/12)` en C++ o Blueprint (`semitone_ratio`) y pasarlo como parámetro `PitchMul`.
   - Si un nombre no aparece en la paleta del editor, usar la fórmula.
   - Ese Hz alimenta un oscilador (`Saw`, `Triangle`) y un tren de pulsos (`Trigger Repeat` con periodo 1/Hz, `AD Envelope`, filtro).
4. Aire: `Noise` por `Biquad Filter` pasabanda; corte y volumen siguen `AirSpeed` x `RPM`. Aspereza: ruido filtrado más `WaveShaper`, por `Heat` x peso R.
5. Distancia: la interfaz `UE.Attenuation` da la distancia al oyente; mapearla a un pasabajos.
6. `Start` y `Stop`: `Wave Player` con muestras cortas.
7. Mezclar con pesos de capa, `Limiter`, salida mono. Nodos confirmados en la referencia de 5.8: InterpTo, Trigger Repeat, Wave Player, Noise, Saw, Triangle, Biquad Filter, WaveShaper, AD Envelope, Limiter, Power, Multiply, MIDI To Frequency.
8. Un preset por familia (clic derecho, Create MetaSound Source Preset). Probar cada uno: el foro reporta problemas de presets en grafos grandes (sin verificar en 5.8). Grafo chico.
9. Banco: Blueprint que barre `RPM` de 0 a 1 en 10 s por preset. La persona elige de oído y se anotan los valores en el archivo de familias del proyecto.

## Builder API (spike de 1 hora)

- Meta: crear por código un MetaSound Source de 3 nodos y llamar Build To Asset. Es Beta. Hay Blueprint y C++; clases Python `MetaSoundBuilderSubsystem` y `MetaSoundSourceBuilder` sin ejemplo completo.
- A los 60 min sin un asset que abra y suene: cortar y seguir a mano.

## Doppler (no usar Delay)

- El Delay y el Simple Delay de MetaSound fallan en 5.7 y 5.8 (UE-393204). No usarlos.
- `pitch = (c + v_oyente_hacia_la_fuente) / (c - v_fuente_hacia_el_oyente)`, c = 343 m/s, sobre la línea de visión, limitado a 0.8 a 1.2, enviado como `DopplerPitch` (`doppler_pitch`).
- Con 1 uu = 1 cm, cm/s por 0.01. Sin verificar la escala del proyecto: medir un cubo.
- C++ (sin compilar), en un `UActorComponent` con tick; inicializar `PrevSrc` y `PrevLis` en `BeginPlay`:
  ```cpp
  const FVector Src = GetOwner()->GetActorLocation();
  const FVector Lis = UGameplayStatics::GetPlayerCameraManager(this, 0)->GetCameraLocation();
  const FVector N = (Lis - Src).GetSafeNormal();
  const float Vs = FVector::DotProduct((Src - PrevSrc) / Dt, N) * 0.01f;
  const float Vl = -FVector::DotProduct((Lis - PrevLis) / Dt, N) * 0.01f;
  PrevSrc = Src; PrevLis = Lis;
  const float Raw = (343.f + Vl) / FMath::Max(343.f - Vs, 1.f);
  Smoothed = FMath::FInterpTo(Smoothed, FMath::Clamp(Raw, 0.8f, 1.2f), Dt, 20.f);
  Audio->SetFloatParameter(TEXT("DopplerPitch"), Smoothed);
  ```
- Blueprint: mismas cuentas en el Tick y `Set Float Parameter` en el Audio Component, donde también van `RPM`, `Size`, `Heat`, `AirSpeed`, `Load` y `Vibration`.

## Concurrencia y atenuación

- `SCON_Eng`: Max Count 8 a 10, regla `Stop Farthest Then Oldest` (`MaxConcurrentResolutionRule.STOP_FARTHEST_THEN_OLDEST`), asignado a cada preset.
- `SA_Eng`: atenuación 3D con pasabajos por distancia, a la escala de la escena.
- Los que quedan fuera del tope: preset barato o Virtualization Mode del asset.

## Rendimiento: prueba con 16 instancias

1. Nivel vacío `L_AudioBench` con 16 Audio Components, mezcla de familias, `RPM` animada con un seno.
2. Línea base con 1, 8 y 16 instancias, con y sin `SCON_Eng`. Consola: `stat audio`; Audio Insights.
3. Costo por MetaSound: en `UMetasoundGeneratorHandle`, `EnableRuntimeRenderTiming` (Python `enable_runtime_render_timing`) y luego `GetRuntimeCPUCoreUtilization`. Activar ANTES de Play o da 0.0.
4. El audio corre en CPU, pero en GPU de 6 GB el juego compite por el hilo de render. Repetir en la escena real.
5. Regla propia, sin verificar: si 16 instancias cuestan claramente más que 16 veces la línea base, o el hilo de audio pasa de 20 % de un núcleo, usar la versión barata.

## Pruebas y "sin verificar"

- Pruebas sin Unreal: `python -I -m unittest discover -s .claude/skills/metasound-engine-family/tests`.
- Sin verificar en 5.8 (1 a 2 minutos cada una): nombre Python del render timing (`dir(unreal.MetasoundGeneratorHandle)` en la consola Python del editor); entradas de la Builder API (`dir(unreal.MetaSoundBuilderSubsystem)`); estado de UE-393204 (buscar el ticket en el foro de Epic). Los números de familias son criterio propio. El C++ no se compiló.

## Verificado en TableFlyer (ronda 8, 9-nov-2026, UE 5.8.4)

- Spike de la Builder API logrado en ~25 min desde Python: `MS_Eng_Paper` (ruido -> Biquad Filter con corte = RPM*2700+300 -> ganancia por AirSpeed -> recorte) y el juego le manda `RPM`, `AirSpeed`, `Size`, `Load`, `Heat` con `SetFloatParameter`.
- Datos exactos de 5.8.4: `create_source_builder` devuelve 5 valores (builder, salida OnPlay, entrada OnFinished, lista de entradas de audio de salida, resultado); la salida de audio se conecta con `connect_nodes(salida_del_nodo, audio_outs[0])`; `Biquad Filter` es versión mayor **2** (con 1 da 'Class not found'); no existe `Map Range` (usar Multiply/Add Float); `build_to_asset` no guarda: llamar `EditorAssetLibrary.save_asset`.
- Script: `scripts/build_airflow_metasound.py` (con `upy.py`; nombre y carpeta por `KIT_MS_NAME` y `KIT_MS_FOLDER`). Nadie lo ha oído todavía: lo juzga la persona.
