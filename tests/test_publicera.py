"""Tester för publicering från teamtavlan, utan nätverk. LinkedIn och X ersätts av attrapper."""

from __future__ import annotations

import io
import json
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROT / "tavla"))
sys.path.insert(0, str(ROT / "mcp"))

import beslut as b  # noqa: E402
import publicera as pub  # noqa: E402
import sharepoint_server as sp  # noqa: E402
from test_beslut import PNG, UTKAST, LasVy, grund  # noqa: E402

UTKASTTEXT = """# LIVV-2026-0002

## Inläggstext
One partner. Several areas of expertise (and one ring).

Follow our page for more.

## Anteckningar
- Ingen länk i inläggstexten.
"""

ENV = {"LINKEDIN_CLIENT_ID": "c", "LINKEDIN_CLIENT_SECRET": "s", "LINKEDIN_SIDOR": "Livv.se=42934065;Livv.fi=99"}
NYCKEL = {"access_token": "token", "gar_ut": time.time() + 30 * 86400}


class Svar:
    def __init__(self, kod=200, data=None, huvud=None, text=""):
        self.status_code, self._data, self.headers, self.text = kod, data or {}, huvud or {}, text

    def json(self):
        return self._data


class FalskHttp:
    def __init__(self, svar_post=None):
        self.anrop = []
        self.svar_post = svar_post or {}

    def post(self, url, **kw):
        self.anrop.append(("POST", url, kw))
        for slut, svar in self.svar_post.items():
            if url.endswith(slut) or slut in url:
                return svar
        return Svar(500, text="okänt")

    def put(self, url, **kw):
        self.anrop.append(("PUT", url, kw))
        return Svar(201)


def linkedin_http():
    return FalskHttp({
        "images?action=initializeUpload": Svar(200, {"value": {"uploadUrl": "https://upload", "image": "urn:li:image:1"}}),
        "/posts": Svar(201, huvud={"x-restli-id": "urn:li:share:777"}),
    })


class TestText(unittest.TestCase):
    def test_bara_inlaggstexten(self):
        self.assertEqual(pub.inlaggstext(UTKASTTEXT),
                         "One partner. Several areas of expertise (and one ring).\n\nFollow our page for more.")
        self.assertIsNone(pub.inlaggstext("Bara en text utan rubriker"))
        self.assertIsNone(pub.inlaggstext("## Inläggstext\n\n## Anteckningar\nx"))

    def test_linkedin_skyddar_specialtecken(self):
        self.assertEqual(pub.linkedin_text("A (b) #c @d"), "A \\(b\\) \\#c \\@d")


class TestKanaler(unittest.TestCase):
    def test_avstangt_utan_nycklar(self):
        k = pub.kanaler({}, None)
        self.assertFalse(k["LinkedIn"]["redo"])
        self.assertFalse(k["X"]["redo"])
        self.assertIn("inte kopplad", k["LinkedIn"]["skal"])

    def test_linkedin_kraver_inloggning(self):
        k = pub.kanaler(ENV, None)["LinkedIn"]
        self.assertFalse(k["redo"])
        self.assertTrue(k["logga_in"])
        self.assertEqual(k["sidor"], ["Livv.se", "Livv.fi"])

    def test_linkedin_redo(self):
        k = pub.kanaler(ENV, NYCKEL)["LinkedIn"]
        self.assertTrue(k["redo"])
        self.assertGreaterEqual(k["dagar_kvar"], 29)

    def test_utgangen_inloggning(self):
        k = pub.kanaler(ENV, {"access_token": "t", "gar_ut": time.time() - 10})["LinkedIn"]
        self.assertFalse(k["redo"])
        self.assertIn("gått ut", k["skal"])

    def test_sidor_blir_urn(self):
        self.assertEqual(pub.linkedin_sidor(ENV)["Livv.se"], "urn:li:organization:42934065")


class TestLinkedIn(unittest.TestCase):
    def test_publicera_med_bild_och_alttext(self):
        http = linkedin_http()
        urn, url = pub.LinkedIn(http, "token", "202609").publicera("urn:li:organization:42934065", "Hej (du)", PNG, "A gloved hand")
        self.assertEqual(urn, "urn:li:share:777")
        self.assertEqual(url, "https://www.linkedin.com/feed/update/urn:li:share:777/")
        post = [a for a in http.anrop if a[1].endswith("/posts")][0][2]
        self.assertEqual(post["json"]["author"], "urn:li:organization:42934065")
        self.assertEqual(post["json"]["commentary"], "Hej \\(du\\)")
        self.assertEqual(post["json"]["content"]["media"], {"id": "urn:li:image:1", "altText": "A gloved hand"})
        self.assertEqual(post["headers"]["LinkedIn-Version"], "202609")
        self.assertTrue(any(a[0] == "PUT" for a in http.anrop))

    def test_fel_fran_linkedin(self):
        http = FalskHttp({"/posts": Svar(403, text="no access")})
        with self.assertRaises(pub.Publiceringsfel):
            pub.LinkedIn(http, "t", "202609").publicera("urn:li:organization:1", "Hej")


class TestX(unittest.TestCase):
    ENV = {"X_API_KEY": "k", "X_API_SECRET": "s", "X_ACCESS_TOKEN": "t", "X_ACCESS_TOKEN_SECRET": "ts"}

    def test_signatur_ar_stabil(self):
        a = pub.oauth1_huvud("POST", "https://api.x.com/2/tweets", self.ENV, nonce="n", tid="1")
        self.assertEqual(a, pub.oauth1_huvud("POST", "https://api.x.com/2/tweets", self.ENV, nonce="n", tid="1"))
        self.assertTrue(a.startswith("OAuth "))
        self.assertIn('oauth_signature="', a)

    def test_publicera(self):
        http = FalskHttp({"/media/upload": Svar(200, {"data": {"id": "55"}}), "/media/metadata": Svar(200),
                          "/tweets": Svar(201, {"data": {"id": "999"}})})
        post_id, url = pub.X(http, self.ENV).publicera("Hej", PNG, "a.png", "alt")
        self.assertEqual((post_id, url), ("999", "https://x.com/i/web/status/999"))
        tweet = [a for a in http.anrop if a[1].endswith("/tweets")][0][2]
        self.assertEqual(tweet["json"]["media"]["media_ids"], ["55"])

    def test_for_lang_text(self):
        with self.assertRaises(pub.Publiceringsfel):
            pub.X(FalskHttp(), self.ENV).publicera("x" * 281)


class TestPubliceraFranTavlan(unittest.TestCase):
    def forbered(self, alt=True, vald=True, text=UTKASTTEXT):
        g = grund(status="Godkänd", mapp="04_Godkant/Livv")
        g.filer[f"04_Godkant/Livv/{UTKAST}"] = text.encode()
        g.filer["12_Pictures/LIVV-2026-0002/LIVV-2026-0002_option-c.jpg"] = PNG
        livv = sp.Livv(g)
        if vald:
            livv.logga("Mattias", "LIVV-2026-0002", "Valde bild i teamtavlan", "12_Pictures", "LIVV-2026-0002_option-c.jpg")
        if alt:
            livv.logga("A0", "LIVV-2026-0002", "Alt-text godkänd", "12_Pictures", "A gloved hand holds a brass ring.")
        http = linkedin_http()
        beslut = b.Beslut(LasVy(g), g, lambda: datetime.now(sp.TIDSZON), env=ENV,
                          http_fabrik=lambda: http, linkedin_nyckel=NYCKEL)
        return g, http, beslut

    def test_detalj_visar_forhandsvisning(self):
        g, _, beslut = self.forbered()
        g.finns_orig = g.finns
        d = beslut.detalj("LIVV-2026-0002")
        self.assertTrue(d["inlaggstext"].startswith("One partner."))
        self.assertEqual(d["bild_vald"], "LIVV-2026-0002_option-c.jpg")
        self.assertEqual(d["alt_text"], "A gloved hand holds a brass ring.")
        p = d["publicering"]
        self.assertEqual((p["kanal"], p["standard"], p["redo"], p["hinder"]), ("LinkedIn", "Livv.se", True, []))
        self.assertEqual(p["sidor"], ["Livv.se", "Livv.fi"])

    def test_publicera_uppdaterar_register_och_logg(self):
        g, http, beslut = self.forbered()
        svar = beslut.publicera("LIVV-2026-0002", "Livv.se")
        self.assertIn("urn:li:share:777", svar)
        post = [a for a in http.anrop if a[1].endswith("/posts")][0][2]["json"]
        self.assertEqual(post["author"], "urn:li:organization:42934065")
        self.assertNotIn("Anteckningar", post["commentary"])
        self.assertEqual(post["content"]["media"]["altText"], "A gloved hand holds a brass ring.")
        rad = sp.register_rader(g.filer[sp.REGISTER_FIL], "LIVV-2026-0002")[0]
        self.assertEqual((rad["status"], rad["plattforms_id"], rad["mapp"]), ("Publicerad", "urn:li:share:777", "05_Publicerat/Livv"))
        self.assertIn(f"05_Publicerat/Livv/{UTKAST}", g.filer)
        # En andra publicering stoppas
        with self.assertRaises(sp.Sparrfel):
            beslut.publicera("LIVV-2026-0002", "Livv.se")
        self.assertEqual(len([a for a in http.anrop if a[1].endswith("/posts")]), 1)

    def test_valbar_sida(self):
        g, http, beslut = self.forbered()
        beslut.publicera("LIVV-2026-0002", "Livv.fi")
        post = [a for a in http.anrop if a[1].endswith("/posts")][0][2]["json"]
        self.assertEqual(post["author"], "urn:li:organization:99")

    def test_hinder(self):
        for kw, ord_ in (({"alt": False}, "Alt-texten"), ({"vald": False}, "Välj bild"),
                         ({"text": "Utan avsnitt"}, "Inläggstext")):
            g, http, beslut = self.forbered(**kw)
            with self.assertRaises(sp.Sparrfel) as fel:
                beslut.publicera("LIVV-2026-0002", "Livv.se")
            self.assertIn(ord_, str(fel.exception))
            self.assertEqual(http.anrop, [])

    def test_okand_sida_stoppas(self):
        g, http, beslut = self.forbered()
        with self.assertRaises(sp.Sparrfel):
            beslut.publicera("LIVV-2026-0002", "Mattias privata profil")
        self.assertEqual(http.anrop, [])

    def test_inte_kopplad(self):
        g, http, beslut = self.forbered()
        beslut._linkedin_nyckel = None
        with self.assertRaises(sp.Sparrfel):
            beslut.publicera("LIVV-2026-0002", "Livv.se")
        self.assertEqual(http.anrop, [])


if __name__ == "__main__":
    unittest.main()
