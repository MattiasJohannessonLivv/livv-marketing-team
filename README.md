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
| A1 Trendspotter med Grok, byggd före fas 3 | |
| A2 Researcher, med exporter i 11_Dataimport | A6 Meta, A7 LinkedIn, A8 X (fas 3) |
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
  hamta.sh                      hämtar senaste main när teamet eller tavlan startar
  tavla/
    server.py                   läser register och logg, serverar tavlan på 127.0.0.1
    beslut.py                   Mattias beslut i tavlan: godkänn och skicka tillbaka
    a0.py                       startar A0 i bakgrunden efter godkännande, för bildbriefen
    publicera.py                publicering till LinkedIn och X, efter bekräftelse i en ruta från macOS
    tavla.html                  teamtavlan
    exempeldata.json            exempel för att visa tavlan utan SharePoint
  .gitignore                    håller hemligheter, .arbetsyta/ och lokala inställningar utanför Git
  .github/
    workflows/tester.yml        kör alla tester vid push till fas-1 och vid pull request mot main
  .claude/
    settings.json               modell, behörigheter och registrering av spärren
    agents/
      a1-trendspotter.md        A1: söker trender med Grok och skriver trendrapporter i 13_Insikter
      a2-researcher.md          A2: analyserar exporter, läser bara och skriver rapporter
      a3-granskare.md           A3: granskar, kan aldrig skapa briefer
      a4-contentcreator.md      A4: skriver utkast, flyttar inga filer, skriver aldrig text till bilden
    skills/
      livv-grund/               arbetsloopen, register, statusflöde, grindar
      livv-skrivregler/         skriv- och publiceringsregler
    hooks/
      sparr-publicering.sh      spärren som körs före varje verktygsanrop
      sparr.py                  spärrens logik
  mcp/
    sharepoint_server.py        egen MCP-server mot Microsoft Graph
    xai_server.py               MCP-server mot xAI med ett verktyg, trendsok, för A1
    requirements.txt
  verktyg/
    excel_andringar.py          engångsverktyg för ändringslistan, körs av Mattias
  docs/
    arbetsdokument.md           specifikationen
    excel-andringslista.md      ändringarna i Innehallsregister, genomförda 17 november 2026
    underlag/
      Bildstil_Please_Disturb.md  bildstilen, originalet ligger i 00_Underlag
  tests/
    test_sparr.sh               tester för spärren
    test_sokvagar.py            tester för servern, utan nätverk
    test_xai.py                 xAI-servern: sökfrågan, stopp för internt material och svaret
    test_felmeddelanden.py      verktygen visar alltid den verkliga orsaken till ett fel
    test_instruktioner.py       regler som måste stå kvar i CLAUDE.md, A3, A4 och livv-grund
    test_excel.py               rullistor och loggkolumner efter skrivning via servern
    test_excel_andringar.py     engångsverktyget för ändringslistan
    test_tavla.py               teamtavlan: omvandling, notiser och webbservern
    test_a0.py                  A0 startas efter godkännande i tavlan, i driftläge och med få verktyg
    test_beslut.py              beslut i tavlan: godkänn, skicka tillbaka och skyddet mot andra sidor
    test_publicera.py           publicering: rutan från macOS, inläggstext, LinkedIn, X och spärrar mot dubbelpublicering
```

## Så hålls reglerna tekniskt
Reglerna står i livv-grund, men de hålls också i kod, i tre lager:

**1. SharePoint-servern** (`mcp/sharepoint_server.py`) har bara de verktyg loopen behöver. driveId och rotmappen är låsta i koden. Servern arbetar bara med sökvägar inne i Livv Marketing Ops och avvisar allt annat. Den har inga verktyg för att radera, byta namn, dela eller ändra behörigheter. Briefer och utkast skrivs aldrig över: en ny version får nytt vNN. Bara tillåtna statusbyten går att göra, och inget flyttas ut ur 06_Arkiv.

| Verktyg | Vad det gör | A0 | A1 | A2 | A3 | A4 |
|---|---|---|---|---|---|---|
| `lista_mapp`, `las_fil` | Läser i Livv Marketing Ops | ja | ja | ja | ja | ja |
| `visa_bild` | Visar ett bildförslag i 12_Pictures för agenten, till exempel för alt-text | ja | nej | nej | nej | nej |
| `skapa_brief` | Ny brief i 01_Briefer | ja | nej | nej | nej | nej |
| `spara_utkast` | Nytt utkast i 02_Utkast. Stoppar utkast med text till bilden | ja | nej | nej | nej | ja |
| `spara_rapport` | Rapport i 08_Rapporter | ja | nej | ja | nej | nej |
| `spara_trendrapport` | Trendrapport i 13_Insikter. Skriver aldrig över | nej | ja | nej | nej | nej |
| `spara_bildbrief` | Bildbrief i 12_Pictures/<objekt-ID>, när texten är godkänd | ja | nej | nej | nej | nej |
| `flytta_objekt` | Flyttar fil vid statusbyte | ja | nej | nej | bara till Granskning eller Avvisad | nej |
| `register_las` | Läser rader i Innehallsregister | ja | nej | ja | ja | ja |
| `register_uppdatera` | Ändrar rader i Innehallsregister | ja | nej | nej | ja | ja |
| `register_ny_rad` | Nytt objekt i registret | ja | nej | nej | nej | nej |
| `logga` | Rad i 09_Loggar | ja | ja | ja | ja | ja |
| `trendsok` (xAI-servern) | Söker trender med Grok på webben och X. Bara korta sökfrågor, aldrig internt material | nej | ja | nej | nej | nej |

Går ett verktyg fel visar det alltid orsaken: spärrens skäl, eller SharePoints svar med kod, fil och Microsofts egen felkod. Ett exempel är 423 när loggfilen är öppen i Excel.

**xAI-servern** (`mcp/xai_server.py`) har bara verktyget `trendsok`. Den skickar en kort sökfråga och ett tidsfönster till Grok och stoppar frågor som innehåller objekt-ID, mappnamn, filnamn, e-postadresser, telefonnummer eller långa textstycken.

**2. Spärren** (`.claude/hooks/sparr-publicering.sh`) körs före varje verktygsanrop, oavsett vad agenten fått för instruktion:
- Alla MCP-verktyg utanför SharePoint-servern stoppas. Det gäller LinkedIn, Meta, Google, X, e-post, Slack, HubSpot och Canva, även kopplingar från ditt claude.ai-konto. Därmed går det inte att publicera, schemalägga eller ändra budget, bud eller kampanj.
- Flytt till Godkänd, Schemalagd eller Publicerad, och ändring av godkand_av, godkand_datum, publicerad_datum, plattforms_id eller url, kräver att du bekräftar i rutan. När ingen människa sitter vid datorn blir det stopp.
- Radering (`rm`, `find -delete`, `git clean`, `gh ... delete` och liknande) och nätverksanrop från skalet (`curl`, `wget` och liknande) stoppas alltid.
- I drift får agenterna bara skriva lokalt i `.arbetsyta/`, och skalet får bara köra läsande kommandon. `git ls-remote` och `git fetch` räknas som läsande, men utan `--upload-pack` och utan tvingade referenser. `.env` kan aldrig läsas eller ändras.
- `gh` får bara användas i utvecklingsläge.
- Bara A1 får använda `trendsok` och `spara_trendrapport`. A1 får inget annat skrivande.
- A1, A2, A3 och A4 har egna rollspärrar utöver sina verktygslistor.

Servern sparar aldrig om Excel-filerna med ett bibliotek som tolkar hela arbetsboken. Den ändrar bara de berörda cellerna i bladets XML och kopierar resten av filen oförändrad. Annars försvinner rullistor som Excel lagrar som tillägg, till exempel listorna som pekar på det dolda bladet Listor. `tests/test_excel.py` kontrollerar detta och kan köras mot riktiga kopior, se nedan.

**3. Verktygslistor per agent** i `.claude/agents/`. A1, A2, A3 och A4 har varken skal eller lokala skrivverktyg.

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
`./starta.sh` och `./tavla.sh` hämtar själva senaste versionen från main innan de startar. Du behöver alltså aldrig köra `git pull`. Det görs i skriptet, utanför Claude, så spärren kan fortsätta stoppa `git pull` i agenterna. Hämtningen kräver att projektet står på main (byt en gång med `git checkout main`). Bara det du slagit ihop i en pull request kommer med, och lokala ändringar skrivs aldrig över. I utvecklingsläge hämtas ingenting. Stäng av med `LIVV_HAMTA=0`.
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

### Trender från A1
A1 Trendspotter söker med Grok på webben och X och skriver en trendrapport i `13_Insikter`. Be A0 om det, till exempel "Be A1 spana på trender inom spa och wellness de senaste två veckorna". Trenderna är idéunderlag. En siffra, ett citat eller ett påstående används i material först när Mattias har verifierat det och fört över det till 00_Underlag. Till Grok skickas bara korta sökfrågor, aldrig internt material.

Engångsinställning:
1. Skapa mappen `13_Insikter` direkt i Livv Marketing Ops. Agenterna får inte skapa huvudmappar.
2. Skapa en API-nyckel på console.x.ai under **API Keys** och lägg den i `.env` som `XAI_API_KEY`. Lägg aldrig nyckeln i en chatt.
3. Starta om teamet. Första gången frågar Claude Code om du godkänner servern xai: svara ja.

### Bilder från Brand Studio
När Mattias har godkänt texten, i chatten eller i teamtavlan, skriver A0 alltid en bildbrief på engelska i `12_Pictures/<objekt-ID>`. Bilderna har aldrig text, och A4 skriver aldrig något till bilden. Brand Studio (Anastasia Johannesson) får en notis i Teams, skapar tre förslag i Atelier och laddar upp dem i samma mapp. Mattias väljer bild i teamtavlan och laddar ned den därifrån. Ingen agent skapar bilder.

Engångsinställning:
1. Skapa mappen `12_Pictures` direkt i Livv Marketing Ops. Agenterna får inte skapa huvudmappar.
2. Lägg `Bildstil_Please_Disturb.md` (finns i `docs/underlag/`) i 00_Underlag när Mattias har godkänt den.
3. Ett flöde i Power Automate pingar Anastasia i Teams. Mattias byggde det 23 november 2026 med namnet **Livv bildbrief till Brand Studio**. Testpingen kom fram samma dag, Anastasia har redigeringsrätt i 12_Pictures, och pingen går nu till henne. Kopplingarna till SharePoint och Teams går via Mattias Microsoft-konto tills IT har flyttat dem till ett tjänstekonto. Flödet är uppsatt så här:
   - Utlösare: SharePoint, *When a file is created (properties only)*, webbplatsen livv-group-data-it-ai, biblioteket Dokument.
   - Villkor: *Folder path* innehåller `Livv Marketing Ops/12_Pictures/` och *File name with extension* innehåller `image-brief`.
   - Åtgärd: Microsoft Teams, *Post message in a chat or channel*, som Flow bot i chatt med Anastasia Johannesson. Meddelande:

     > New image brief from the Livv marketing team: *File name*. Please create three options in Atelier and upload them to the same folder. The brief has the deadline. Open it here: *Link to item*

### Publicera från tavlan
När texten är godkänd, bilden vald och alt-texten godkänd visar tavlan knappen **Publicera** för objektet. Mattias väljer avsändare (Livv.se är förvalt, fler sidor läggs till i `LINKEDIN_SIDOR`), ser exakt vad som går ut och bekräftar i tavlan. Sedan visar tavlans server en ruta från macOS med objekt, kanal, avsändare, text och bild. Först när Mattias klickar **Publicera** i rutan går inlägget ut. Avbryt, ingen reaktion inom två minuter eller en dator utan macOS ger ingen publicering. Tavlan publicerar bara texten under `## Inläggstext` i utkastet, laddar upp bilden med alt-texten, flyttar filen till 05_Publicerat, fyller i publicerad_datum, plattforms_id och url och loggar "Publicerade i teamtavlan". Ett objekt kan bara publiceras en gång från tavlan.

Ingen agent kan publicera. Publiceringen finns bara i tavlans server (`tavla/publicera.py`), och spärren stoppar alla agentanrop till LinkedIn och X. Tavlans nyckel finns i sidan som servern levererar, så ett program på datorn som anropar 127.0.0.1:8787 direkt kommer förbi kontrollen av nyckeln. Därför krävs rutan från macOS: den visas av servern och måste besvaras av en människa vid datorn. Utan nycklar i `.env` är knappen avstängd och tavlan säger vad som saknas.

**Koppla LinkedIn, en gång:**
1. Gå till linkedin.com/developers och välj **Create app**. Ange appens namn, till exempel *Livv Marketing Ops*, välj företagssidan Livv.se, lägg in en länk till integritetspolicyn och Livvs logotyp.
2. Under **Settings**, välj **Verify** vid företagssidan. En admin för Livv.se godkänner via länken som skapas.
3. Under **Products**, begär **Community Management API** och fyll i ansökan. LinkedIn granskar den, och det kan ta flera veckor. Appen bör bara ha den här produkten.
4. Under **Auth**, lägg till Redirect URL `http://localhost:8787/linkedin/svar` och kopiera **Client ID** och **Client Secret** till `.env` (`LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`).
5. När ansökan är godkänd: starta om tavlan, öppna ett godkänt objekt och klicka **Logga in med LinkedIn**. Logga in med kontot som är admin för sidorna. Inloggningen sparas i `.env.linkedin` och gäller i 60 dagar, sedan ber tavlan dig logga in igen.

**Koppla X:** lägg in nycklarna för Livv Groups utvecklarapp i `.env` (`X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`). Appen behöver behörigheten *Read and write*, och nycklarna ska skapas för Livv Groups konto.

Publiceringen mot LinkedIn och X är testad mot attrapper, inte mot de riktiga tjänsterna. Första riktiga publiceringen bör göras på ett objekt där det gör lite om något behöver rättas.

### Teamtavlan
```bash
./tavla.sh
```
Öppnar http://127.0.0.1:8787 i webbläsaren. Tavlan visar teamet runt A0, flödet av objekt, vad som väntar på dig och vad agenterna har gjort. Den läser Innehallsregister och loggfilerna för den här och förra månaden i 09_Loggar, med samma app-registrering som SharePoint-servern, och hämtar nytt var femte minut.

Medan tavlan körs får du en notis på Macen när något nytt väntar på ditt beslut, och listan Väntar på dig har en länk direkt till filen i SharePoint. Notiserna stängs av med `TAVLA_NOTISER=0 ./tavla.sh`.

**Besluta i tavlan.** Under Väntar på dig öppnar du ett objekt med **Läs och godkänn**. Utkastet och briefen visas i tavlan. Du kan:
- **Godkänna.** Knappen kräver en bekräftelse. Tavlan kontrollerar att A3 har godkänt och att objektet står i Granskning, flyttar filen till 04_Godkant, fyller i godkand_av och godkand_datum och loggar att Mattias godkände. Sedan startar tavlan A0 i bakgrunden, som skriver bildbriefen direkt (`tavla/a0.py`). Körningen är i driftläge och kan bara läsa, spara bildbriefen och logga. Utskriften sparas i `.arbetsyta/a0-bildbrief/`. Kan A0 inte startas skriver den bildbriefen nästa gång du startar teamet.
- **Skicka tillbaka med kommentar.** Objektet går tillbaka till Utkast med a3_utfall Revidera, och kommentaren loggas. A0 ger den till A4 nästa gång teamet arbetar.
- **Välja bild och publicera.** Varje godkänt objekt har knappen **Publicera** i listan Väntar på dig. Den öppnar objektet vid publiceringen, se Publicera från tavlan.
- **Kopiera texten** när du hellre publicerar för hand.

Typsnitten är Livvs egna: Crake i rubriker och Inter i text. Har datorn Crake installerat används det direkt. Annars hämtar tavlan Crake-filer från `00_Underlag` eller `00_Underlag/Fonter`, och utan dem visas ett liknande reservtypsnitt. Logotypen hämtas också från `00_Underlag`. Typsnitt och logotyp läggs aldrig i Git.

Tavlan skriver bara när du beslutar i den: godkänner, skickar tillbaka, väljer bild eller publicerar (`tavla/beslut.py`). Den publicerar bara när du klickar Publicera och sedan bekräftar i rutan från macOS, se Publicera från tavlan. Den kan aldrig schemalägga eller ändra något annat. Besluten tas bara emot från tavlan på den egna datorn: servern lyssnar på 127.0.0.1, kontrollerar värd och ursprung och kräver en nyckel som bara finns i sidan den själv levererar. Andra webbsidor i webbläsaren kan alltså inte fatta beslut åt dig. Avsluta med Ctrl+C. Exempeldata utan SharePoint: http://127.0.0.1:8787/?exempel

### Ändra teamet
```bash
./starta.sh --utveckling
```
Bara i utvecklingsläge får agenter, skills, hooks och CLAUDE.md ändras. Gör ändringarna i en gren och granska dem innan de slås ihop.

## Vad som väntar på Mattias
Klart: app-registreringen i Entra ID och kopplingen mot SharePoint (17 november 2026), ändringslistan för Innehallsregister (17 november), bildstilen Please Disturb (17 november) och LinkedIn-appen Livv Marketing Ops, verifierad mot Livv.se (18 november).

Nu:
- **Kör `logga` igen** när ändringarna är sammanslagna och teamet startats om. Verktyget visar nu den verkliga orsaken. Står det 423 är loggfilen öppen i Excel: stäng den överallt, även i webbläsaren, och försök igen. Står det något annat: ge texten till utvecklingssessionen.
- **Testa rutan från macOS** första gången du publicerar från tavlan, gärna på ett objekt där det gör lite om något behöver rättas. Rutan är testad mot en attrapp, inte på en Mac, och den kan hamna bakom andra fönster.
- **Integritetspolicyn på livv.se/se/integritetspolicy** är tom och blockerar LinkedIn. Webbansvarig tar fram texten och den som ansvarar för GDPR godkänner den. Begär sedan Community Management API i appen.
- **Nycklarna för X**: lägg in dem för Livv Groups utvecklarapp, med Read and write, enligt Publicera från tavlan.
- **A1 Trendspotter:** skapa mappen 13_Insikter och lägg API-nyckeln från xAI i `.env`. Se Trender från A1.
- **Tjänstekonto för flödet** Livv bildbrief till Brand Studio: Jesper på IT har fått frågan 23 november 2026. Tills det är klart går flödet via ditt konto.

Senare:
- Starta API-ansökan hos Google Ads redan nu. Godkännandet kan ta flera veckor och behövs i fas 2.
- De öppna frågorna sist i arbetsdokumentet, bland annat ersättare för godkännanden när du är borta.
