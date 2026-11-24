"""Publicering från teamtavlan när Mattias själv klickar Publicera.

Ingen agent använder den här filen. Agenterna har inga verktyg för att publicera,
och spärren stoppar alla anrop till LinkedIn och X. Det här anropas bara av
teamtavlans server när Mattias har bekräftat en publicering i tavlan.

Nycklarna läses från miljön (.env) och LinkedIn-inloggningen från .env.linkedin.
Båda skyddas av spärren och ignoreras av Git.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

ROT = Path(__file__).resolve().parent.parent
LINKEDIN_NYCKELFIL = ROT / ".env.linkedin"
LINKEDIN_API = "https://api.linkedin.com/rest"
LINKEDIN_OAUTH = "https://www.linkedin.com/oauth/v2"
LINKEDIN_SCOPE = "w_organization_social r_organization_social"
X_API = "https://api.x.com/2"
X_MAXTECKEN = 280


class Publiceringsfel(Exception):
    pass


# ---------------------------------------------------------------------------
# Bekräftelse i en ruta från macOS före varje publicering
# ---------------------------------------------------------------------------
# Tavlans nyckel finns i sidan som servern levererar, så ett program på datorn som
# anropar 127.0.0.1:8787 direkt kan skicka samma anrop som tavlan. Därför räcker inte
# klicket i webbläsaren. Rutan visas av tavlans egen server och måste besvaras av en
# människa vid datorn. Utan svar, med Avbryt eller där rutan inte kan visas: ingen publicering.

BEKRAFTA_KNAPP = "Publish"
AVBRYT_KNAPP = "Cancel"
BEKRAFTA_SEKUNDER = 120
FORHANDSVISNING = 700

BEKRAFTA_SKRIPT = [
    "on run argv",
    f'display dialog (item 1 of argv) with title "Livv teamtavla" buttons {{"{AVBRYT_KNAPP}", "{BEKRAFTA_KNAPP}"}} '
    f'default button "{AVBRYT_KNAPP}" cancel button "{AVBRYT_KNAPP}" with icon caution giving up after {BEKRAFTA_SEKUNDER}',
    'return (button returned of result) & "|" & ((gave up of result) as text)',
    "end run",
]


def bekraftelsetext(objekt_id: str, kanal: str, sida: str, text: str, bildnamn: str = "") -> str:
    visas = text if len(text) <= FORHANDSVISNING else text[:FORHANDSVISNING].rstrip() + " …"
    return (f"Publish {objekt_id} on {kanal} as {sida}?\n\n{visas}\n\n"
            f"Image: {bildnamn or 'none'}\n\n"
            "The post goes out immediately and cannot be withdrawn from here.")


def macos_bekraftelse(objekt_id: str, kanal: str, sida: str, text: str, bildnamn: str = "",
                      kor: Any = None, hitta: Any = None, plattform: str | None = None) -> bool:
    """Visar rutan och returnerar True bara om Mattias klickade Publicera."""
    import shutil
    import subprocess
    import sys

    kor = kor or subprocess.run
    hitta = hitta or shutil.which
    if (plattform or sys.platform) != "darwin" or not hitta("osascript"):
        raise Publiceringsfel("Publishing needs a confirmation dialog from macOS, and it cannot be shown here. "
                              "Nothing was published. Publish from the board on the Mac, or by hand from the company page.")
    argument = ["osascript"]
    for rad in BEKRAFTA_SKRIPT:
        argument += ["-e", rad]
    # Texten skickas som argument och blir aldrig en del av skriptet.
    argument.append(bekraftelsetext(objekt_id, kanal, sida, text, bildnamn))
    try:
        svar = kor(argument, capture_output=True, text=True, timeout=BEKRAFTA_SEKUNDER + 30)
    except Exception:
        return False
    return svar.returncode == 0 and (svar.stdout or "").strip() == f"{BEKRAFTA_KNAPP}|false"


# ---------------------------------------------------------------------------
# Inläggstexten
# ---------------------------------------------------------------------------

_RUBRIK_RE = re.compile(r"^#{1,6}\s*(.+?)\s*$", re.M)


def inlaggstext(utkast: str) -> str | None:
    """Texten under rubriken Inläggstext, utan anteckningarna. None om avsnittet saknas."""
    rubriker = list(_RUBRIK_RE.finditer(utkast or ""))
    for i, m in enumerate(rubriker):
        if m[1].strip().lower().rstrip(":") in {"inläggstext", "inlaggstext", "post text"}:
            slut = rubriker[i + 1].start() if i + 1 < len(rubriker) else len(utkast)
            text = utkast[m.end():slut].strip()
            return text or None
    return None


# LinkedIn tolkar de här tecknen som formatering och kräver att de skyddas med \
_LINKEDIN_RESERVERADE = re.compile(r"([\\|{}@\[\]()<>#*_~])")


def linkedin_text(text: str) -> str:
    return _LINKEDIN_RESERVERADE.sub(r"\\\1", text)


# ---------------------------------------------------------------------------
# Inställningar
# ---------------------------------------------------------------------------

def _par(varde: str) -> dict[str, str]:
    """'Livv.se=42934065;Unique=123' till en ordbok."""
    ut = {}
    for del_ in (varde or "").split(";"):
        if "=" in del_:
            k, v = del_.split("=", 1)
            if k.strip() and v.strip():
                ut[k.strip()] = v.strip()
    return ut


def linkedin_sidor(env=os.environ) -> dict[str, str]:
    """Sidans namn till organisationens URN."""
    return {namn: (v if v.startswith("urn:li:organization:") else f"urn:li:organization:{v}")
            for namn, v in _par(env.get("LINKEDIN_SIDOR", "")).items()}


def linkedin_version(idag: date | None = None) -> str:
    """LinkedIn kräver en API-version på formen YYYYMM som inte är för gammal eller ny."""
    if os.environ.get("LINKEDIN_VERSION"):
        return os.environ["LINKEDIN_VERSION"]
    d = (idag or date.today()).replace(day=1) - timedelta(days=45)
    return f"{d:%Y%m}"


def las_linkedin_nyckel(fil: Path = LINKEDIN_NYCKELFIL) -> dict[str, Any] | None:
    try:
        data = json.loads(fil.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not data.get("access_token"):
        return None
    return data


def spara_linkedin_nyckel(svar: dict[str, Any], fil: Path = LINKEDIN_NYCKELFIL) -> None:
    data = {
        "access_token": svar["access_token"],
        "gar_ut": int(time.time()) + int(svar.get("expires_in", 0)),
        "refresh_token": svar.get("refresh_token", ""),
    }
    fil.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(fil, 0o600)


def kanaler(env=os.environ, nyckel: dict | None = None) -> dict[str, Any]:
    """Vad som är kopplat just nu, och varför något inte är det. Visas i tavlan."""
    nyckel = nyckel if nyckel is not None else las_linkedin_nyckel()
    sidor = linkedin_sidor(env)
    li: dict[str, Any] = {"sidor": list(sidor), "redo": False}
    if not (env.get("LINKEDIN_CLIENT_ID") and env.get("LINKEDIN_CLIENT_SECRET")):
        li["skal"] = "LinkedIn is not connected yet: the LinkedIn app is missing in .env."
    elif not sidor:
        li["skal"] = "LinkedIn is not connected yet: LINKEDIN_SIDOR is missing in .env."
    elif not nyckel:
        li["skal"] = "Sign in with LinkedIn on the board to connect the company pages."
        li["logga_in"] = True
    elif nyckel.get("gar_ut") and nyckel["gar_ut"] < time.time():
        li["skal"] = "The LinkedIn sign-in has expired. Sign in again on the board."
        li["logga_in"] = True
    else:
        li["redo"] = True
        if nyckel.get("gar_ut"):
            li["dagar_kvar"] = max(0, int((nyckel["gar_ut"] - time.time()) // 86400))
    x_falt = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
    x: dict[str, Any] = {"sidor": [env.get("X_KONTO", "Livv Group")], "redo": all(env.get(f) for f in x_falt)}
    if not x["redo"]:
        x["skal"] = "X is not connected yet: the keys for the Livv Group account are missing in .env."
    return {"LinkedIn": li, "X": x}


# ---------------------------------------------------------------------------
# LinkedIn
# ---------------------------------------------------------------------------

def linkedin_inloggningsadress(client_id: str, redirect: str, state: str) -> str:
    return f"{LINKEDIN_OAUTH}/authorization?" + urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": redirect,
        "state": state, "scope": LINKEDIN_SCOPE,
    })


def linkedin_byt_kod(http: Any, kod: str, redirect: str, env=os.environ) -> dict[str, Any]:
    r = http.post(f"{LINKEDIN_OAUTH}/accessToken", data={
        "grant_type": "authorization_code", "code": kod, "redirect_uri": redirect,
        "client_id": env["LINKEDIN_CLIENT_ID"], "client_secret": env["LINKEDIN_CLIENT_SECRET"],
    })
    if r.status_code != 200:
        raise Publiceringsfel(f"LinkedIn godtog inte inloggningen ({r.status_code}).")
    return r.json()


class LinkedIn:
    def __init__(self, http: Any, token: str, version: str | None = None) -> None:
        self.http = http
        self.token = token
        self.version = version or linkedin_version()

    def _huvud(self, json_: bool = True) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.token}", "LinkedIn-Version": self.version,
             "X-Restli-Protocol-Version": "2.0.0"}
        if json_:
            h["Content-Type"] = "application/json"
        return h

    @staticmethod
    def _kontrollera(r: Any, vad: str) -> None:
        if r.status_code >= 300:
            raise Publiceringsfel(f"LinkedIn svarade {r.status_code} vid {vad}: {r.text[:300]}")

    def ladda_upp_bild(self, sida: str, data: bytes) -> str:
        r = self.http.post(f"{LINKEDIN_API}/images?action=initializeUpload", headers=self._huvud(),
                           json={"initializeUploadRequest": {"owner": sida}})
        self._kontrollera(r, "start av bilduppladdning")
        varde = r.json()["value"]
        u = self.http.put(varde["uploadUrl"], content=data, headers={"Authorization": f"Bearer {self.token}"})
        self._kontrollera(u, "bilduppladdning")
        return varde["image"]

    def publicera(self, sida: str, text: str, bild: bytes | None = None, alt: str = "") -> tuple[str, str]:
        kropp: dict[str, Any] = {
            "author": sida,
            "commentary": linkedin_text(text),
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if bild:
            kropp["content"] = {"media": {"id": self.ladda_upp_bild(sida, bild), "altText": alt}}
        r = self.http.post(f"{LINKEDIN_API}/posts", headers=self._huvud(), json=kropp)
        self._kontrollera(r, "publicering")
        urn = r.headers.get("x-restli-id", "")
        if not urn:
            raise Publiceringsfel("LinkedIn publicerade men skickade inget id tillbaka. Kontrollera sidan.")
        return urn, f"https://www.linkedin.com/feed/update/{urn}/"


# ---------------------------------------------------------------------------
# X (OAuth 1.0a med Livv Groups konto)
# ---------------------------------------------------------------------------

def _pct(s: str) -> str:
    return quote(str(s), safe="~-._")


def oauth1_huvud(metod: str, url: str, env=os.environ, nonce: str | None = None, tid: str | None = None) -> str:
    param = {
        "oauth_consumer_key": env["X_API_KEY"],
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": tid or str(int(time.time())),
        "oauth_token": env["X_ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }
    bas = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted(param.items()))
    signera = "&".join([metod.upper(), _pct(url), _pct(bas)])
    nyckel = f"{_pct(env['X_API_SECRET'])}&{_pct(env['X_ACCESS_TOKEN_SECRET'])}"
    param["oauth_signature"] = base64.b64encode(hmac.new(nyckel.encode(), signera.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{_pct(k)}="{_pct(v)}"' for k, v in sorted(param.items()))


class X:
    def __init__(self, http: Any, env=os.environ) -> None:
        self.http = http
        self.env = env

    def _kontrollera(self, r: Any, vad: str) -> None:
        if r.status_code >= 300:
            raise Publiceringsfel(f"X svarade {r.status_code} vid {vad}: {r.text[:300]}")

    def ladda_upp_bild(self, data: bytes, filnamn: str, alt: str) -> str:
        url = f"{X_API}/media/upload"
        typ = "image/png" if filnamn.lower().endswith(".png") else "image/jpeg"
        r = self.http.post(url, headers={"Authorization": oauth1_huvud("POST", url, self.env)},
                           files={"media": (filnamn, data, typ)}, data={"media_category": "tweet_image"})
        self._kontrollera(r, "bilduppladdning")
        media_id = str((r.json().get("data") or r.json()).get("id") or r.json().get("media_id_string"))
        if alt:
            url = f"{X_API}/media/metadata"
            m = self.http.post(url, headers={"Authorization": oauth1_huvud("POST", url, self.env)},
                               json={"id": media_id, "metadata": {"alt_text": {"text": alt[:1000]}}})
            self._kontrollera(m, "alt-text")
        return media_id

    def publicera(self, text: str, bild: bytes | None = None, filnamn: str = "", alt: str = "") -> tuple[str, str]:
        if len(text) > X_MAXTECKEN:
            raise Publiceringsfel(f"The text is {len(text)} characters. X allows at most {X_MAXTECKEN}.")
        kropp: dict[str, Any] = {"text": text}
        if bild:
            kropp["media"] = {"media_ids": [self.ladda_upp_bild(bild, filnamn, alt)]}
        url = f"{X_API}/tweets"
        r = self.http.post(url, headers={"Authorization": oauth1_huvud("POST", url, self.env)}, json=kropp)
        self._kontrollera(r, "publicering")
        post_id = r.json()["data"]["id"]
        return post_id, f"https://x.com/i/web/status/{post_id}"
