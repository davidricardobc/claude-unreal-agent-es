"""Estructura de ue-mcp-safe-edit (no tiene scripts). Correr: python -I tests/test_skill.py
Neutral al idioma: las pruebas revisan estructura y tokens de código, así que pasan con el SKILL.md en español y en inglés."""
import os, re, unittest

TXT = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md"), encoding="utf-8").read()
H2 = re.findall(r"^## (.+)$", TXT, re.M)


def section(pred):
    """Texto de la primera sección de nivel 2 cuyo título cumple pred, hasta el siguiente título de nivel 2."""
    for i, h in enumerate(H2):
        if pred(h):
            start = TXT.index("## " + h) + len(h) + 3
            nxt = TXT.find("\n## ", start)
            return TXT[start:nxt if nxt != -1 else len(TXT)]
    return None


class Skill(unittest.TestCase):
    def test_frontmatter(self):
        self.assertTrue(TXT.startswith("---\nname: ue-mcp-safe-edit\ndescription: ") or TXT.startswith("---\r\nname: ue-mcp-safe-edit"))

    def test_twelve_rules_in_order(self):
        sec = section(lambda h: "12" in h)
        self.assertIsNotNone(sec, "a section whose heading has '12' (the 12 rules)")
        nums = [int(n) for n in re.findall(r"^(\d+)\. \*\*", sec, re.M)]
        self.assertEqual(nums, list(range(1, 13)))

    def test_enough_sections(self):
        self.assertGreaterEqual(len(H2), 6)

    def test_unverified_items_say_how_to_verify(self):
        sec = section(lambda h: re.search(r"(?i)verif", h))
        self.assertIsNotNone(sec)
        items = [l for l in sec.splitlines() if l.startswith("- ")]
        self.assertGreaterEqual(len(items), 4)
        for it in items:
            self.assertRegex(it, r"(?i)verif", it)

    def test_short(self):
        self.assertLess(len(TXT.splitlines()), 95)

    def test_no_personal_data(self):
        self.assertNotRegex(TXT, r"C:\\Users\\|@gmail|\bsk-[A-Za-z0-9]")

    def test_execute_tool_script_is_a_sandbox(self):
        self.assertIn("`import unreal`", TXT)
        self.assertIn("run()", TXT)

    def test_verified_names(self):
        for w in ("editor_toolset.toolsets.scene.SceneTools", "add_rows", "get_referencers",
                  "Template_Default", "toolset_name"):
            self.assertIn(w, TXT)


if __name__ == "__main__":
    unittest.main()
