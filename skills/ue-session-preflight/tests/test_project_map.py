"""Prueba project-map.ps1 con un proyecto falso. Sin Unreal. Correr: python -I tests/test_project_map.py"""
import os, subprocess, unittest, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "project-map.ps1")

def run(*args):
    r = subprocess.run(["powershell", "-NoProfile", "-File", SCRIPT, *args], capture_output=True, text=True)
    return r.returncode, r.stdout

class ProjectMap(unittest.TestCase):
    def test_mapa(self):
        code, out = run("-ProjectDir", os.path.join(HERE, "fixture-proj"))
        self.assertEqual(code, 0, out)
        self.assertIn("EngineAssociation=5.8", out)
        self.assertIn("Game(Runtime)", out)
        self.assertIn("ModelContextProtocol", out)
        self.assertNotIn("Off", out.split("Plugins")[1].split("\n")[0])
        self.assertIn("Mapas    : 1  L_Test", out)
        self.assertIn("DataTabl : 1  DT_Items", out)
        self.assertIn("UCLASS AMyActor", out)
        self.assertIn("USTRUCT FRowA", out)
        self.assertIn("2 lineas de error", out)
        self.assertLessEqual(len(out.strip().splitlines()), 25)

    def test_sin_uproject(self):
        with tempfile.TemporaryDirectory() as d:
            code, out = run("-ProjectDir", d)
        self.assertEqual(code, 2)
        self.assertIn("SIN .uproject", out)

    def test_respeta_maxlines(self):
        code, out = run("-ProjectDir", os.path.join(HERE, "fixture-proj"), "-MaxLines", "3")
        self.assertEqual(len(out.strip().splitlines()), 3)

if __name__ == "__main__":
    unittest.main()
