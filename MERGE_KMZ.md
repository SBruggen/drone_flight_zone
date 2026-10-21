# Aerial 3D-vluchtplannen samenvoegen voor DJI Mavic 3T

## Technische conclusie

Samenvoegen is op bestandsniveau mogelijk. DJI WPML ondersteunt de Mavic 3T
en een doorlopende waypointindex die verder gaat dan 99. `merge_kmz.py` maakt
een **experimenteel importbestand** voor DJI Pilot 2. Acceptatie door jouw
Pilot 2-versie, firmware en drone moet afzonderlijk worden gecontroleerd. Bij de
ZOL-opnames bleken samenvoegen, uitvoeren en hervatten operationeel bruikbaar,
maar werd een probleem met de gimbalhoek na hervatten vastgesteld (zie hieronder).
De gedocumenteerde
indexruimte 0–65535 is geen bewijs dat Pilot 2 iedere dergelijke missiegrootte
kan importeren of uitvoeren. Het script gebruikt 65535 punten als bovengrens;
met `--max-waypoints` kun je zelf een lagere grens opleggen.

De originele exports bevatten `finishAction=goHome`: iedere afzonderlijke
missie vraagt dus na afloop een terugvlucht. Na samenvoeging is er één Folder
met één wayline, en geldt deze eindactie pas na het laatste waypoint.
Bestaande waypointstops en hoveracties blijven bestaan. Ook batterijbeheer,
verbindingsverlies en handmatig afbreken kunnen een route onderbreken.

## Gebruik

### Bekend aandachtspunt: gimbal-tilt na hervatten

Bij de ZOL-opnames stond de verticale camerahoek na hervatten na een
batterijwissel aanvankelijk verkeerd. De juiste hoek werd opnieuw ingesteld
rond het begin van een volgende oorspronkelijke missie van maximaal 99
waypoints. Dat wijst mogelijk op instellingen die alleen op de startwaypoints
van de oorspronkelijke missies aanwezig zijn; de oorzaak is nog niet bewezen.

`merge_kmz.py` kopieert bestaande `gimbalRotate`-acties, maar voegt niet op elk
waypoint een expliciete tiltactie toe. Behoud van bronacties garandeert daarom
geen correcte tilt op ieder hervatpunt. Ook een door `kmz_to_gpkg.py`
doorgegeven gimbalhoek is een afgeleide toestand, geen bewijs dat op dat
waypoint een expliciete gimbalactie staat.

Open werk: vergelijk bron- en merge-WPML bij missiegrenzen en hervatpunten,
bepaal welke expliciete gimbalacties nodig zijn en valideer een aanpassing
met een korte missie die bewust wordt onderbroken en hervat. Controleer direct
de gimbalhoek en eerste beelden. Deze oplossing is nog niet geïmplementeerd;
de bestaande regressietests testen geen hervatgedrag op de drone.

Vanuit de map `drone_flight_zone`, met Python 3.9 of nieuwer; geen extra packages:

```powershell
python merge_kmz.py data/ZOL_zone_1_2026-09-24 -o output/zone1_test.kmz --dry-run
python merge_kmz.py data/ZOL_zone_1_2026-09-24 -o output/zone1_test.kmz
```

Een map wordt niet recursief doorzocht. De volgorde is natuurlijk numeriek:
Mission_1, Mission_2, ..., Mission_10. Voor een selectie of andere volgorde:

```powershell
python merge_kmz.py data/ZOL_zone_1_2026-09-24/Mission_1.kmz data/ZOL_zone_1_2026-09-24/Mission_2.kmz -o output/zone1_twee_missies.kmz
```

Expliciete instellingen zijn bijvoorbeeld `--takeoff-height 60 --rth-height 80`
(meters ten opzichte van vertrek). Kies waarden passend bij het terrein.
Zonder deze opties wordt de vertrekhoogte gelijk aan de eerste waypointhoogte;
de RTH-hoogte wordt max(20 m, vertrekhoogte, vlieghoogte). Dit zijn
conversiestandaarden, geen beoordeling van vrije ruimte boven obstakels.

Fotoacties gebruiken standaard de groothoekcamera (`--image-format wide`).
Kies `--image-format ir` of `--image-format wide,ir` voor thermisch of beide.
Er worden geen fotoacties toegevoegd als de bron die niet bevat. Overstappen
naar de Mavic 3T verandert de camera: gelijke waypoints geven niet automatisch
gelijke beelddekking/GSD/overlap. Controleer camera-instellingen en fototempo.

Bronbestanden worden niet gewijzigd. Bestaande uitvoer en rapporten worden
niet overschreven. Kies een nieuwe uitvoernaam voor een volgende test.

## Bestandsstructuur en conversie

```text
Mavic3T_merged.kmz       (ZIP-container)
└── wpmz/
    ├── template.kml
    ├── waylines.wpml
    └── ... eventuele ongewijzigde resources
Mavic3T_merged.report.json   (naast het KMZ-bestand)
```

- Beide XML-bestanden gebruiken de DJI-namespace `http://www.dji.com/wpmz/1.0.2`.
- Droneprofiel: `droneEnumValue=77`, `droneSubEnumValue=1`; camera: `payloadEnumValue=67`, positie 0.
- De lege Aerial 3D-template wordt opgebouwd als waypointtemplate met dezelfde route.
- Waypointindices, actiegroep-ID's, actie-ID's en begin/eindverwijzingen worden hernummerd.
- Coördinaten, relatieve hoogte, snelheid, POI, bochten, gimbalacties en hoveracties blijven behouden.
- Aerial 3D gebruikt soms `parallel` voor een groep met slechts één fotoactie.
  Dat wordt `sequence`, zoals gedocumenteerd voor DJI WPML. Parallelgroepen met
  meerdere acties worden geweigerd, omdat omzetten hun gedrag kan veranderen.
- De uitvoerinstellingen uit `waylines.wpml` zijn leidend en worden ook naar
  de template gekopieerd. Bij de aanwezige bronnen wijkt de oorspronkelijke
  template daarvan af voor verbindingsverlies. In de samengevoegde bestanden
  blijft de uitvoerinstelling `executeLostAction` + `hover` behouden.
- Onbetrouwbare afstand/duurvelden met bronwaarde 0 worden weggelaten.
  Het rapport geeft een benaderde 3D-polylijnafstand, geen werkelijke vliegtijd.
- Resources behouden hun interne paden; verschillende inhoud op hetzelfde pad
  veroorzaakt een fout in plaats van stil overschrijven.

Het script ondersteunt bewust de aangetroffen Aerial 3D-exportvorm: lege
template, één uitvoerroute per bestand, dezelfde missie-instellingen, één
constante relatieve vlieghoogte en reachPoint-acties voor foto/gimbal/hover.
Rijke templates, variabele hoogten, andere hoogtereferenties of onbekende
actietypen worden geweigerd. Alle bronnen moeten hetzelfde vertrekhoogteniveau
veronderstellen; dat kan niet uit deze exports worden bewezen. Punten worden
niet verwijderd of geoptimaliseerd, ook niet wanneer ze samenvallen.

## Controleren in DJI Pilot 2

Importeer eerst de variant met twee bestaande missies in de vluchtbibliotheek
van DJI Pilot 2 en controleer of de app 198 waypoints en het Mavic 3T-profiel
toont. Controleer hoogte, POI/kijkrichting, gimbal, camera/lenskeuze, overgang
98→99 (interne index), eindactie, RTH en gedrag bij verbindingsverlies.
Importeer daarna het volledige bestand om de praktische importlimiet te testen.
Een geslaagde XML/ZIP-controle vervangt deze controllercontrole niet.

Begin uitvoering met een korte route op een geschikte testlocatie. Houd bij
lange routes rekening met een onderbreking en controleer de hervatfunctie op
jouw controller. Er is vanuit dit script geen verbinding met de drone en er
wordt geen missie gestart.

Het bestaande `kmz_to_gpkg.py` herkent nu zowel de Aerial- als de DJI-namespace:

```powershell
python kmz_to_gpkg.py output/merged/ZOL_zone_1_2026-09-24 -o output/zone1_merged_preview.gpkg --no-vector-overlap
```

## Validatie en bronnen

```powershell
python -m unittest discover -s . -p test_merge_kmz.py -v
```

Vijf regressietests controleren behoud van bronbestanden, route en acties,
hernummering, ongeldige verwijzingen, verschillende instellingen, limieten,
dry-run, overschrijfbeveiliging, parallelgroepen en resourceconflicten. Alle
vier gegenereerde KMZ-bestanden zijn opnieuw met de bestaande geodataparser
gelezen; aantallen, foto-indicatoren, hoogten en snelheden zijn gecontroleerd.
Dit is geen DJI SDK-/schema-validatie of praktijktest met firmware.

Geraadpleegd op 24 september 2026:

- [DJI WPML waylines](https://developer.dji.com/doc/cloud-api-tutorial/en/api-reference/dji-wpml/waylines-wpml.html): uitvoerroute, indices, eindactie en hoogtereferentie.
- [DJI WPML template](https://developer.dji.com/doc/cloud-api-tutorial/en/api-reference/dji-wpml/template-kml.html): waypointtemplate en globale hoogte.
- [DJI WPML common elements](https://developer.dji.com/doc/cloud-api-tutorial/en/api-reference/dji-wpml/common-element.html): acties, POI en camera-instellingen.
- [Officiële DJI-documentatie op GitHub](https://github.com/dji-sdk/Cloud-API-Doc/blob/master/docs/en/60.api-reference/00.dji-wpml/40.common-element.md): Mavic 3T drone- en camera-enumeraties.
