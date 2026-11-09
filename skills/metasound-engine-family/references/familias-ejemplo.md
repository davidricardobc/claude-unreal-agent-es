# Ejemplo ficticio: 9 familias de motores de aviones RC

Ejemplo de cómo llenar los parámetros por familia. Los nombres y números son inventados como punto de partida para afinar de oído; no son de ningún juego real. Copiar este archivo a la carpeta de documentos del proyecto y cambiar los valores.

## Tablas

Todos los valores son puntos de partida propios: afinar de oído.

| Familia | Suena | Depende de | Respuesta |
|---|---|---|---|
| Coreless (6 mm, 8520) | zumbido agudo y delgado, de mosquito | RPM; se ensucia con el calor | 0.4 s |
| Escobillas (130 a 540) | zumbido con el rasposo de los carbones; más grave entre más grande | RPM y calor | 0.4 s |
| Outrunner (2204 a 5065) | silbido limpio y redondo que sube al instante; los grandes, más graves | RPM | 0.1 s |
| Inrunner (2845, 3660) | chillido muy agudo, casi de turbina, que tarda en subir | RPM | arranca al 60 %, tarda en recuperar |
| EDF (50 a 120 mm) | soplido con silbido de aspas, suena a jet | RPM y velocidad del aire | 1 s |
| Nitro 2T (.15, .46) | ring-ding agudo y rasposo; petardea al cortar | RPM y vibración | se apaga en ralentí más de 4 s |
| Nitro 4T (.52) | pop-pop grave y lento, de moto vieja | RPM | vibración -8 % |
| Gasolina (20 cc, 50 cc boxer) | grave y profundo; el boxer suena a avioneta (el de 20 cc, motosierra grave) | RPM | vibración -20 % |
| Turbina (100 N) | chasquido al arrancar, silbido que crece y rugido | empuje y temperatura | arranque 3 s |

Receta de síntesis (propia): pulsos de bujía 2T = RPM/60 por segundo; 4T = RPM/120; hélice = RPM/60 x palas; motor eléctrico = RPM/60 x pares de polos. Capas: T tono, P pulsos, A aire, R aspereza por calor.

| Familia | Capas (peso) | `BaseHz` en reposo | `SpanSt` | `SizeSt` | `RpmLag` |
|---|---|---|---|---|---|
| Coreless | T 1, A 0.1, R 0.3 | 900 Hz | 24 | 3 | 0.05 s |
| Escobillas | T 0.8, A 0.1, R 0.6 | 180 Hz | 19 | 12 | 0.15 s |
| Outrunner | T 1, A 0.2 | 350 Hz | 24 | 12 | 0.05 s |
| Inrunner | T 1, A 0.3 | 1400 Hz | 20 | 3 | 0.8 s subiendo |
| EDF | T 0.5 (aspas), A 1 | 700 Hz | 17 | 12 | 1 s |
| Nitro 2T | P 1, T 0.2, R 0.5 | 25 pulsos/s | 38 | 6 | 0.2 s |
| Nitro 4T | P 1, T 0.1 | 15 pulsos/s | 28 | 4 | 0.3 s |
| Gasolina | P 1, A 0.2 | 20 pulsos/s | 28 | 6 | 0.4 s |
| Turbina | T 0.4 (silbido), A 1 | 1000 Hz | 31 | 0 | 3 s |

`SpanSt` es el salto en semitonos de reposo a RPM máxima; `SizeSt`, cuánto baja con `Size` = 1. En la turbina `RPM` es el empuje y `Heat` la temperatura. En gasolina, `Size` 0 es el de 20 cc y 1 el boxer.
