# Livv Groups AI-marknadsteam

Ett AI-marknadsteam i Claude Code för Livv Group, Livv och Unique. Teamet arbetar i en sluten loop ovanpå SharePoint-mappen Livv Marketing Ops: brief, utkast, granskning, godkännande, publicering, mätning och lärande.

Två principer styr allt:
1. Mattias godkänner varje objekt innan det når 04_Godkant.
2. Ingen agent publicerar, schemalägger eller ändrar budgetar, bud eller kampanjer.

Hela specifikationen finns i [docs/arbetsdokument.md](docs/arbetsdokument.md).

## Läge just nu: fas 1, kärnloopen
| Klart | Kommer senare |
|---|---|
| A0 Marketing Director (huvudsessionen) | A2 Researcher, A5 Google (fas 2) |
| A3 Granskare, A4 Contentcreator | A1 Trendspotter, A6 Meta, A7 LinkedIn, A8 X (fas 3) |
| SharePoint-koppling, spärrar, skills | Schemalagda körningar (fas 4) |

Resultatdata läggs in manuellt i fas 1. Grinden till fas 2: tre objekt har gått hela vägen från Brief till Publicerad utan fel i register eller logg.

## Struktur
```
livv-marketing-team/
  CLAUDE.md                     A0:s uppdrag, loopen och hänvisning till skills
  .mcp.json                     SharePoint-servern, hemligheter som platshållare
  .env.example                  mall för hemligheterna (.env ignoreras av Git)
  starta.sh                     startar teamet, i drift eller i utvecklingsläge
  .claude/
    settings.json               modell, behörigheter och registrering av spärren
    agents/
      a3-granskare.md           A3: granskar, kan aldrig skapa briefer
      a4-contentcreator.md      A4: skriver utkast, flyttar inga filer
    skills/
      livv-grund/               arbetsloopen, register, statusflöde, grindar
      livv-skrivregler/         skriv- och publiceringsregler
    hooks/
      sparr-publicering.sh      spärren som körs före varje verktygsanrop
      sparr.py                  spärrens logik
  mcp/
    sharepoint_server.py        egen MCP-server mot Microsoft Graph
    requirements.txt
  docs/
    arbetsdokument.md           specifikationen
    excel-andringslista.md      föreslagna ändringar i Innehallsregister
  tests/
    test_sparr.sh               tester för spärren
    test_sokvagar.py            tester för servern, utan nätverk
    test_excel.py               rullistor och loggkolumner efter skrivning via servern
```

## Så hålls reglerna tekniskt
Reglerna står i livv-grund, men de hålls också i kod, i tre lager:

**1. SharePoint-servern** (`mcp/sharepoint_server.py`) har bara de verktyg loopen behöver. driveId och rotmappen är låsta i koden. Servern arbetar bara med sökvägar inne i Livv Marketing Ops och avvisar allt annat. Den har inga verktyg för att radera, byta namn, dela eller ändra behörigheter. Briefer och utkast skrivs aldrig över: en ny version får nytt vNN. Bara tillåtna statusbyten går att göra, och inget flyttas ut ur 06_Arkiv.

| Verktyg | Vad det gör | A0 | A3 | A4 |
|---|---|---|---|---|
| `lista_mapp`, `las_fil` | Läser i Livv Marketing Ops | ja | ja | ja |
| `skapa_brief` | Ny brief i 01_Briefer | ja | nej | nej |
| `spara_utkast` | Nytt utkast i 02_Utkast | ja | nej | ja |
| `spara_rapport` | Rapport i 08_Rapporter | ja | nej | nej |
| `flytta_objekt` | Flyttar fil vid statusbyte | ja | bara till Granskning eller Avvisad | nej |
| `register_las`, `register_uppdatera` | Läser och ändrar rader i Innehallsregister | ja | ja | ja |
| `register_ny_rad` | Nytt objekt i registret | ja | nej | nej |
| `logga` | Rad i 09_Loggar | ja | ja | ja |

**2. Spärren** (`.claude/hooks/sparr-publicering.sh`) körs före varje verktygsanrop, oavsett vad agenten fått för instruktion:
- Alla MCP-verktyg utanför SharePoint-servern stoppas. Det gäller LinkedIn, Meta, Google, X, e-post, Slack, HubSpot och Canva, även kopplingar från ditt claude.ai-konto. Därmed går det inte att publicera, schemalägga eller ändra budget, bud eller kampanj.
- Flytt till Godkänd, Schemalagd eller Publicerad, och ändring av godkand_av, godkand_datum, publicerad_datum, plattforms_id eller url, kräver att du bekräftar i rutan. När ingen människa sitter vid datorn blir det stopp.
- Radering (`rm`, `find -delete`, `git clean`, `gh ... delete` och liknande) och nätverksanrop från skalet (`curl`, `wget` och liknande) stoppas alltid.
- I drift får agenterna bara skriva lokalt i `.arbetsyta/`, och skalet får bara köra läsande kommandon. `git ls-remote` och `git fetch` räknas som läsande, men utan `--upload-pack` och utan tvingade referenser. `.env` kan aldrig läsas eller ändras.
- `gh` får bara användas i utvecklingsläge.
- A3 och A4 har egna rollspärrar utöver sina verktygslistor.

Servern sparar aldrig om Excel-filerna med ett bibliotek som tolkar hela arbetsboken. Den ändrar bara de berörda cellerna i bladets XML och kopierar resten av filen oförändrad. Annars försvinner rullistor som Excel lagrar som tillägg, till exempel listorna som pekar på det dolda bladet Listor. `tests/test_excel.py` kontrollerar detta och kan köras mot riktiga kopior, se nedan.

**3. Verktygslistor per agent** i `.claude/agents/`. A3 och A4 har varken skal eller lokala skrivverktyg.

## Kom igång

### En gång
1. Installera Claude Code och Python 3.11 eller senare.
2. Klona repot och installera serverns beroenden:
   ```bash
   pip install -r mcp/requirements.txt
   ```
3. Gör en app-registrering i Entra ID med applikationsbehörigheten **Sites.Selected** och bevilja den skrivrätt bara till webbplatsen livv-group-data-it-ai. Skapa en klienthemlighet.
4. Kopiera mallen och fyll i värdena från app-registreringen:
   ```bash
   cp .env.example .env
   ```
5. Kör testerna:
   ```bash
   bash tests/test_sparr.sh
   ```
   ```bash
   python3 -m unittest discover -s tests
   ```

   Testa mot riktiga kopior av Innehallsregister och en loggfil. Kopiorna läses bara:
   ```bash
   LIVV_KOPIOR=/sökväg/till/kopiorna python3 -m unittest discover -s tests
   ```

### Drift och utveckling i separata miljöer
Håll drift och utveckling i separata miljöer redan nu, även i fas 1. Miljövariabeln `LIVV_UTVECKLING` avgör vad spärren tillåter, och den ska aldrig behöva ändras för hand i en pågående session.

| Miljö | LIVV_UTVECKLING | Används till |
|---|---|---|
| Default | saknas eller 0 | Drift: loopen mot Livv Marketing Ops. Agenterna skriver bara i SharePoint och `.arbetsyta/`. Inga ändringar i agenter, skills, hooks eller CLAUDE.md. |
| Livv utveckling | 1 | Utveckling: ändringar i projektet, tester, Git och `gh`. Arbetet görs i en gren och granskas innan det slås ihop. |

I Claude Code på webben är det två miljöer: **Default** för drift och **Livv utveckling** med `LIVV_UTVECKLING=1` satt som miljövariabel. Lokalt sätter `./starta.sh` värdet åt dig. Kör aldrig loopen i miljön Livv utveckling, och gör aldrig projektändringar i Default.

### Starta teamet
```bash
./starta.sh
```
Du pratar med A0. Exempel: "Skapa en brief för ett LinkedIn-inlägg för Livv om vinterkollektionen", eller "Vad väntar på mig?". Första gången frågar Claude Code om du litar på projektmappen och SharePoint-servern: svara ja.

### Ändra teamet
```bash
./starta.sh --utveckling
```
Bara i utvecklingsläge får agenter, skills, hooks och CLAUDE.md ändras. Gör ändringarna i en gren och granska dem innan de slås ihop.

## Vad som väntar på Mattias
- App-registreringen i Entra ID och värdena i `.env`.
- Godkännande av [docs/excel-andringslista.md](docs/excel-andringslista.md).
- Starta API-ansökningarna hos Google Ads och LinkedIn redan nu. Godkännandet kan ta flera veckor och behövs i fas 2 och 3.
- De öppna frågorna sist i arbetsdokumentet, bland annat ersättare för godkännanden när du är borta.
