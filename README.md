# VHF2OpenCPN

VHF2OpenCPN maakt VHF-gerelateerde informatie voor Nederland geschikt voor gebruik als lagen in OpenCPN.

Het project bevat momenteel twee bronnen:

- **VHFinfo**: VHF-gebieden en locaties uit de Nederlandse VHFinfo-dataset.
- **Rijkswaterstaat**: relevante scheepvaartverkeerstekens voor marifoongebruik (B.11.a, B.11.b en E.23).

De gegenereerde GPX-bestanden staan in `layers/`. De bijbehorende OpenCPN-iconen staan in `UserIcons/`.

## Structuur

```text
VHF2OpenCPN/
├── README.md
├── .gitignore
├── scripts/
│   ├── update_vhfinfo.py
│   └── update_rws_vhf.py
├── layers/
│   ├── VHFinfo-Nederland.gpx
│   └── RWS_VHF.gpx
├── UserIcons/
│   └── ...
├── packages/
└── catalog/
```

`packages/` is gereserveerd voor downloadbare ZIP-pakketten voor OpenCPN. `catalog/` is gereserveerd voor het XML-catalogusbestand waarmee die pakketten later vanuit OpenCPN kunnen worden aangeboden.

## Gebruik in OpenCPN

1. Kopieer de benodigde PNG-bestanden uit `UserIcons/` naar de OpenCPN-map `UserIcons`.
2. Importeer `layers/VHFinfo-Nederland.gpx` en/of `layers/RWS_VHF.gpx` in OpenCPN als laag.

De precieze locatie van de OpenCPN-gebruikersmap verschilt per besturingssysteem en installatie.

## Lagen bijwerken

Voor de scripts is alleen Python 3 nodig; er zijn geen externe Python-modules vereist.

Vanuit de hoofdmap van het project:

```bash
python3 scripts/update_vhfinfo.py
python3 scripts/update_rws_vhf.py
```

Beide scripts schrijven standaard naar `layers/`. De scripts zijn niet afhankelijk van de naam van de hoofdmap: de repository mag lokaal dus ook anders heten.

### VHFinfo

`update_vhfinfo.py` downloadt standaard de Nederlandse dataset van het VHFinfo-project en zet deze om naar een OpenCPN-compatibel GPX-bestand.

Bron:

- https://github.com/htool/vhfinfo
- https://raw.githubusercontent.com/htool/vhfinfo/main/data/NLD.json

### Rijkswaterstaat

`update_rws_vhf.py` haalt scheepvaartverkeerstekens op via de WFS-service van Rijkswaterstaat. Het script probeert eerst server-side ruim te filteren op B.11.a, B.11.b en E.23 en controleert de resultaten daarna lokaal. Bij een onbetrouwbaar resultaat valt het terug op de volledige dataset.

Bronservice:

- https://geo.rijkswaterstaat.nl/services/ogc/gdr/geografische_areaalregistratie/ows

## Distributie via OpenCPN

De mappen `packages/` en `catalog/` zijn voorbereid voor een volgende stap:

- ZIP-bestanden met de benodigde lagen en iconen in `packages/`;
- een XML-catalogus in `catalog/` die naar de GitHub-downloads verwijst.

Deze bestanden worden pas toegevoegd zodra de definitieve OpenCPN-pakketstructuur en GitHub-download-URL's zijn vastgesteld.

## Disclaimer

Dit is een onafhankelijk project. Het is niet verbonden aan of uitgegeven door VHFinfo, Rijkswaterstaat of OpenCPN. Gebruik de gegevens als aanvullende informatie en niet als vervanging voor officiële nautische publicaties, actuele verkeersinformatie of marifoonprocedures.
