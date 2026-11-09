"""Python de editor (upy.py): construye un MetaSound de flujo de aire con la Builder API (verificado en UE 5.8.4, 9-nov-2026).
Entorno: KIT_MS_NAME (por defecto MS_Eng_Airflow), KIT_MS_FOLDER (por defecto /Game/Audio/Eng). El juego fija RPM, AirSpeed, Size,
Load, Heat con SetFloatParameter (ver SKILL.md). Claude no oye: lo juzga una persona.
Ruido -> pasabanda Biquad (el corte sigue a RPM) -> ganancia (AirSpeed) -> salida mono. Entradas RPM, AirSpeed, Size, Load, Heat
(los nombres del maestro; Size/Load/Heat no se usan en este spike de 3 nodos). Imprime cada paso para que los fallos se vean."""
import os, unreal
NAME = os.environ.get("KIT_MS_NAME", "MS_Eng_Airflow")
FOLDER = os.environ.get("KIT_MS_FOLDER", "/Game/Audio/Eng")
sub = unreal.get_engine_subsystem(unreal.MetaSoundBuilderSubsystem)
res = sub.create_source_builder(NAME + "_Builder", unreal.MetaSoundOutputAudioFormat.MONO, False)
print("create_source_builder ->", type(res), len(res) if isinstance(res, tuple) else "")
print([type(x).__name__ for x in res]); b, on_play, on_finished, audio_outs = res[0], res[1], res[2], res[3]
print("audio outs", audio_outs)
OK = unreal.MetaSoundBuilderResult.SUCCEEDED

def lit_f(v):
    return sub.create_float_meta_sound_literal(v)[0] if isinstance(sub.create_float_meta_sound_literal(v), tuple) else sub.create_float_meta_sound_literal(v)

def node(ns, name, variant):
    cn = unreal.MetasoundFrontendClassName(ns, name, variant)
    for mv in (1, 0, 2):  # Biquad Filter es versión mayor 2 en 5.8.4
        r = b.add_node_by_class_name(cn, mv)
        h, ok = (r if isinstance(r, tuple) else (r, None))
        if ok == OK:
            break
    print("node", name, variant, ok)
    return h

def inp(n, name):
    r = b.find_node_input_by_name(n, name)
    return r[0] if isinstance(r, tuple) else r

def out(n, name):
    r = b.find_node_output_by_name(n, name)
    return r[0] if isinstance(r, tuple) else r

g = {}
for name in ("RPM", "AirSpeed", "Size", "Load", "Heat"):
    r = b.add_graph_input_node(name, "Float", lit_f(0.5), False)
    g[name] = r[0] if isinstance(r, tuple) else r
    print("input", name)

noise = node("UE", "Noise", "Audio")
bq = node("UE", "Biquad Filter", "Audio")
mul = node("UE", "Multiply", "Audio by Float")
mulf = node("UE", "Multiply", "Float")   # no hay nodo Map Range en 5.8.4: corte = RPM * 2700 + 300
addf = node("UE", "Add", "Float")

def con(o, i, label):
    r = b.connect_nodes(o, i)
    print("connect", label, r)

con(out(noise, "Audio"), inp(bq, "In"), "noise->biquad")
# corte: RPM 0..1 -> 300..3000 Hz
def show_pins(n, label):
    ins = b.find_node_inputs(n); outs = b.find_node_outputs(n)
    ins = ins[0] if isinstance(ins, tuple) else ins; outs = outs[0] if isinstance(outs, tuple) else outs
    print("pins", label, [str(x) for x in ins][:4], [str(x) for x in outs][:3])
con(g["RPM"], inp(mulf, "PrimaryOperand"), "RPM->mul")
print("default mul", b.set_node_input_default(inp(mulf, "AdditionalOperands"), lit_f(2700.0)))
con(out(mulf, "Out"), inp(addf, "PrimaryOperand"), "mul->add")
print("default add", b.set_node_input_default(inp(addf, "AdditionalOperands"), lit_f(300.0)))
con(out(addf, "Out"), inp(bq, "Cutoff Frequency"), "add->cutoff")
print("bandpass", b.set_node_input_default(inp(bq, "Bandwidth"), lit_f(1.5)))
con(out(bq, "Out"), inp(mul, "PrimaryOperand"), "biquad->mul")
con(g["AirSpeed"], inp(mul, "AdditionalOperands"), "airspeed->gain")
# Nivel: el ruido está casi a escala completa; dejar el flujo de aire ~ -18 dB por debajo de los SFX normalizados (Claude no oye: lo juzga una persona).
trim = node("UE", "Multiply", "Audio by Float")
con(out(mul, "Out"), inp(trim, "PrimaryOperand"), "gain->trim")
print("trim", b.set_node_input_default(inp(trim, "AdditionalOperands"), lit_f(0.12)))
r = b.connect_nodes(out(trim, "Out"), audio_outs[0])
print("to output", r)
ed = unreal.get_editor_subsystem(unreal.MetaSoundEditorSubsystem)
r = ed.build_to_asset(b, "unreal-agent", NAME, FOLDER, None)
print("build_to_asset", r)
print("saved", unreal.EditorAssetLibrary.save_asset(FOLDER + "/" + NAME, only_if_is_dirty=False))
