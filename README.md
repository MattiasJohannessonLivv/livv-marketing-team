# Livv Groups AI-marknadsteam

Ett AI-marknadsteam i Claude Code för Livv Group, Livv och Unique. Teamet arbetar i en sluten loop ovanpå SharePoint-mappen Livv Marketing Ops: brief, utkast, granskning, godkännande, publicering, mätning och lärande.

Två principer styr allt:
1. Mattias godkänner varje objekt innan det når 04_Godkant.
2. Ingen agent publicerar, schemalägger eller ändrar budgetar, bud eller kampanjer.

Hela specifikationen finns i [docs/arbetsdokument.md](docs/arbetsdokument.md).

## Läge just nu: fas 1, kärnloopen
| Klart | Kommer senare |
|---|---|
| A0 Marketing Director (huvudsessionen) | A5 Google (fas 2) |
| A2 Researcher, med exporter i 11_Dataimport | A1 Trendspotter, A6 Meta, A7 LinkedIn, A8 X (fas 3) |
| A3 Granskare, A4 Contentcreator | Automatisk import till Matregister (fas 2) |
| SharePoint-koppling, spärrar, skills, teamtavlan | Schemalagda körningar (fas 4) |

Resultatdata läggs in manuellt i fas 1. A2 analyserar exporter som läggs i 11_Dataimport, se nedan. Grinden till fas 2: tre objekt har gått hela vägen från Brief till Publicerad utan fel i register eller logg.

## Struktur
```
livv-marketing-team/
  CLAUDE.md                     A0:s uppdrag, loopen och hänvisning till skills
  .mcp.json                     SharePoint-servern, hemligheter som platshållare
  .env.example                  mall för hemligheterna (.env ignoreras av Git)
  starta.sh                     startar teamet, i drift eller i utvecklingsläge
  tavla.sh                      startar teamtavlan lokalt
  tavla/
    server.py                   läser register och logg, serverar tavlan på 127.0.0.1
    beslut.py                   Mattias beslut i tavlan: godkänn och skicka tillbaka
    tavla.html                  teamtavlan
    exempeldata.json            exempel för att visa tavlan utan SharePoint
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
    test_tavla.py               teamtavlan: omvandling, notiser och webbservern
    test_beslut.py              beslut i tavlan: godkänn, skicka tillbaka och skyddet mot andra sidor
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

### Exporter till A2
A2 analyserar varje vecka det som ligger i 11_Dataimport i SharePoint. Exportera för förra veckan, helst på måndag morgon, och lägg filerna i rätt mapp:

| Mapp i 11_Dataimport | Var exporten görs | Vad som exporteras |
|---|---|---|
| `LinkedIn Livv.se`, `LinkedIn Livv.fi`, `LinkedIn Unique` | Företagssidans adminvy, Analytics, Export | Inlägg (Content) och följare (Followers) |
| `GA4 Livv.se`, `GA4 Livv.fi`, `GA4 Unique` | GA4, Rapporter, dela-ikonen, Ladda ned fil | Trafikförvärv och Sidor och skärmar |
| `GSC Livv.se`, `GSC Livv.fi`, `GSC Unique` | Search Console, Resultat, Exportera | Sökfrågor och sidor |
| `X Livv Group` | X, Analytics | Inläggsstatistik |

Spara som CSV eller XLSX. LinkedIn exporterar som XLS: öppna filen i Excel och spara som XLSX. Döp filen med datum och vecka, till exempel `20261124_linkedin_livvse_v47.xlsx`. Mapparna ligger direkt i 11_Dataimport och skapas för hand första gången. Saknas en export analyserar A2 resten och skriver vad som saknades.

### Bilder från Brand Studio
När Mattias har godkänt texten skriver A0 en bildbrief på engelska i `12_Pictures/<objekt-ID>`. Brand Studio (Anastasia Johannesson) får en notis i Teams, skapar två eller tre förslag i Atelier och laddar upp dem i samma mapp. Mattias väljer bild i teamtavlan och laddar ned den därifrån. Ingen agent skapar bilder.

Engångsinställning:
1. Skapa mappen `12_Pictures` direkt i Livv Marketing Ops. Agenterna får inte skapa huvudmappar.
2. Lägg `Bildstil_Please_Disturb.md` (finns i `docs/underlag/`) i 00_Underlag när Mattias har godkänt den.
3. Skapa ett flöde i Power Automate som pingar Anastasia i Teams:
   - Utlösare: SharePoint, *When a file is created (properties only)*, webbplatsen livv-group-data-it-ai, biblioteket Dokument.
   - Villkor: *Folder path* innehåller `Livv Marketing Ops/12_Pictures/` och *File name with extension* innehåller `image-brief`.
   - Åtgärd: Microsoft Teams, *Post message in a chat or channel*, som Flow bot i chatt med Anastasia Johannesson. Meddelande:

     > New image brief from the Livv marketing team: *File name*. Please create two or three options in Atelier and upload them to the same folder. The brief has the deadline. Open it here: *Link to item*

### Teamtavlan
```bash
./tavla.sh
```
Öppnar http://127.0.0.1:8787 i webbläsaren. Tavlan visar teamet runt A0, flödet av objekt, vad som väntar på dig och vad agenterna har gjort. Den läser Innehallsregister och loggfilerna för den här och förra månaden i 09_Loggar, med samma app-registrering som SharePoint-servern, och hämtar nytt var femte minut.

Medan tavlan körs får du en notis på Macen när något nytt väntar på ditt beslut, och listan Väntar på dig har en länk direkt till filen i SharePoint. Notiserna stängs av med `TAVLA_NOTISER=0 ./tavla.sh`.

**Besluta i tavlan.** Under Väntar på dig öppnar du ett objekt med **Läs och godkänn**. Utkastet och briefen visas i tavlan. Du kan:
- **Godkänna.** Knappen kräver en bekräftelse. Tavlan kontrollerar att A3 har godkänt och att objektet står i Granskning, flyttar filen till 04_Godkant, fyller i godkand_av och godkand_datum och loggar att Mattias godkände.
- **Skicka tillbaka med kommentar.** Objektet går tillbaka till Utkast med a3_utfall Revidera, och kommentaren loggas. A0 ger den till A4 nästa gång teamet arbetar.
- **Kopiera texten** när ett godkänt objekt ska publiceras.

Det är det enda tavlan skriver (`tavla/beslut.py`). Den kan aldrig publicera, schemalägga eller ändra något annat. Besluten tas bara emot från tavlan på den egna datorn: servern lyssnar på 127.0.0.1, kontrollerar värd och ursprung och kräver en nyckel som bara finns i sidan den själv levererar. Andra webbsidor i webbläsaren kan alltså inte fatta beslut åt dig. Avsluta med Ctrl+C. Exempeldata utan SharePoint: http://127.0.0.1:8787/?exempel

### Ändra teamet
```bash
./starta.sh --utveckling
```
Bara i utvecklingsläge får agenter, skills, hooks och CLAUDE.md ändras. Gör ändringarna i en gren och granska dem innan de slås ihop.

## Vad som väntar på Mattias
Klart 17 november 2026: app-registreringen i Entra ID och hemligheterna på Mattias dator. Kopplingen mot SharePoint är testad därifrån.

- Godkännande av [docs/excel-andringslista.md](docs/excel-andringslista.md).
- Starta API-ansökningarna hos Google Ads och LinkedIn redan nu. Godkännandet kan ta flera veckor och behövs i fas 2 och 3.
- De öppna frågorna sist i arbetsdokumentet, bland annat ersättare för godkännanden när du är borta.
