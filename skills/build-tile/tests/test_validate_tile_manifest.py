import copy
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import validate_tile_manifest as v  # noqa: E402
import rotation_smoke_test as rst  # noqa: E402
import api_probe  # noqa: E402

with open(os.path.join(HERE, "..", "scripts", "tile_manifest.example.json"), encoding="utf-8") as f:
    GOOD = json.load(f)


def errors(m):
    return [t for lvl, t in v.validate_manifest(m) if lvl == "ERROR"]


class Tests(unittest.TestCase):
    def test_example_is_valid(self):
        self.assertEqual(errors(GOOD), [])

    def test_missing_field(self):
        m = copy.deepcopy(GOOD)
        del m["edges"]
        self.assertTrue(errors(m))

    def test_not_grid_multiple(self):
        m = copy.deepcopy(GOOD)
        m["size_cm"] = [200001, 200000]
        self.assertTrue(any("multiplo" in e for e in errors(m)))

    def test_placement_outside(self):
        m = copy.deepcopy(GOOD)
        m["placements"][0]["location_cm"] = [999999, 0, 0]
        self.assertTrue(any("fuera" in e for e in errors(m)))

    def test_pcg_must_be_baked(self):
        m = copy.deepcopy(GOOD)
        m["pcg"]["mode"] = "runtime"
        self.assertTrue(any("baked" in e for e in errors(m)))

    def test_budget_exceeded(self):
        m = copy.deepcopy(GOOD)
        m["stats"]["triangles"] = 5000000
        self.assertTrue(any("triangles" in e for e in errors(m)))

    def test_rotation_maps_north_to_east(self):
        edges = {"N": {"profile": "a"}, "E": {"profile": "b"},
                 "S": {"profile": "c"}, "W": {"profile": "d"}}
        r = v.rotate_edges(edges, 1)
        self.assertEqual(r["E"]["profile"], "a")
        self.assertEqual(r["N"]["profile"], "d")
        self.assertEqual(v.rotate_edges(edges, 4), edges)

    def test_adjacent_mismatch(self):
        b = copy.deepcopy(GOOD)
        b["tile_id"] = "T02"
        b["edges"]["W"]["profile"] = "cliff"
        self.assertTrue(v.check_adjacent(GOOD, "E", b, "W"))
        self.assertFalse(v.check_adjacent(GOOD, "E", GOOD, "W"))

    # --- el caso que antes pasaba y debe fallar ---
    def test_alternating_edges_rotatable_fails(self):
        m = copy.deepcopy(GOOD)
        for s in ("N", "S"):
            m["edges"][s]["profile"] = "a"
        for s in ("E", "W"):
            m["edges"][s]["profile"] = "b"
        self.assertTrue(any("rotatable=true exige" in e for e in errors(m)))
        # la prueba de giro lo detecta en el giro 90 (antes solo miraba lados opuestos)
        self.assertTrue(rst.edge_fails_for_rotation(m, 1))

    def test_alternating_edges_not_rotatable_ok(self):
        m = copy.deepcopy(GOOD)
        m["rotatable"] = False
        m["edges"]["N"]["profile"] = "a"
        self.assertEqual(errors(m), [])

    def test_uniform_tile_passes_all_rotations(self):
        for q in range(4):
            self.assertEqual(rst.edge_fails_for_rotation(GOOD, q), [])

    def test_adjacent_all_rotations(self):
        a = copy.deepcopy(GOOD)
        b = copy.deepcopy(GOOD)
        b["tile_id"] = "T02"
        self.assertEqual(v.check_adjacent_rotations(a, "E", b, "W"), [])
        b["edges"]["N"]["profile"] = "cliff"  # B girada 90 pone "cliff" contra "flat_road"
        self.assertTrue(v.check_adjacent_rotations(a, "E", b, "W"))
        b["rotatable"] = False  # solo giro 0: E/W de B siguen iguales
        a["rotatable"] = False
        self.assertEqual(v.check_adjacent_rotations(a, "E", b, "W"), [])

    def test_non_square_rotatable_is_error(self):
        m = copy.deepcopy(GOOD)
        m["size_cm"] = [200000, 100000]
        self.assertTrue(any("no cuadrada" in e for e in errors(m)))
        m["rotatable"] = False
        self.assertFalse(any("no cuadrada" in e for e in errors(m)))

    def test_road_center_uses_x_for_north_south(self):
        m = copy.deepcopy(GOOD)
        m["rotatable"] = False
        m["size_cm"] = [200000, 100000]
        m["edges"]["N"]["road_center_cm"] = 100000  # size[0]/2: correcto
        m["edges"]["E"]["road_center_cm"] = 50000   # size[1]/2: correcto
        w = [t for lvl, t in v.validate_manifest(m) if "road_center" in t]
        self.assertEqual(w, [t for t in w if "borde S" in t or "borde W" in t])

    # --- la prueba de colisión gira de verdad los puntos ---
    def test_trace_points_rotate_with_yaw(self):
        m = copy.deepcopy(GOOD)
        p0 = {(s, round(x), round(y)) for s, x, y, z in rst.trace_points(m, 0)}
        p90 = {(s, round(x), round(y)) for s, x, y, z in rst.trace_points(m, 90)}
        self.assertNotEqual(p0, p90)
        x, y = rst.rotate_point(100, 0, 90)
        self.assertAlmostEqual(x, 0, places=6)
        self.assertAlmostEqual(y, 100, places=6)
        self.assertEqual(len(rst.trace_points(m, 180)), 20)

    def test_hit_z_accepts_tuple_and_none(self):
        # Modela el HitResult real de UE 5.8.4: los campos solo salen por to_tuple() ([0] choque bloqueante, luego un Vector).
        class Pt:
            x, y, z = 1.0, 2.0, 5.0

        class Hr:
            def __init__(self, hit):
                self.hit = hit

            def to_tuple(self):
                return (self.hit, False, 0, 0.5, 100.0, Pt(), Pt())
        self.assertEqual(rst.hit_z(Hr(True)), 5.0)
        self.assertEqual(rst.hit_z((True, Hr(True))), 5.0)
        self.assertIsNone(rst.hit_z(Hr(False)))
        self.assertIsNone(rst.hit_z((False, Hr(True))))
        self.assertIsNone(rst.hit_z(None))

    def test_seed_is_stable(self):
        self.assertEqual(v.tile_seed("T01"), v.tile_seed("T01"))
        self.assertNotEqual(v.tile_seed("T01"), v.tile_seed("T02"))
        self.assertLess(v.tile_seed("T01"), 2 ** 31)

    def test_api_probe_format(self):
        self.assertTrue(len(api_probe.read_entries()) >= 10)

    def test_api_txt_marca_partitioned_como_prop(self):
        kinds = {e[2]: e[3] for e in api_probe.read_entries()}
        self.assertEqual(kinds["PCGComponent.is_component_partitioned"], "prop")
        self.assertEqual(kinds["PCGComponent.generate_local"], "func")

    def test_bake_pcg_no_llama_la_propiedad(self):
        src = open(os.path.join(HERE, "..", "scripts", "bake_pcg.py"), encoding="utf-8").read()
        self.assertNotIn("is_component_partitioned()", src)
        self.assertIn('get_editor_property("is_component_partitioned")', src)

    def test_with_retries(self):
        calls = iter([None, None, 12.5])
        waits = []
        self.assertEqual(rst.with_retries(lambda: next(calls), 3, lambda: waits.append(1)), (12.5, 3))
        self.assertEqual(len(waits), 2)
        self.assertEqual(rst.with_retries(lambda: None, 2), (None, 2))
        self.assertEqual(rst.with_retries(lambda: 0.0, 5), (0.0, 1))  # 0 cm es impacto válido


if __name__ == "__main__":
    unittest.main()
