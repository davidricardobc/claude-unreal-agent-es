"""Pruebas de las partes puras de ue-headless. No necesitan Unreal ni red.
Correr: python -I tests/test_headless.py   (solo Windows, usa powershell)"""
import os, subprocess, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.join(HERE, "..", "scripts")

def ps(script, *args):
    r = subprocess.run(["powershell", "-NoProfile", "-File", os.path.join(SCR, script), *args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout

class RunTests(unittest.TestCase):
    def _report(self, name):
        import tempfile, shutil
        d = tempfile.mkdtemp()
        shutil.copy(os.path.join(HERE, name), os.path.join(d, "index.json"))
        self.addCleanup(shutil.rmtree, d, True)
        return d

    def test_skipped_no_es_falla(self):
        code, out = ps("run-tests.ps1", "-ParseOnly", self._report("index.allok.json"))
        self.assertEqual(code, 0, out)
        self.assertIn("falladas=0", out)
        self.assertIn("saltadas=1", out)

    def test_fail_real_da_1(self):
        code, out = ps("run-tests.ps1", "-ParseOnly", self._report("index.sample.json"))
        self.assertEqual(code, 1, out)
        self.assertIn("FALLA Project.C", out)
        self.assertNotIn("Project.B [", out)
        self.assertIn("valor mal", out)

    def test_log_exit_code(self):
        import tempfile
        d = tempfile.mkdtemp(); self.addCleanup(__import__("shutil").rmtree, d, True)
        for n, exp in ((0, 0), (3, 1)):
            lg = os.path.join(d, f"l{n}.log")
            open(lg, "w").write(f"LogX: hi\n**** TEST COMPLETE. EXIT CODE: {n} ****\n")
            code, out = ps("run-tests.ps1", "-ParseOnly", d, "-LogFile", lg)
            self.assertEqual(code, exp, out)

class RunPython(unittest.TestCase):
    def _log(self, text):
        import tempfile
        d = tempfile.mkdtemp(); self.addCleanup(__import__("shutil").rmtree, d, True)
        p = os.path.join(d, "py.log")
        open(p, "w").write(text)
        return p

    def test_codigos_de_salida(self):
        ok = self._log("LogPython: hola\nLogPython: KIT_OK\n")
        warn = self._log("LogPython: Error: algo\nLogPython: KIT_OK\n")
        fail = self._log("LogPython: Traceback (most recent call last)\n")
        self.assertEqual(ps("run-python.ps1", "-ParseLog", ok)[0], 0)
        code, out = ps("run-python.ps1", "-ParseLog", warn)
        self.assertEqual(code, 4, out)  # KIT_OK con errores ya no cuenta como verde
        self.assertIn("No es verde", out)
        self.assertEqual(ps("run-python.ps1", "-ParseLog", fail)[0], 1)


class Build(unittest.TestCase):
    def test_tope_de_hilos(self):
        code, out = ps("build.ps1", "-UERoot", "C:/UE", "-Project", "C:/P/G.uproject", "-PrintArgs")
        self.assertEqual(code, 0, out)
        self.assertIn("GEditor Win64 Development", out)
        self.assertIn("-MaxParallelActions=4", out)
        code, out = ps("build.ps1", "-UERoot", "C:/UE", "-Project", "C:/P/G.uproject", "-PrintArgs", "-Hilos", "0")
        self.assertNotIn("MaxParallelActions", out)

    def test_parse_errores(self):
        code, out = ps("build.ps1", "-ParseLog", os.path.join(HERE, "build.sample.log"))
        self.assertEqual(code, 1, out)
        self.assertEqual(out.count("Foo.cpp(123): C2065"), 1, out)  # deduplicado
        self.assertIn("Foo.h(9): C1083", out)
        self.assertIn("LNK2019", out)
        self.assertIn("UnrealHeaderTool", out)
        self.assertIn("BUILD FAIL", out)

if __name__ == "__main__":
    unittest.main()
