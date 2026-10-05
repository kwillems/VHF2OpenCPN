# VHF2OpenCPN

VHF2OpenCPN maakt VHF-gerelateerde informatie voor Nederland beschikbaar als lagen in OpenCPN.

Het project combineert momenteel twee gegevensbronnen:

- **VHFinfo Nederland** – VHF-gebieden en locaties uit de Nederlandse VHFinfo-dataset.
- **Rijkswaterstaat marifoonborden** – relevante scheepvaartverkeerstekens voor marifoongebruik, waaronder B.11.a, B.11.b en E.23.

De lagen kunnen rechtstreeks vanuit OpenCPN worden geïnstalleerd en bijgewerkt via de **Kaartdownloader**. De benodigde UserIcons worden daarbij als apart pakket meegeleverd.

## Installeren in OpenCPN

Voeg in OpenCPN bij de **Kaartdownloader** deze catalogus-URL toe:

```text
https://raw.githubusercontent.com/kwillems/VHF2OpenCPN/main/catalog/VHF2OpenCPN.xml
```

Gebruik als installatielocatie de map **boven** de OpenCPN-map, zodat de pakketten hun interne `opencpn/...`-structuur op de juiste plaats kunnen uitpakken.

De catalogus bevat drie downloads:

1. **VHFinfo Nederland**
2. **UserIcons voor VHF2OpenCPN**
3. **Rijkswaterstaat marifoonborden**

Installeer alle drie wanneer je beide lagen met de juiste iconen wilt gebruiken.

## Bestanden

```text
VHF2OpenCPN/
├── README.md
├── .gitignore
├── scripts/
│   ├── update_vhfinfo.py
│   ├── update_rws_vhf.py
│   └── build_distribution.py
├── layers/
│   ├── VHFinfo_Nederland.gpx
│   └── RWS_Marifoonborden.gpx
├── UserIcons/
│   └── ...
├── packages/
│   ├── VHFinfo_Nederland.zip
│   ├── VHF2OpenCPN_UserIcons.zip
│   └── RWS_Marifoonborden.zip
└── catalog/
    └── VHF2OpenCPN.xml
```

## Hoe de OpenCPN-pakketten zijn opgebouwd

De ZIP-bestanden volgen dezelfde aanpak als andere OpenCPN-downloadpakketten: elk intern pad begint met `opencpn/`.

Voorbeeld:

```text
VHFinfo_Nederland.zip
└── opencpn/
    └── layers/
        └── VHFinfo_Nederland.gpx
```

```text
VHF2OpenCPN_UserIcons.zip
└── opencpn/
    └── UserIcons/
        └── ...
```

```text
RWS_Marifoonborden.zip
└── opencpn/
    └── layers/
        └── RWS_Marifoonborden.gpx
```

De XML-catalogus gebruikt per pakket `target_filename`, zodat OpenCPN het downloadpakket correct verwerkt.

## Gegevens bijwerken

Voor de scripts is alleen **Python 3** nodig. Er zijn geen externe Python-modules vereist.

Voer vanuit de hoofdmap uit:

```bash
python3 scripts/update_vhfinfo.py
python3 scripts/update_rws_vhf.py
```

De scripts schrijven standaard naar:

```text
layers/VHFinfo_Nederland.gpx
layers/RWS_Marifoonborden.gpx
```

De scripts bepalen de projectmap aan de hand van hun eigen locatie en zijn dus niet afhankelijk van de naam van de lokale repositorymap.

## Distributiepakketten opnieuw bouwen

Nadat een of beide GPX-bestanden zijn bijgewerkt:

```bash
python3 scripts/build_distribution.py
```

Dit script maakt opnieuw:

```text
packages/VHFinfo_Nederland.zip
packages/VHF2OpenCPN_UserIcons.zip
packages/RWS_Marifoonborden.zip
catalog/VHF2OpenCPN.xml
```

Daarbij worden de datum/tijd in de catalogus en de package-URL's opnieuw vastgelegd.

Een volledige update kan dus bijvoorbeeld zo worden uitgevoerd:

```bash
python3 scripts/update_vhfinfo.py
python3 scripts/update_rws_vhf.py
python3 scripts/build_distribution.py
```

Daarna kunnen de gewijzigde bestanden naar GitHub worden gecommit en gepusht.

## Gegevensbronnen

### VHFinfo

`update_vhfinfo.py` downloadt de Nederlandse VHFinfo-dataset en zet deze om naar een OpenCPN-compatibel GPX-bestand.

Bron:

- https://github.com/htool/vhfinfo
- https://raw.githubusercontent.com/htool/vhfinfo/main/data/NLD.json

### Rijkswaterstaat

`update_rws_vhf.py` haalt scheepvaartverkeerstekens op via de WFS-service van Rijkswaterstaat. Het script filtert op voor dit project relevante marifoonborden, waaronder B.11.a, B.11.b en E.23, en voert aanvullende lokale controles uit.

Bronservice:

- https://geo.rijkswaterstaat.nl/services/ogc/gdr/geografische_areaalregistratie/ows

## Publiceren van een update

Na het bijwerken van de data en distributiepakketten:

```bash
git status
git add .
git commit -m "Update VHF2OpenCPN data"
git push
```

Voor een nieuwe release kan vervolgens een Git-tag worden gemaakt, bijvoorbeeld:

```bash
git tag -a v1.0.0 -m "VHF2OpenCPN v1.0.0"
git push origin v1.0.0
```

## Disclaimer

VHF2OpenCPN is een onafhankelijk project en is niet verbonden aan of uitgegeven door VHFinfo, Rijkswaterstaat of OpenCPN.

Gebruik de gegevens als aanvullende nautische informatie. Zij vervangen geen officiële nautische publicaties, actuele verkeersinformatie, lokale voorschriften of marifoonprocedures.
