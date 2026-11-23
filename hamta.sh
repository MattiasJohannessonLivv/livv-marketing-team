# Hämtar senaste godkända versionen av projektet från main. Läses in av starta.sh och tavla.sh.
#
# Bara main hämtas: den grenen ändras först när Mattias har slagit ihop en pull request.
# Hämtningen spolar bara framåt (--ff-only) och skriver aldrig över lokala ändringar.
# Går den inte att göra startar teamet ändå, med den version som finns, och säger varför.
# Stäng av med LIVV_HAMTA=0.

if [ "${LIVV_HAMTA:-1}" != "0" ] && git rev-parse --git-dir >/dev/null 2>&1; then
  livv_gren="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo okand)"
  if [ "$livv_gren" != "main" ]; then
    echo "Obs: projektet står på grenen $livv_gren, inte main. Ingen automatisk hämtning." >&2
    echo "     Byt en gång med: git checkout main" >&2
  else
    livv_fore="$(git rev-parse --short HEAD)"
    if git pull --ff-only --quiet origin main 2>/dev/null; then
      livv_efter="$(git rev-parse --short HEAD)"
      if [ "$livv_fore" != "$livv_efter" ]; then
        echo "Uppdaterad från main: $livv_fore till $livv_efter."
      fi
    else
      echo "Kunde inte hämta från main (inget nät, eller lokala ändringar). Startar med version $livv_fore." >&2
    fi
  fi
fi
