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
    def forbered(self, alt=True, vald=True, text=UTKASTTEXT, svar_i_rutan=True):
        g = grund(status="Godkänd", mapp="04_Godkant/Livv")
        g.filer[f"04_Godkant/Livv/{UTKAST}"] = text.encode()
        g.filer["12_Pictures/LIVV-2026-0002/LIVV-2026-0002_option-c.jpg"] = PNG
        livv = sp.Livv(g)
        if vald:
            livv.logga("Mattias", "LIVV-2026-0002", "Valde bild i teamtavlan", "12_Pictures", "LIVV-2026-0002_option-c.jpg")
        if alt:
            livv.logga("A0", "LIVV-2026-0002", "Alt-text godkänd", "12_Pictures", "A gloved hand holds a brass ring.")
        http = linkedin_http()
        self.rutor = []  # varje bekräftelseruta som visades, med innehållet

        def bekrafta(**kw):
            self.rutor.append(kw)
            return svar_i_rutan

        beslut = b.Beslut(LasVy(g), g, lambda: datetime.now(sp.TIDSZON), env=ENV,
                          http_fabrik=lambda: http, linkedin_nyckel=NYCKEL, bekrafta=bekrafta)
        return g, http, beslut

    def test_rutan_visas_med_det_som_gar_ut(self):
        g, http, beslut = self.forbered()
        beslut.publicera("LIVV-2026-0002", "Livv.fi")
        self.assertEqual(len(self.rutor), 1)
        ruta = self.rutor[0]
        self.assertEqual((ruta["objekt_id"], ruta["kanal"], ruta["sida"]), ("LIVV-2026-0002", "LinkedIn", "Livv.fi"))
        self.assertTrue(ruta["text"].startswith("One partner."))
        self.assertEqual(ruta["bildnamn"], "LIVV-2026-0002_option-c.jpg")

    def test_nej_i_rutan_publicerar_inget(self):
        g, http, beslut = self.forbered(svar_i_rutan=False)
        fore = dict(g.filer)
        with self.assertRaises(sp.Sparrfel) as fel:
            beslut.publicera("LIVV-2026-0002", "Livv.se")
        self.assertIn("bekräftades inte", str(fel.exception))
        self.assertEqual(http.anrop, [])
        self.assertEqual(g.filer, fore, "Inget får flyttas, ändras eller loggas")

    def test_ingen_ruta_vid_hinder(self):
        g, http, beslut = self.forbered(alt=False)
        with self.assertRaises(sp.Sparrfel):
            beslut.publicera("LIVV-2026-0002", "Livv.se")
        self.assertEqual(self.rutor, [])

    def test_standard_ar_rutan_fran_macos(self):
        g = grund(status="Godkänd", mapp="04_Godkant/Livv")
        self.assertIs(b.Beslut(LasVy(g), g)._bekrafta, pub.macos_bekraftelse)

    def test_direktanrop_till_servern_publicerar_inte_utan_rutan(self):
        """Ett program som hämtar nyckeln ur sidan och anropar 127.0.0.1 direkt kommer inte förbi rutan."""
        import re
        import threading
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer

        import server as tavla

        g, http, beslut = self.forbered(svar_i_rutan=False)
        server = ThreadingHTTPServer(("127.0.0.1", 0), tavla.bygg_hanterare(tavla.Cache(lambda: {}), beslut))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            bas = f"http://127.0.0.1:{server.server_address[1]}"
            sida = urllib.request.urlopen(bas + "/", timeout=5).read().decode()
            nyckel = re.search(r'NYCKEL = "([^"]+)"', sida)[1]
            anrop = urllib.request.Request(bas + "/publicera", method="POST", data=b'{"id": "LIVV-2026-0002", "sida": "Livv.se"}',
                                           headers={"Content-Type": "application/json", "X-Tavla-Nyckel": nyckel})
            with self.assertRaises(urllib.error.HTTPError) as fel:
                urllib.request.urlopen(anrop, timeout=5)
            self.assertEqual(fel.exception.code, 502)
            self.assertIn("bekräftades inte", json.loads(fel.exception.read())["fel"])
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(len(self.rutor), 1)
        self.assertEqual(http.anrop, [])


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

class TestRutanFranMacos(unittest.TestCase):
    """Själva rutan. osascript ersätts av en attrapp."""

    class Kor:
        def __init__(self, kod=0, ut="Publicera|false"):
            self.kod, self.ut, self.argument = kod, ut, None

        def __call__(self, argument, **kw):
            self.argument = argument
            return type("Svar", (), {"returncode": self.kod, "stdout": self.ut})()

    def visa(self, kor, plattform="darwin", hitta=lambda namn: "/usr/bin/osascript"):
        return pub.macos_bekraftelse("LIVV-2026-0002", "LinkedIn", "Livv.se", 'Hej "du"\nend run', "a.png",
                                     kor=kor, hitta=hitta, plattform=plattform)

    def test_publicera_klickad(self):
        kor = self.Kor()
        self.assertTrue(self.visa(kor))
        self.assertEqual(kor.argument[0], "osascript")
        # Texten är ett eget argument och blir aldrig en del av skriptet
        self.assertIn('Hej "du"\nend run', kor.argument[-1])
        self.assertIn("Livv.se", kor.argument[-1])
        self.assertNotIn("Hej", " ".join(kor.argument[:-1]))
        self.assertIn('default button "Avbryt"', " ".join(kor.argument))

    def test_avbryt_tidsgrans_och_fel(self):
        for kor in (self.Kor(kod=1, ut=""), self.Kor(ut="|true"), self.Kor(ut="Avbryt|false"), self.Kor(ut="Publicera|true")):
            with self.subTest(ut=kor.ut, kod=kor.kod):
                self.assertFalse(self.visa(kor))

    def test_utan_macos_publiceras_inget(self):
        for plattform, hitta in (("linux", lambda n: "/usr/bin/osascript"), ("darwin", lambda n: None)):
            with self.subTest(plattform=plattform):
                kor = self.Kor()
                with self.assertRaises(pub.Publiceringsfel):
                    self.visa(kor, plattform, hitta)
                self.assertIsNone(kor.argument)


if __name__ == "__main__":
    unittest.main()
