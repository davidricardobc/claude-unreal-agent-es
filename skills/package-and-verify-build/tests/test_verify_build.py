"""Pruebas de verify-build.ps1 y butler-push.ps1 (sin Unreal, sin red, sin subida de butler)."""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.abspath(os.path.join(HERE, ".."))
PS = shutil.which("powershell")


def run_ps(script, *args, cwd=None):
    return subprocess.run([PS, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-File", os.path.join(SKILL, script), *args],
                          capture_output=True, text=True, cwd=cwd)


@unittest.skipUnless(PS and sys.platform == "win32", "needs Windows PowerShell")
class VerifyBuild(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="pvb_")
        self.addCleanup(shutil.rmtree, self.root, True)
        self.staged = os.path.join(self.root, "out", "Windows")
        os.makedirs(os.path.join(self.staged, "MiJuego", "Binaries", "Win64"))
        for rel, data in (("MiJuego.exe", b"launcher"),
                          ("MiJuego/Binaries/Win64/MiJuego.exe", b"game" * 100),
                          ("MiJuego/Binaries/Win64/MiJuego.pdb", b"symbols")):
            with open(os.path.join(self.staged, rel), "wb") as f:
                f.write(data)

    def test_zip_name_sha_and_registry_row(self):
        reg = os.path.join(self.root, "docs", "builds.md")
        r = run_ps("verify-build.ps1", "-Staged", self.staged, "-Exe", "MiJuego.exe",
                   "-Zip", "Equipo_MiJuego.zip", "-SinSmoke", "-Registro", reg,
                   "-Nota", "prueba", cwd=self.root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        zpath = os.path.join(self.root, "out", "Equipo_MiJuego.zip")
        self.assertTrue(os.path.isfile(zpath))
        names = zipfile.ZipFile(zpath).namelist()
        self.assertIn("MiJuego.exe", names)
        self.assertFalse(any(n.endswith(".pdb") for n in names))
        self.assertFalse(any("\\" in n for n in names))
        self.assertFalse(os.path.exists(os.path.join(
            self.staged, "MiJuego", "Binaries", "Win64", "MiJuego.pdb")))
        sha = hashlib.sha256(open(zpath, "rb").read()).hexdigest().upper()
        rows = open(reg, encoding="utf-8").read().splitlines()
        self.assertEqual(len(rows), 3)  # encabezado, separador, una fila
        self.assertIn(sha, rows[2])
        self.assertIn("OK <1 GB", rows[2])
        self.assertIn("prueba", rows[2])
        self.assertIn("omitido", rows[2])

    def test_second_run_appends_and_replaces_zip(self):
        reg = os.path.join(self.root, "docs", "builds.md")
        for _ in range(2):
            r = run_ps("verify-build.ps1", "-Staged", self.staged, "-Exe", "MiJuego.exe",
                       "-Zip", "Equipo_MiJuego.zip", "-SinSmoke", "-Registro", reg, cwd=self.root)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(open(reg, encoding="utf-8").read().splitlines()), 4)

    def test_bad_zip_name_rejected(self):
        for bad in ("juego.zip", "Equipo MiJuego.zip", "Equipo_Mi_Juego.zip", "Equipo_MiJuego.rar"):
            r = run_ps("verify-build.ps1", "-Staged", self.staged, "-Exe", "MiJuego.exe",
                       "-Zip", bad, "-SinSmoke", "-Registro", os.path.join(self.root, "b.md"),
                       cwd=self.root)
            self.assertNotEqual(r.returncode, 0, bad)

    def test_missing_staged_fails(self):
        r = run_ps("verify-build.ps1", "-Staged", os.path.join(self.root, "nope"),
                   "-Exe", "MiJuego.exe", "-Zip", "Equipo_MiJuego.zip", "-SinSmoke", cwd=self.root)
        self.assertNotEqual(r.returncode, 0)

    def test_placeholders_rejected(self):
        r = run_ps("verify-build.ps1", cwd=self.root)
        self.assertNotEqual(r.returncode, 0)

    def test_butler_push_validation_without_butler(self):
        # Un destino inválido (con mayúsculas) debe fallar antes de llamar a butler.
        r = run_ps("butler-push.ps1", "-Origen", self.staged, "-Destino", "Cuenta/juego:windows")
        self.assertNotEqual(r.returncode, 0)
        # Un push real sin -ConfirmadoPor debe fallar antes de llamar a butler.
        r = run_ps("butler-push.ps1", "-Origen", self.staged, "-Destino", "cuenta/juego:windows", "-Real")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("ConfirmadoPor", r.stdout + r.stderr)



@unittest.skipUnless(PS and sys.platform == "win32", "needs Windows PowerShell")
class PackageDryRun(unittest.TestCase):
    """Correcciones verificadas en la máquina real (8-nov-2026)."""
    def _dry(self, *extra):
        r = run_ps("package.ps1", "-UERoot", r"C:\UE", "-Proyecto", r"C:\P\G.uproject",
                   "-Salida", r"C:\P\out", "-DryRun", *extra)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_tope_de_hilos_por_defecto(self):
        out = self._dry()
        self.assertIn("-UbtArgs=-MaxParallelActions=4", out)
        self.assertIn("-iostore", out)

    def test_sin_tope_y_nunca_skip_editor_content(self):
        out = self._dry("-Hilos", "0")
        self.assertNotIn("MaxParallelActions", out)
        self.assertNotIn("SkipCookingEditorContent", out)
        self.assertNotIn("skipeditorcontent", out.lower())

    def test_editor_abierto_nocompileeditor(self):
        self.assertNotIn("-nocompileeditor", self._dry())
        self.assertIn("-nocompileeditor", self._dry("-NoCompileEditor"))

    def test_skill_no_recomienda_skip_editor_content(self):
        md = open(os.path.join(SKILL, "SKILL.md"), encoding="utf-8").read()
        # Neutral al idioma: se nombra la bandera y se documenta su fallo (ExitCode=25, NeverCook).
        self.assertIn("`-SkipCookingEditorContent`", md)
        self.assertIn("NeverCook", md)
        self.assertIn("NetFxSDK", md)
        self.assertIn("bIsEditorOnly=True", md)

if __name__ == "__main__":
    unittest.main()
