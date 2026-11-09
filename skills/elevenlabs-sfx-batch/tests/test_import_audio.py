"""Revisa import_audio.py sin Unreal (importa `unreal`, así que se lee como texto y se parsea).
Correr: python -I .claude/skills/elevenlabs-sfx-batch/tests/test_import_audio.py"""
import ast
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = open(os.path.join(HERE, "..", "import_audio.py"), encoding="utf-8").read()
MD = open(os.path.join(HERE, "..", "SKILL.md"), encoding="utf-8").read()


class ImportAudio(unittest.TestCase):
    def test_sintaxis(self):
        ast.parse(SRC)

    def test_imprime_kit_ok_para_run_python(self):
        self.assertIn('print("KIT_OK" if ok else "KIT_FAIL")', SRC)
        self.assertIn('if __name__ == "__main__":', SRC)
        self.assertIn('return not report["failed"]', SRC)

    def test_skill_no_promete_mcp(self):
        self.assertNotIn("consola de Python o por MCP", MD)
        self.assertIn("run-python.ps1", MD)


if __name__ == "__main__":
    unittest.main()
