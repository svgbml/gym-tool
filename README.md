# Gym-tool – hardloop-weekrapport

Elke zondag om 20:39 (Nederlandse tijd) haalt een GitHub Actions-workflow je lopen uit Strava. Daarna gebeurt dit:

- het weekrapport wordt berekend: afstand, tempo, hartslag, doelen, trend en een voorspelde 5/10 km-tijd;
- er gaat een **pushmelding** naar je telefoon en pc via [ntfy](https://ntfy.sh);
- de **webversie** op GitHub Pages wordt bijgewerkt (je kunt die als app installeren).

Webversie: https://svgbml.github.io/gym-tool/

## Hoe het werkt

```
GitHub Actions (zondag) ──► Strava API ──► scripts/weekrapport.py
                                              ├─► ntfy-melding (telefoon/pc)
                                              └─► docs/data/report.json ──► GitHub Pages (webversie/app)
```

| Bestand | Wat |
|---|---|
| `.github/workflows/weekrapport.yml` | Planning (zondag) + handmatig starten |
| `.github/workflows/pages.yml` | Webversie publiceren op GitHub Pages |
| `scripts/weekrapport.py` | Strava ophalen, rapport berekenen, melding sturen |
| `scripts/get_token.py` | Eenmalig: Strava-toegang regelen |
| `docs/` | Webversie (GitHub Pages, installeerbaar als app) |
| `state/strava_token.enc` | Versleutelde, vernieuwde Strava-token (door de workflow beheerd) |
| `tests/` | Tests van de berekening |

## Eenmalig instellen

### 1. Strava API-app aanmaken
1. Ga naar https://www.strava.com/settings/api en maak een app aan.
   - Application Name: `Gym-tool`
   - Category: `Data Importer` (of iets passends)
   - Website: `https://svgbml.github.io/gym-tool/`
   - Authorization Callback Domain: `localhost`
2. Noteer je **Client ID** en **Client Secret**.

### 2. Refresh token ophalen (op je pc)
```bash
pip install requests
python scripts/get_token.py <CLIENT_ID> <CLIENT_SECRET>
```
Open de link en klik op **Authorize**. Je komt uit op een pagina die niet laadt (`localhost/exchange_token?...code=...`). Kopieer de code uit de adresbalk en plak die in het script. Het script toont daarna je refresh token.

### 3. ntfy-app
Installeer ntfy (Android, iOS of https://ntfy.sh/app op je pc). Abonneer je op een topic met een lange naam die niemand kan raden, bijvoorbeeld `stijn-hardlopen-8k3f9x2q`. **Topicnamen zijn openbaar**: iedereen die de naam kent, kan je meldingen lezen.

### 4. GitHub Secrets instellen
Repo → Settings → Secrets and variables → Actions → **New repository secret**:

| Secret | Waarde |
|---|---|
| `STRAVA_CLIENT_ID` | uit stap 1 |
| `STRAVA_CLIENT_SECRET` | uit stap 1 |
| `STRAVA_REFRESH_TOKEN` | uit stap 2 |
| `TOKEN_KEY` | een lange willekeurige tekst (wachtwoordgenerator) |
| `NTFY_TOPIC` | je topicnaam uit stap 3 |

Optioneel, onder het tabblad **Variables**:

| Variable | Standaard | Betekenis |
|---|---|---|
| `DOEL_KM_WEEK` | `5` | weekdoel in km |
| `PUBLISH_HEARTRATE` | leeg | `true` = hartslag ook in de openbare webversie (de melding toont hem altijd) |

### 5. GitHub Pages
Repo → Settings → Pages → Source: **GitHub Actions**. De workflow `pages.yml` publiceert `docs/` bij elke wijziging en na elk weekrapport.

### 6. Testen
Repo → Actions → **Hardloop-weekrapport** → **Run workflow**. Binnen een minuut krijg je de melding en wordt de webversie bijgewerkt.

## Goed om te weten
- **Token:** Strava access tokens verlopen na 6 uur. Het script vraagt elke run een nieuwe aan. Geeft Strava een nieuwe refresh token, dan bewaart het script die versleuteld (met `TOKEN_KEY`) in `state/`.
- **Tijd:** GitHub rekent cron-tijden in UTC. De workflow draait daarom op twee tijden en het script gebruikt alleen de run die om 20:xx Nederlandse tijd valt (zomer- en wintertijd). Bij drukte kan GitHub een run vertragen.
- **60 dagen:** GitHub zet geplande workflows uit na 60 dagen zonder activiteit. Omdat de workflow elke week het rapport commit, gebeurt dat hier niet.
- **Privacy:** de repo is openbaar. Daarom komen standaard alleen afstand, tijden en tempo in de webversie, zonder hartslag en zonder locatie of GPS-route.

## Lokaal testen
```bash
pip install -r requirements.txt pytest
python -m pytest tests
```

## Bronnen
- Strava API – Getting Started: https://developers.strava.com/docs/getting-started/
- ntfy – documentatie: https://docs.ntfy.sh
- GitHub Actions – `schedule`-trigger: https://docs.github.com/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#schedule
- Riegel, P.S. (1981). Athletic records and human endurance. *American Scientist* 69(3): 285–290.
