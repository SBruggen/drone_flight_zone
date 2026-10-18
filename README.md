# Drone Flight Zone

Pythonhulpmiddelen om DJI-waypointmissies te analyseren en zichtbaar te maken
voor de voorbereiding van droneopnames voor 3D-reconstructie.

De hoofdworkflow zet bestaande KMZ-vluchtplannen om naar kaartlagen voor QGIS.
Daarnaast is er een **experimentele** workflow om Aerial 3D-missies samen te
voegen voor de DJI Mavic 3T. Deze scripts berekenen zelf geen nieuw vluchtplan
of 3D-model en sturen geen drone aan.

> **Bekend aandachtspunt bij samengevoegde missies:** na het hervatten na een
> batterijwissel kan de gimbal-tilt (verticale camerahoek) aanvankelijk verkeerd
> staan. Het merge-script bewaart bestaande gimbalacties, maar voegt niet op elk
> waypoint een expliciete tiltactie toe. De correcte hoek op ieder hervatpunt
> is dus niet gegarandeerd. Zie [bekende werkpunten](#bekende-werkpunten-uit-de-praktijkevaluatie)
> en [de merge-handleiding](MERGE_KMZ.md).

## Wat staat er in deze repository?

| Bestand | Functie |
| --- | --- |
| `kmz_to_gpkg.py` | KMZ omzetten naar GeoPackage met waypoints, routes, missiegebieden en theoretische beelddekking. |
| `merge_kmz.py` | Experimenteel samenvoegen van ondersteunde Aerial 3D-exports voor de Mavic 3T. |
| `MERGE_KMZ.md` | Ondersteunde merge-invoer, opties, beperkingen en controleprocedure. |
| `audit_merged_kmz.py` | Bestaande merge-uitvoer vergelijken met de bronnen; gebruikt de vaste mapstructuur `output/merged/`. |
| `disable_finish_rth.py` | Afzonderlijk hulpscript dat in kopieën de missie-eindactie `goHome` naar `noAction` omzet; dit schakelt andere RTH-oorzaken niet uit. |
| `test_merge_kmz.py` | Regressietests voor het merge-script, met de bestaande ZOL-testdataset. |
| `requirements.txt` | Pythonafhankelijkheden voor de conversie naar GeoPackage. |
| `environment.yml` | Alternatieve conda-omgeving met dezelfde pakketten en GDAL voor rasteruitvoer. |
| `qgis legende bestanden/` | QML-stijlbestanden om punten en routes in QGIS op te maken. |

## Enkele geodatabegrippen

- **KMZ / WPML:** een KMZ is een ZIP-container. DJI-missies bevatten hierin XML
  met waypointcoördinaten en acties, onder meer in `wpmz/waylines.wpml`.
  Een willekeurig KMZ-kaartbestand is niet automatisch een ondersteunde missie.
- **GeoPackage (`.gpkg`):** een SQLite-bestand met meerdere benoemde kaartlagen.
  Een laag is vergelijkbaar met een tabel met een extra geometriekolom.
- **Vector en raster:** punten, lijnen en polygonen zijn vectorgeometrieën;
  een raster is een grid met een waarde per cel, bijvoorbeeld het aantal beelden.
- **CRS:** het coördinatenreferentiesysteem. GPS gebruikt lengte- en breedtegraad
  in graden. Voor buffers, afstanden en oppervlakten gebruikt dit project een
  geprojecteerd CRS met meters als eenheid, standaard Belgian Lambert 72
  (`EPSG:31370`). Kies buiten dit toepassingsgebied een passend lokaal CRS.
- **GeoPandas, Shapely, PyProj en Pyogrio:** respectievelijk tabellen met geometrie,
  geometrische bewerkingen, coördinatentransformaties en het lezen/schrijven van
  geodatabestanden. Afhankelijkheden zoals pandas en NumPy worden mee geïnstalleerd.

## Installatie

Download de repository als ZIP en pak die uit, of clone ze met Git. Open een
terminal **in de uitgepakte projectmap**, waar `kmz_to_gpkg.py` staat.
Gebruik bij voorkeur Python **3.11**; dat is de lokaal gecontroleerde versie.
[QGIS](https://qgis.org/) is alleen nodig om de resultaten op een kaart te bekijken,
niet om de Pythonconversie uit te voeren.

### Optie A: Python met venv en pip

Voor GeoPackage-uitvoer is een normale virtuele Pythonomgeving voldoende.
Op Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Als PowerShell het activatiescript blokkeert, kun je zonder activatie werken:
gebruik dan `.\.venv\Scripts\python.exe` in plaats van `python` bij de pip- en
scriptcommando's. Een wijziging aan het systeembeleid is daarvoor niet nodig.

Op Linux of macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Optie B: conda, inclusief optionele rasteruitvoer

Gebruik een conda-installatie, bijvoorbeeld Miniforge, en open een terminal
waarin `conda` beschikbaar is:

```text
conda env create -f environment.yml
conda activate drone-flight-zone
```

Hiermee wordt ook GDAL geïnstalleerd. Voor `--raster-output` roept het script
het externe programma `gdal_rasterize` aan. De GDAL-bibliotheek in een pip-wheel
van Pyogrio levert dit terminalprogramma niet mee. Houd de conda-omgeving bij
conda-forge; combineer de twee installatieroutes niet in dezelfde omgeving.

### Installatie controleren

```text
python -c "import geopandas, shapely, pyproj, pyogrio; print('Geodatapakketten geladen')"
python kmz_to_gpkg.py --help
python merge_kmz.py --help
```

Bij optie B kun je ook `gdal_rasterize --version` uitvoeren. `requirements.txt`
en `environment.yml` gebruiken versiebereiken en zijn geen volledige lockfiles.
De merge- en auditscripts zelf gebruiken alleen de Pythonstandaardbibliotheek.

Installatieachtergrond: [GeoPandas](https://geopandas.org/en/stable/getting_started/install.html),
[Pyogrio](https://pyogrio.readthedocs.io/en/latest/install.html) en
[GDAL](https://gdal.org/en/stable/download.html).

## Eerste conversie: van vluchtplan naar kaart

Plaats eigen DJI-waypointmissies in een aparte map per zone. Bijvoorbeeld:

```text
data/
  workshop_zone/
    Mission_1.kmz
    Mission_2.kmz
output/
```

`workshop_zone` is een voorbeeldnaam: maak deze map zelf aan en voeg eigen
exports toe. Voor onderstaande voorbeelden zijn geen persoonlijke bestandspaden
nodig. Voer vanuit de projectmap uit:

```text
python kmz_to_gpkg.py data/workshop_zone -o output/workshop.gpkg --no-vector-overlap
```

Het script leest alle `.kmz`-bestanden in de opgegeven map en submappen. De
bronbestanden blijven ongewijzigd. **Een bestaand uitvoer-GeoPackage op hetzelfde
pad wordt vervangen.** Sluit het bestand in QGIS voordat je het opnieuw maakt.

`--no-vector-overlap` slaat de relatief zware exacte overlapberekening over;
de overige lagen worden wel aangemaakt. Laat de optie weg om ook de vectorlaag
`beeld_overlap` te berekenen. Er kunnen ook afzonderlijke KMZ-bestanden of
meerdere invoerpaden worden meegegeven.

### Aangemaakte lagen

Lege lagen worden niet naar het GeoPackage geschreven.

| Laag | Inhoud |
| --- | --- |
| `waypoints` | Punten met volgnummer, label, hoogte, snelheid, koers, gimbalhoek en foto-indicator. |
| `vliegroutes` | Eén lijn per missie met minstens twee waypoints, in waypointvolgorde. |
| `missiepolygonen` | Eén convex hull van alle waypoints per missie, met standaard 5 meter buffer. |
| `kijkrichtingen` | Lijnen van waypoints naar het opgegeven doel, het point of interest (POI). |
| `cirkelcentra` | Gereconstrueerde centra van cirkelvormige opnamebanen met hetzelfde POI. |
| `vliegcirkels` | Gereconstrueerde cirkels met de mediane afstand van waypoints tot hun POI als straal. |
| `foto_footprints` | Geschatte projectie van het camerabeeld op een horizontaal vlak. |
| `beeld_overlap` | Niet-overlappende gebieden met het theoretische aantal overlappende beelden, vanaf twee beelden. |

`mission` komt van de bestandsnaam; `zone` komt van de naam van de directe
bovenliggende map. `vlucht_id` combineert beide. Gebruik daarom verschillende
zonemappen als twee bestanden allebei `Mission_1.kmz` heten. Een waypointlabel
zoals `Mission_1-001` is op zichzelf niet uniek over meerdere zones.

### Missiegebieden en geprinte kaarten in QGIS

Open `output/workshop.gpkg` in QGIS en kies de gewenste lagen.

1. Plaats `missiepolygonen` onder `vliegroutes` en `waypoints`.
2. Kies voor polygonen en routes gecategoriseerde symbologie op `vlucht_id`
   en ken dezelfde categorieën dezelfde kleuren toe.
3. Stel de polygoonvulling in op ongeveer **20% dekking** (80% transparantie)
   met een dunne rand in de missiekleur. Label de gebieden met `mission`.
4. Verberg op een overzichtskaart de kijkrichtingen, vliegcirkels en individuele
   waypointlabels. Bewaar deze details voor een afzonderlijke waypointkaart.
5. Label op de detailkaart de waypoints met `label` of `wp_nr`; geef
   `beeld_overlap` eventueel een oplopende kleurenschaal op `overlap_aantal`.

Een convex hull is de buitenste omhullende van de waypointpunten. Die overbrugt
inhammen en openingen en geeft een overzichtsgebied, geen werkelijke fotodekking.
De buffer is instelbaar met `--mission-buffer 10` (meter; positief en eindig).
Ook één waypoint of punten op één rechte lijn krijgen een gebufferde polygoon.
De velden `buffer_m` en `oppervlakte_m2` beschrijven het resultaat. De kaartopmaak
stel je in QGIS in; het script slaat die niet automatisch in het GeoPackage op.

### Meegeleverde QGIS-stijlen (QML)

In de map [qgis legende bestanden](qgis%20legende%20bestanden/) staan enkele
herbruikbare laagstijlen: `waypoints.qml` voor waypointpunten, `vliegroutes.qml`
voor routelijnen en `vluchtmissies.qml` voor lijnen met kleuren per `mission`.
Deze bestanden bevatten de kaartopmaak, niet de geodata zelf.

Open in QGIS de **Laageigenschappen** van de bijbehorende laag en kies via
**Stijl → Stijl laden** het gewenste QML-bestand. Pas de missiecategorieën en
kleuren zo nodig aan je eigen dataset aan.

## Beelddekking, missieselectie en overlaprasters

Footprints zijn een **theoretische benadering** op vlak terrein. Ze gebruiken
hoogte, koers en gimbal-pitch, standaard een diagonale beeldhoek van 82,1 graden
met een 4:3-beeldverhouding. Stem deze parameters af op de gebruikte camera:

```text
python kmz_to_gpkg.py data/workshop_zone -o output/workshop_dekking.gpkg --diagonal-fov 82.1 --aspect-ratio 1.333333 --no-vector-overlap
```

Standaard tellen alleen waypoints met een WPML-`takePhoto`-actie mee voor
footprints, en moeten hoogte, koers en gimbalhoek beschikbaar zijn. Bij bronnen
zonder fotoacties kun je met `--assume-photo-at-waypoints` expliciet één foto
per waypoint simuleren. Dit voegt geen fotoacties aan de vluchtmissie toe.
`foto_basis` vermeldt of een fotoactie of een aanname is gebruikt.

Met `--footprint-plane aim` wordt geprojecteerd op de WPML-POI-hoogte in plaats
van maaiveld (`ground`, standaard). Bij vlieghoogte 80 m en POI-hoogte 15 m
is de effectieve projectiehoogte 65 m; `projectievlak_m` registreert het vlak.
De berekening gebruikt geen terrein- of gebouwenmodel en bewijst geen werkelijk
behaalde overlap of geschiktheid voor 3D-reconstructie.

Selecteer missienummers uit bestanden met namen als `Mission_1.kmz`:

```text
python kmz_to_gpkg.py data/workshop_zone --include-missions 1 2 -o output/workshop_selectie.gpkg --no-vector-overlap
```

Voor rasteruitvoer, met GDAL beschikbaar in de actieve omgeving:

```text
python kmz_to_gpkg.py data/workshop_zone -o output/workshop_raster.gpkg --raster-output output/workshop_overlap.tif --raster-resolution 1 --no-vector-overlap
```

Iedere footprint telt één op bij een rastercel. Het GeoTIFF gebruikt `UInt16`,
waarde 0 als NoData en standaard cellen van 1 meter. Zonder `--include-missions`
worden alle gevonden missies verwerkt. Exacte vectoroverlap wordt globaal over
alle footprints berekend; objecten in `beeld_overlap` overlappen elkaar niet.

## Missies samenvoegen (experimenteel)

Lees eerst [MERGE_KMZ.md](MERGE_KMZ.md) voor de ondersteunde Aerial 3D-exportvorm,
hoogtereferentie, camera-instellingen, bestandsvolgorde en beperkingen.
Begin met een controle zonder uitvoerbestand:

```text
python merge_kmz.py data/workshop_zone -o output/workshop_merged.kmz --dry-run
```

Laat `--dry-run` weg om het KMZ-bestand en bijbehorende JSON-rapport te maken.
Bronnen worden niet gewijzigd; bestaande merge-uitvoer wordt geweigerd.
Samenvoegen voegt bestaande waypointacties samen en hernummert verwijzingen.
Het garandeert geen correcte camera-instelling bij hervatten tussen twee
bestaande gimbalacties. Een geslaagde import of XML-controle is daarvoor geen
praktijkvalidatie. Controleer op een korte testmissie ook expliciet onderbreken,
hervatten, gimbalhoek en de eerste opgenomen beelden.

## Bekende werkpunten uit de praktijkevaluatie

De evaluatie van de ZOL-opnames leverde onderstaande ontwikkel- en operationele
werkpunten op. Dit is een actielijst; de punten zijn nog niet allemaal uitgevoerd.

- **Gimbal-tilt bij samengevoegde Mavic 3T-missies — hoge prioriteit.** Na hervatten
  na een batterijwissel was de camerahoek aanvankelijk verkeerd en werd die rond
  het begin van een volgende oorspronkelijke missie weer correct. Bestaande
  gimbalacties worden gekopieerd, maar een expliciete tiltactie is mogelijk niet
  op ieder waypoint aanwezig. Onderzoek bron- en merge-WPML rond missiegrenzen
  en hervatpunten. Bepaal vervolgens of expliciete acties per waypoint of per
  geschikt hervatpunt nodig zijn, en valideer dit met een onderbreek-/hervattest.
  De oorzaak is nog een hypothese; een oplossing is nog niet geïmplementeerd.
- **Variatie in camerahoeken voor 3D — hoge prioriteit.** Ondersteuning voor
  camerahoeken per waypoint verder uitwerken en opnames met meer variatie in
  schuine (oblique), lagere en perimeterbeelden testen.
- **Missievisualisatie — eerste stap uitgevoerd.** Missiepolygonen met buffer
  zijn beschikbaar. Werk leesbare overzichtskaarten en gedetailleerde
  waypointkaarten verder uit voor gebruik op het terrein.
- **Dronekeuze en haalbaarheid — hoge prioriteit.** Per zone vooraf het platform,
  de operationele omgeving, batterijcapaciteit, missieduur en verwachte
  batterijwissels toetsen.
- **Energiebeheer — middenprioriteit.** Een laadstrategie voor dronebatterijen
  én controllers opnemen, met een powerstation voor lange opnamedagen.
- **Mini 4 Pro-missiewissels — middenprioriteit.** Een beknopte stappenkaart
  maken voor afsluiten, wisselen en starten van opeenvolgende missies.
- **Video voor 3D-reconstructie — middenprioriteit.** Video als overgang tussen
  grond- en dronebeelden testen en geëxtraheerde frames vergelijken met foto's.
- **RTK — lage tot middenprioriteit.** De behoefte vooraf bepalen vanuit de
  gewenste nauwkeurigheid en het eindproduct.
- **Fallback behouden.** Een alternatieve workflow beschikbaar houden zolang
  samenvoegen en hervatten nog verder worden gevalideerd.

## Problemen oplossen en bijdragen

- **`ModuleNotFoundError`:** controleer met `python -c "import sys; print(sys.executable)"`
  of je de juiste omgeving gebruikt. Selecteer diezelfde interpreter in je IDE.
- **`gdal_rasterize` niet gevonden:** gebruik de conda-installatieroute of laat
  `--raster-output` weg. Alleen `requirements.txt` installeren is niet voldoende.
- **Geen footprintlaag:** controleer fotoacties, hoogte, koers en gimbalhoek;
  gebruik de foto-aanname alleen voor een bewuste simulatie.
- **Geen bruikbare waypoints:** controleer of de KMZ daadwerkelijk een ondersteund
  DJI-WPML-bestand bevat. Het script meldt fouten per invoerbestand en kan de
  overige bestanden wel verwerken; lees dus ook de waarschuwingen.
- **Conversie duurt lang:** begin met één missie en `--no-vector-overlap`.
- **DLL- of installatieproblemen:** maak een schone omgeving volgens één van de
  installatieroutes in plaats van pakketten tussen omgevingen te mengen.

De bestaande mergetests gebruiken bestanden in
`data/ZOL_zone_1_2026-09-24` en zijn dus niet onafhankelijk van die testdataset:

```text
python -m unittest discover -s . -p test_merge_kmz.py -v
```

Tests controleren bestandsconversie en actiebehoud; ze controleren geen drone,
firmwaregedrag of correcte tilt na hervatten. Vermeld bij een bugmelding het
commando, Python- en pakketversies, de foutmelding en een deelbare minimale
invoer. Vermeld voor import-/vluchtproblemen ook drone, app en firmwareversie.
