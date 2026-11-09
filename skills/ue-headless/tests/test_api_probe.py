"""Pruebas de la sonda compartida (api_probe.py). Puras: sin Unreal, con un módulo falso.
Correr: python -I .claude/skills/ue-headless/tests/test_api_probe.py"""
import os, sys, types, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import api_probe as ap  # noqa: E402


class FakePCG:
    """Imita la clase de UE: UFUNCTION = método, UPROPERTY = descriptor no callable."""
    is_component_partitioned = property(lambda self: False)

    def generate_local(self, force):
        return None

    @staticmethod
    def get_default_object():
        class CDO:
            def get_editor_property(self, name):
                if name == "seed":
                    return 42
                raise Exception("no existe " + name)
        return CDO()


FAKE = types.SimpleNamespace(PCGComponent=FakePCG, register_slate_post_tick_callback=lambda f: 0)


class Parse(unittest.TestCase):
    def test_formas_validas(self):
        self.assertIsNone(ap.parse_line("# comentario"))
        self.assertEqual(ap.parse_line("Vector"), (None, None, "Vector", None))
        self.assertEqual(ap.parse_line("A.b"), ("A", "b", "A.b", None))
        self.assertEqual(ap.parse_line("A.b prop  # nota"), ("A", "b", "A.b", "prop"))

    def test_formas_invalidas(self):
        for bad in ("A.b.c", "A.b metodo", "A func", "A.b func extra", ".b"):
            with self.assertRaises(ValueError, msg=bad):
                ap.parse_line(bad)

    def test_todos_los_api_txt_del_kit_parsean(self):
        files = ap.find_api_files()
        self.assertGreaterEqual(len(files), 5)
        for f in files:
            self.assertTrue(ap.read_entries(f), f)


class Check(unittest.TestCase):
    def test_func_y_prop_bien(self):
        self.assertEqual(ap.check(FAKE, ap.parse_line("PCGComponent.generate_local func"))[0], "OK")
        self.assertEqual(ap.check(FAKE, ap.parse_line("PCGComponent.is_component_partitioned prop"))[0], "OK")

    def test_caza_el_bug_de_build_tile(self):
        # El código viejo la trataba como función: la sonda debe decir TIPO, no OK.
        state, detail = ap.check(FAKE, ap.parse_line("PCGComponent.is_component_partitioned func"))
        self.assertEqual(state, "TIPO")
        self.assertIn("get/set_editor_property", detail)

    def test_prop_solo_por_editor_property(self):
        self.assertEqual(ap.check(FAKE, ap.parse_line("PCGComponent.seed prop"))[0], "OK")

    def test_faltantes(self):
        self.assertEqual(ap.check(FAKE, ap.parse_line("PCGComponent.nope"))[0], "FALTA")
        self.assertEqual(ap.check(FAKE, ap.parse_line("NoClase.x"))[0], "FALTA")
        self.assertEqual(ap.check(FAKE, ap.parse_line("register_slate_post_tick_callback"))[0], "OK")
        self.assertEqual(ap.check(FAKE, ap.parse_line("otra_funcion"))[0], "FALTA")

    def test_fuera_de_ue_salta(self):
        self.assertTrue(ap.main(["x"]))


if __name__ == "__main__":
    unittest.main()
