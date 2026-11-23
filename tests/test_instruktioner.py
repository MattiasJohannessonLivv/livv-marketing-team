"""Regler som måste stå kvar i instruktionerna till A0, A3 och A4.

Instruktionerna styr agenterna. De här testerna fångar en ändring som tar bort
en regel av misstag. Kör: python3 -m unittest discover -s tests
"""

import re
import unittest
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent


def las(relativ: str) -> str:
    return (ROT / relativ).read_text(encoding="utf-8")


class TestBildbrief(unittest.TestCase):
    """A0 skriver alltid bildbriefen när Mattias godkänt en text, i chatten eller i tavlan."""

    def setUp(self):
        self.a0 = las("CLAUDE.md")

    def test_efter_godkannande_i_chatten(self):
        steg5 = re.search(r"^5\. \*\*Godkänt\.\*\*.*?(?=^5b\.)", self.a0, re.S | re.M)[0]
        self.assertIn("Skriv sedan bildbriefen direkt", steg5)

    def test_efter_godkannande_i_tavlan(self):
        rad = next(r for r in self.a0.splitlines() if '"Godkände i teamtavlan"' in r)
        self.assertIn("skriva bildbriefen enligt 5b", rad)
        self.assertIn("Finns ingen bildbrief", rad)
        self.assertNotIn("Gör ingenting mer", rad)

    def test_alltid_och_oavsett_var(self):
        steg5b = re.search(r"^5b\. \*\*Bild\.\*\*.*?(?=^6\.)", self.a0, re.S | re.M)[0]
        self.assertIn("alltid, oavsett om han godkände i chatten eller i teamtavlan", steg5b)
        self.assertNotIn("och inlägget ska ha en bild", steg5b)

    def test_kontroll_nar_a0_borjar(self):
        self.assertRegex(self.a0, r"saknar mappen 12_Pictures/<objekt-ID> en fil med image-brief i namnet, skriv bildbriefen nu")

    def test_grunden(self):
        self.assertIn("skriver A0 alltid en bildbrief", las(".claude/skills/livv-grund/SKILL.md"))


class TestIngenTextPaBilden(unittest.TestCase):
    """A4 föreslår aldrig text till bilden, och A3 stoppar det."""

    def test_a4(self):
        a4 = las(".claude/agents/a4-contentcreator.md")
        self.assertIn("Skriv aldrig något till bilden", a4)
        self.assertNotIn("förslag på alt-text", a4)

    def test_a3(self):
        a3 = las(".claude/agents/a3-granskare.md")
        self.assertRegex(a3, r"Bilden: utkastet får inte innehålla något till bilden.*Revidera")


if __name__ == "__main__":
    unittest.main()
