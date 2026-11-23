"""Tester för xAI-servern (A1 Trendspotter), utan nätverk. Grok ersätts av en attrapp.

Kör: python3 -m unittest discover -s tests
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import date
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT / "mcp"))

import xai_server as x  # noqa: E402


class Svar:
    def __init__(self, kod=200, data=None, text=""):
        self.status_code, self._data, self.text = kod, data or {}, text

    def json(self):
        return self._data


class FalskHttp:
    def __init__(self, svar=None):
        self.anrop = []
        self.svar = svar or Svar(data={
            "output": [
                {"type": "web_search_call"},
                {"type": "message", "content": [{
                    "type": "output_text",
                    "text": "1. Sleep tourism keeps growing.",
                    "annotations": [{"type": "url_citation", "url": "https://example.com/sleep"}],
                }]},
            ],
            "citations": ["https://example.com/sleep", "https://x.com/i/status/1"],
        })

    def post(self, url, json=None, headers=None):
        self.anrop.append((url, json, headers))
        return self.svar


IDAG = date(2026, 11, 24)


class TestFragan(unittest.TestCase):
    def test_godkand_fraga(self):
        self.assertEqual(x.kontrollera_fraga("  hotel  spa trends ", 7), ("hotel spa trends", 7))

    def test_internt_material_stoppas(self):
        for fraga in ["LIVV-2026-0003 trends", "read 00_Underlag about towels", "Innehallsregister status",
                      "contact anna@livv.se", "call 070 123 45 67", "summary of brief.docx", "x" * 301]:
            with self.subTest(fraga=fraga):
                with self.assertRaises(x.Fragefel):
                    x.kontrollera_fraga(fraga, 7)

    def test_dagar(self):
        for dagar in (0, 31, "sju"):
            with self.assertRaises(x.Fragefel):
                x.kontrollera_fraga("hotel trends", dagar)
        self.assertEqual(x.kontrollera_fraga("hotel trends 2026", "14")[1], 14)


class TestGrok(unittest.TestCase):
    def test_skickar_bara_fragan(self):
        http = FalskHttp()
        text = x.Grok(http, "nyckel", "grok-test").trendsok("spa wellness hotels Nordic", 7, IDAG)
        url, kropp, huvud = http.anrop[0]
        self.assertEqual(url, x.XAI_API)
        self.assertEqual(huvud["Authorization"], "Bearer nyckel")
        self.assertEqual(kropp["model"], "grok-test")
        self.assertEqual([v["type"] for v in kropp["tools"]], ["web_search", "x_search"])
        self.assertEqual(kropp["tools"][1]["from_date"], "2026-11-17")
        self.assertIn("Topic: spa wellness hotels Nordic", kropp["input"][1]["content"])
        self.assertIn("Sleep tourism", text)
        self.assertIn("idéunderlag", text)
        self.assertEqual(text.count("https://example.com/sleep"), 1, "Källor ska inte upprepas")
        self.assertIn("https://x.com/i/status/1", text)

    def test_utan_nyckel_skickas_inget(self):
        http = FalskHttp()
        with self.assertRaises(x.Fragefel) as fel:
            x.Grok(http, "", "m").trendsok("hotel trends", 7, IDAG)
        self.assertIn("XAI_API_KEY", str(fel.exception))
        self.assertEqual(http.anrop, [])

    def test_fel_fran_xai(self):
        http = FalskHttp(Svar(401, {"error": "Incorrect API key"}))
        with self.assertRaises(x.Fragefel) as fel:
            x.Grok(http, "fel", "m").trendsok("hotel trends", 7, IDAG)
        self.assertIn("401", str(fel.exception))
        self.assertIn("nyckeln godtogs inte", str(fel.exception))

    def test_svar_med_output_text(self):
        text, kallor = x.tolka_svar({"output_text": "Trend A", "citations": [{"url": "https://a.se"}]})
        self.assertEqual((text, kallor), ("Trend A", ["https://a.se"]))


class TestServern(unittest.TestCase):
    def test_verktyget_och_felmeddelandet(self):
        server = x.bygg_server(lambda: x.Grok(FalskHttp(), "nyckel", "m"))
        verktyg = asyncio.run(server.list_tools())
        self.assertEqual([v.name for v in verktyg], ["trendsok"])
        svar = asyncio.run(server.call_tool("trendsok", {"fraga": "hotel amenities trends", "dagar": 7}))
        self.assertIn("Sleep tourism", svar.content[0].text)
        try:
            asyncio.run(server.call_tool("trendsok", {"fraga": "LIVV-2026-0003"}))
            text = "inget fel"
        except Exception as fel:
            text = str(fel)
        self.assertIn("aldrig internt material", text)


if __name__ == "__main__":
    unittest.main()
