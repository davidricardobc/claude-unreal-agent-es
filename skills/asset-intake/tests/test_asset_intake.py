import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import asset_rules as r  # noqa: E402
import license_registry as lr  # noqa: E402
import api_probe  # noqa: E402
import batch_import as bi  # noqa: E402

EXAMPLE = os.path.join(SCRIPTS, "licenses.example.csv")


def errs(rows, fields=None):
    fields = fields or list(rows[0].keys())
    return [m for lvl, n, m in lr.validate_rows(fields, rows) if lvl == "ERROR"]


def good_row(**kw):
    row = {"asset": "SM_A", "source": "Kenney", "license": "CC0", "allowed_use": "comercial",
           "declare": "yes"}
    row.update(kw)
    return row


class NamingTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(r.asset_name("static_mesh", "wood crate", 1), "SM_WoodCrate_01")
        self.assertEqual(r.asset_name("material_instance", "grass"), "MI_Grass")
        self.assertEqual(r.validate_name("SM_WoodCrate_01", "static_mesh"), [])
        self.assertTrue(r.validate_name("wood crate"))
        self.assertTrue(r.validate_name("M_Wall", "static_mesh"))

    def test_folder(self):
        self.assertEqual(r.target_folder("third_party", "props", "Synty/PolygonFarm"),
                         "/Game/ThirdParty/Synty/PolygonFarm/Props")

    def test_scale_guess(self):
        self.assertEqual(r.guess_scale((1.2, 0.5, 0.8))[0], 100.0)
        self.assertEqual(r.guess_scale((120, 50, 80))[0], 1.0)
        self.assertEqual(r.guess_scale((12000, 5000, 8000))[0], 0.1)
        self.assertAlmostEqual(r.guess_scale((1.0, 1.0, 2.0), 800)[0], 400.0)

    def test_pivot(self):
        self.assertEqual(r.pivot_offset((10, 10, 5), (30, 30, 25)), (-20.0, -20.0, -5))

    def test_plan_item(self):
        p = r.plan_item({"base": "wood crate", "index": 2, "origin": "ai", "pack": "Meshy",
                         "category": "Props", "target_max_cm": 100}, (0, 0, 0), (1, 1, 2))
        self.assertEqual(p["name"], "SM_WoodCrate_02")
        self.assertEqual(p["folder"], "/Game/AI_Generated/Meshy/Props")
        self.assertAlmostEqual(p["scale"], 50.0)


class LicenseTests(unittest.TestCase):
    def test_example_valid(self):
        fields, rows = lr.read_rows(EXAMPLE)
        self.assertEqual(errs(rows, fields), [])

    def test_missing_column(self):
        self.assertTrue(lr.validate_rows(["asset"], [{"asset": "x"}]))

    def test_bad_declare_and_duplicates(self):
        self.assertTrue(errs([good_row(declare="maybe")]))
        self.assertTrue(any("repetido" in e for e in errs([good_row(), good_row()])))

    def test_ai_rules(self):
        row = good_row(source="Meshy", license="CC BY 4.0", declare="no",
                       ai_generated="yes", reviewed="no", credit_text="")
        e = " | ".join(errs([row]))
        self.assertIn("declare debe ser yes", e)
        self.assertIn("sin revisar", e)
        self.assertIn("credit_text", e)

    def test_synty_not_to_ai(self):
        row = good_row(source="Synty Polygon", license="Synty", allowed_use="solo equipo",
                       uploaded_to_ai="yes")
        self.assertTrue(any("Synty" in e for e in errs([row])))

    def test_unknown_license(self):
        self.assertTrue(errs([good_row(license="unknown")]))

    def test_checklist(self):
        fields, rows = lr.read_rows(EXAMPLE)
        md = lr.checklist_markdown(rows)
        self.assertIn("SM_Statue_01", md)
        self.assertIn("Model created with Meshy", md)
        self.assertIn("## Kenney", md)

    def test_cc_by_non_ai_needs_credit(self):
        row = good_row(license="CC BY 4.0", credit_text="")
        self.assertTrue(any("atribucion" in e for e in errs([row])))
        self.assertEqual(errs([good_row(license="CC BY 4.0", credit_text="Autor X")]), [])
        self.assertEqual(errs([good_row(license="CC0")]), [])

    def test_hunyuan_blocked(self):
        row = good_row(source="Hunyuan3D-2", ai_generated="yes", reviewed="yes", license="otra")
        self.assertTrue(any("bloqueada" in e for e in errs([row])))

    def test_o_without_value(self):
        self.assertEqual(lr.main(["checklist", EXAMPLE, "-o"]), 2)

    def test_gitignore_check(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True)
            with open(os.path.join(d, ".gitignore"), "w") as f:
                f.write("Content/ThirdParty/Synty/" + chr(10))
            self.assertEqual(lr.check_gitignored(d, ["Content/ThirdParty/Synty/x.fbx"]), [])
            self.assertEqual(lr.check_gitignored(d, ["Content/Art"]), ["Content/Art"])


class SecondaryTests(unittest.TestCase):
    def test_secondary_names(self):
        self.assertEqual(r.secondary_name("texture", "wood_diffuse"), "T_WoodDiffuse")
        self.assertEqual(r.secondary_name("texture", "Tex_Wood"), "T_Wood")
        self.assertEqual(r.secondary_name("material", "Mat_Stone"), "M_Stone")
        self.assertEqual(r.secondary_name("material_instance", "stone dark"), "MI_StoneDark")
        with self.assertRaises(ValueError):
            r.secondary_name("static_mesh", "x")

    def test_final_size(self):
        self.assertIsNone(r.check_final_size((100, 50, 120), 120))
        self.assertIsNone(r.check_final_size((100, 50, 120), None))
        self.assertIn("distinta", r.check_final_size((100, 50, 80), 120))

    def test_api_probe_format(self):
        self.assertTrue(len(api_probe.read_entries()) >= 10)


class FakeUnreal:
    """Módulo unreal falso: lo justo para rename_secondaries y save_packages."""
    class Material: pass
    class MaterialInstanceConstant(Material): pass
    class Texture: pass
    class StaticMesh: pass

    def __init__(self, assets, fail_save=()):
        outer = self
        self.saved, self.renamed = [], []

        class EAL:
            @staticmethod
            def load_asset(p):
                return assets[p.split(".")[0]]

            @staticmethod
            def rename_asset(old, new):
                outer.renamed.append((old, new))
                return True

            @staticmethod
            def save_asset(pkg, only_if_is_dirty=True):
                outer.saved.append((pkg, only_if_is_dirty))
                return pkg not in fail_save
        self.EditorAssetLibrary = EAL


class SaveSecondaries(unittest.TestCase):
    """Los materiales y texturas renombrados se perdían: los secundarios también se guardan."""
    def setUp(self):
        F = FakeUnreal
        self.assets = {"/Game/P/SM_Rock": F.StaticMesh(), "/Game/P/Rock_Mat": F.Material(),
                       "/Game/P/Rock_D": F.Texture()}
        self.paths = ["/Game/P/SM_Rock.SM_Rock", "/Game/P/Rock_Mat.Rock_Mat", "/Game/P/Rock_D.Rock_D"]

    def test_renombra_y_devuelve_rutas_finales(self):
        u = FakeUnreal(self.assets)
        notes, finals = bi.rename_secondaries(u, self.paths, self.paths[0], "/Game/P")
        self.assertEqual(notes, [])
        self.assertEqual(len(finals), 2)
        self.assertEqual([n for _, n in u.renamed], finals)
        self.assertTrue(all(f.rsplit("/", 1)[-1].split("_")[0] in ("M", "T") for f in finals), finals)

    def test_guarda_secundarios_y_malla_al_final(self):
        u = FakeUnreal(self.assets)
        _, finals = bi.rename_secondaries(u, self.paths, self.paths[0], "/Game/P")
        saved, notes = bi.save_packages(u, finals + ["/Game/P/SM_Rock"])
        self.assertEqual((saved, notes), (3, []))
        self.assertEqual([p for p, _ in u.saved][-1], "/Game/P/SM_Rock")
        self.assertTrue(all(flag is False for _, flag in u.saved))  # guarda aunque no lo vea sucio

    def test_falla_de_guardado_se_reporta(self):
        u = FakeUnreal(self.assets, fail_save={"/Game/P/T_Rock_D"})
        saved, notes = bi.save_packages(u, ["/Game/P/T_Rock_D", "/Game/P/SM_Rock"])
        self.assertEqual(saved, 1)
        self.assertIn("no se pudo guardar /Game/P/T_Rock_D", notes)

    def test_enum_de_colision_vigente(self):
        src = open(os.path.join(SCRIPTS, "batch_import.py"), encoding="utf-8").read()
        self.assertNotIn("ScriptingCollisionShapeType", src)
        self.assertIn("ScriptCollisionShapeType.BOX", src)


if __name__ == "__main__":
    unittest.main()
