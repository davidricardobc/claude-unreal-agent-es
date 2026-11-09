"""Pruebas puras (sin Unreal). Correr: python -m unittest discover -s .claude/skills/trailer-shot-prep/tests"""
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import shot_plan as sp  # noqa: E402
import verify_video as vv  # noqa: E402
import build_sequences as bs  # noqa: E402
import make_mrq_preset as mp  # noqa: E402

EXAMPLE = os.path.join(HERE, "..", "templates", "shots.example.csv")


def shot(i, name, dur, cam="static", mp_="/Game/Maps/A"):
    return {"index": i, "moment": name, "duration_s": dur, "camera_type": cam, "map": mp_, "target": "", "notes": "",
            "frames": int(dur * 60)}


class PlanTests(unittest.TestCase):
    def test_example_is_valid(self):
        shots = sp.load_shots(EXAMPLE)
        errs, warns = sp.validate(shots)
        self.assertEqual(errs, [])
        self.assertEqual(warns, [])
        self.assertAlmostEqual(sum(s["duration_s"] for s in shots), 41.5)

    def test_slug_and_names(self):
        self.assertEqual(sp.slug("  Opening Dive! "), "opening_dive")
        shots = sp.load_shots(EXAMPLE)
        self.assertEqual(shots[0]["seq_name"], "LS_01_cold_open_action")
        self.assertEqual(shots[0]["frames"], 150)

    def test_duration_limits(self):
        short = [shot(1, "a", 5), shot(2, "b", 5)]
        self.assertTrue(any("mínimo" in e for e in sp.validate(short)[0]))
        long_ = [shot(i, "s%d" % i, 10) for i in range(1, 8)]
        self.assertTrue(any("máximo" in e for e in sp.validate(long_)[0]))

    def test_hook_warning_and_bad_fields(self):
        shots = [shot(1, "a", 6), shot(2, "b", 30), shot(3, "a", 5, cam="zoom", mp_="Maps/A")]
        errs, warns = sp.validate(shots)
        self.assertTrue(any("repetido" in e for e in errs))
        self.assertTrue(any("camera_type" in e for e in errs))
        self.assertTrue(any("map" in e for e in errs))
        self.assertTrue(any("gancho" in w for w in warns))

    def test_orbit_keys_keep_radius_and_look_at_center(self):
        c = (100.0, 200.0, 50.0)
        keys = sp.camera_keys("orbit", c, 1500.0, 6.0)
        self.assertEqual(keys[0]["frame"], 0)
        self.assertEqual(keys[-1]["frame"], 360)
        for k in keys:
            d = math.hypot(k["loc"][0] - c[0], k["loc"][1] - c[1])
            self.assertAlmostEqual(d, 1500.0, places=3)
        # la cámara mira al centro: yaw apunta de loc a c
        k = keys[len(keys) // 2]
        yaw = math.degrees(math.atan2(c[1] - k["loc"][1], c[0] - k["loc"][0]))
        self.assertAlmostEqual(k["rot"][2], yaw, places=6)

    def test_dolly_gets_closer_and_crane_rises(self):
        c = (0.0, 0.0, 0.0)
        d = sp.camera_keys("dolly", c, 1000.0, 4.0)
        self.assertLess(abs(d[-1]["loc"][0]), abs(d[0]["loc"][0]))
        cr = sp.camera_keys("crane", c, 1000.0, 4.0)
        self.assertGreater(cr[-1]["loc"][2], cr[0]["loc"][2])
        self.assertEqual(len(sp.camera_keys("static", c, 1000.0, 4.0)), 1)
        with self.assertRaises(ValueError):
            sp.camera_keys("zoom", c, 1000.0, 4.0)

    def test_manifest_and_ffmpeg(self):
        shots = sp.load_shots(EXAMPLE)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.csv")
            self.assertEqual(sp.main(["manifest", EXAMPLE, out]), 0)
            with open(out, encoding="utf-8") as f:
                self.assertEqual(len(f.read().strip().splitlines()), len(shots) + 1)
        cmds = sp.ffmpeg_commands(shots, r"C:\out")
        self.assertIn("-framerate 60", cmds[0])
        self.assertIn("C:/out/LS_01_cold_open_action.%04d.png", cmds[0])


class ReviewFixTests(unittest.TestCase):
    def test_duration_range_is_configurable(self):
        long_ = [shot(i, "s%d" % i, 10) for i in range(1, 10)]  # 90 s
        self.assertTrue(any("máximo" in e for e in sp.validate(long_)[0]))
        self.assertEqual(sp.validate(long_, 30, 120)[0], [])

    def test_cli_min_max_flags(self):
        self.assertEqual(sp.main(["check", EXAMPLE, "--max-s", "40"]), 1)
        self.assertEqual(sp.main(["check", EXAMPLE, "--min-s", "20", "--max-s", "120"]), 0)

    def test_manifest_has_out_dir(self):
        import csv
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "m.csv")
            self.assertEqual(sp.main(["manifest", EXAMPLE, out, "--out-dir", "C:/render"]), 0)
            with open(out, encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["out_dir"], "C:/render")
            self.assertEqual(rows[0]["seq_name"], "LS_01_cold_open_action")

    def test_manifest_without_target_fails(self):
        self.assertEqual(sp.main(["manifest", EXAMPLE]), 1)

    def test_parse_cvars(self):
        self.assertEqual(mp.parse_cvars("a.b=1, c.d=0.5"), [("a.b", 1.0), ("c.d", 0.5)])
        self.assertEqual(mp.parse_cvars(""), [])
        with self.assertRaises(ValueError):
            mp.parse_cvars("sin_valor")

    def test_build_sequences_has_no_deprecated_calls(self):
        with open(os.path.join(HERE, "..", "scripts", "build_sequences.py"), encoding="utf-8") as f:
            lines = [l for l in f if "SV" not in l and not l.strip().startswith("#")]
        code = "".join(lines)
        self.assertNotIn("make_binding_id(", code)
        self.assertNotIn("EditorLevelLibrary", code)

    def test_ps1_counts_only_new_frames(self):
        with open(os.path.join(HERE, "..", "scripts", "render-shots.ps1"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("LastWriteTime -ge $t0", src)
        self.assertIn('".png", ".exr"', src)


class VideoTests(unittest.TestCase):
    @staticmethod
    def info(w=1920, h=1080, fps="60/1", dur="45.0", audio=True):
        st = [{"codec_type": "video", "width": w, "height": h, "avg_frame_rate": fps, "codec_name": "h264"}]
        if audio:
            st.append({"codec_type": "audio"})
        return {"streams": st, "format": {"duration": dur}}

    def test_ok(self):
        errs, warns, s = vv.evaluate(self.info())
        self.assertEqual((errs, warns), ([], []))
        self.assertEqual(s["fps"], 60.0)

    def test_failures(self):
        errs, _, _ = vv.evaluate(self.info(w=1280, h=720, dur="12"))
        self.assertEqual(len(errs), 2)
        errs, warns, _ = vv.evaluate(self.info(fps="30000/1001", audio=False))
        self.assertEqual(errs, [])
        self.assertEqual(len(warns), 2)
        self.assertTrue(vv.evaluate({"streams": [], "format": {}})[0])

    def test_real_ffprobe_if_available(self):
        if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
            self.skipTest("sin ffmpeg")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.mp4")
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=60:duration=31",
                            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast", p], check=True)
            self.assertEqual(vv.main([p]), 0)
            self.assertEqual(vv.main([p, "--min-s", "40"]), 1)


class PresetTests(unittest.TestCase):
    def test_parse_res(self):
        self.assertEqual(mp.parse_res("3840x2160"), (3840, 2160))
        with self.assertRaises(ValueError):
            mp.parse_res("1280x720")



class FakeBinding:
    def __init__(self, ok):
        self.ok = ok

    def is_valid(self):
        return self.ok


class FakeSeq:
    def __init__(self, ok):
        self.ok = ok

    def add_spawnable_from_class(self, cls):
        return FakeBinding(self.ok)


class FakeSub:
    def __init__(self, ok):
        self.ok, self.calls = ok, 0

    def add_spawnable_from_class(self, seq, cls):
        self.calls += 1
        return FakeBinding(self.ok)


class FakeUnreal:
    CineCameraActor = object
    LevelSequenceEditorSubsystem = object

    def __init__(self, sub):
        self.sub = sub

    def get_editor_subsystem(self, cls):
        return self.sub


class CameraSpawnable(unittest.TestCase):
    """Sin Sequencer abierto, el subsistema devuelve un proxy vacío."""
    def test_sin_sequencer_usa_la_secuencia(self):
        sub = FakeSub(False)
        b, how = bs.add_camera_spawnable(FakeUnreal(sub), FakeSeq(True))
        self.assertTrue(b.is_valid())
        self.assertIn("secuencia", how)
        self.assertEqual(sub.calls, 0)

    def test_proxy_vacio_cae_al_subsistema_y_si_falla_avisa(self):
        b, how = bs.add_camera_spawnable(FakeUnreal(FakeSub(True)), FakeSeq(False))
        self.assertIn("subsistema", how)
        with self.assertRaises(RuntimeError) as cm:
            bs.add_camera_spawnable(FakeUnreal(FakeSub(False)), FakeSeq(False))
        self.assertIn("Sequencer", str(cm.exception))

    def test_binding_ok(self):
        self.assertFalse(bs.binding_ok(None))
        self.assertFalse(bs.binding_ok(FakeBinding(False)))
        self.assertTrue(bs.binding_ok(FakeBinding(True)))

if __name__ == "__main__":
    unittest.main()
