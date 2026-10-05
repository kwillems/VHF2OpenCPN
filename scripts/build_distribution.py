#!/usr/bin/env python3
from pathlib import Path
from datetime import datetime, timezone
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
LAYERS = ROOT / "layers"
ICONS = ROOT / "UserIcons"
PACKAGES = ROOT / "packages"
CATALOG = ROOT / "catalog"
RELEASES = ROOT / "releases"
BASE = "https://raw.githubusercontent.com/kwillems/VHF2OpenCPN/main"
PROJECT_URL = "https://github.com/kwillems/VHF2OpenCPN"
VERSION = "1.0.0"

PACKAGES.mkdir(exist_ok=True)
CATALOG.mkdir(exist_ok=True)
RELEASES.mkdir(exist_ok=True)

def make_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for src, arc in entries:
            if not src.exists():
                raise SystemExit(f"Ontbrekend bestand: {src}")
            zf.write(src, arc)


def make_release_zip(path, vhf_gpx, rws_gpx):
    icons = sorted(ICONS.glob("*.png"))
    if not icons:
        raise SystemExit(f"Geen PNG-iconen gevonden in: {ICONS}")

    top = f"VHF2OpenCPN-v{VERSION}"

    readme = f"""VHF2OpenCPN {VERSION}
===================

Deze ZIP bevat de twee VHF2OpenCPN-kaartlagen en de bijbehorende
UserIcons voor OpenCPN.

INHOUD

layers/
    VHFinfo_Nederland.gpx
    RWS_Marifoonborden.gpx

UserIcons/
    De bij de kaartlagen behorende VHF-iconen.

BELANGRIJK

De map UserIcons is een verplicht onderdeel van de installatie.
Zonder deze iconen worden de VHF-symbolen in OpenCPN niet correct
weergegeven.

Na installatie van nieuwe of gewijzigde UserIcons moet OpenCPN
opnieuw worden gestart.

Voor volledige installatie-instructies en projectinformatie:
{PROJECT_URL}
"""

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(vhf_gpx, f"{top}/layers/{vhf_gpx.name}")
        zf.write(rws_gpx, f"{top}/layers/{rws_gpx.name}")

        for icon in icons:
            zf.write(icon, f"{top}/UserIcons/{icon.name}")

        zf.writestr(f"{top}/README.txt", readme)

def main():
    vhf_gpx = LAYERS / "VHFinfo_Nederland.gpx"
    rws_gpx = LAYERS / "RWS_Marifoonborden.gpx"

    vhf_zip = PACKAGES / "VHFinfo_Nederland.zip"
    icons_zip = PACKAGES / "VHF2OpenCPN_UserIcons.zip"
    rws_zip = PACKAGES / "RWS_Marifoonborden.zip"

    make_zip(vhf_zip, [(vhf_gpx, "opencpn/layers/VHFinfo_Nederland.gpx")])
    make_zip(rws_zip, [(rws_gpx, "opencpn/layers/RWS_Marifoonborden.gpx")])
    make_zip(
        icons_zip,
        [(p, f"opencpn/UserIcons/{p.name}") for p in sorted(ICONS.glob("*.png"))]
    )

    release_zip = RELEASES / f"VHF2OpenCPN-v{VERSION}.zip"
    make_release_zip(release_zip, vhf_gpx, rws_gpx)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    root = ET.Element("RncProductCatalogChartCatalogs")
    header = ET.SubElement(root, "Header")
    for tag, value in (
        ("title", "VHF2OpenCPN - VHF-lagen voor Nederland"),
        ("date_created", now.strftime("%Y-%m-%d")),
        ("time_created", now.strftime("%H:%M:%S")),
        ("date_valid", now.strftime("%Y-%m-%d")),
        ("time_valid", now.strftime("%H:%M:%S")),
        ("dt_valid", iso),
        ("ref_spec", "VHF2OpenCPN"),
        ("ref_spec_vers", "1.0"),
        ("s62AgencyCode", "0"),
    ):
        ET.SubElement(header, tag).text = value

    entries = (
        ("1", "VHFinfo Nederland", vhf_zip),
        ("2", "UserIcons voor VHF2OpenCPN", icons_zip),
        ("3", "Rijkswaterstaat marifoonborden", rws_zip),
    )

    for number, title, pkg in entries:
        chart = ET.SubElement(root, "chart")
        ET.SubElement(chart, "number").text = number
        ET.SubElement(chart, "title").text = title
        ET.SubElement(chart, "format").text = "Sailing Chart, International Chart"
        ET.SubElement(chart, "zipfile_location").text = f"{BASE}/packages/{pkg.name}"
        ET.SubElement(chart, "zipfile_datetime_iso8601").text = iso
        ET.SubElement(chart, "target_filename").text = pkg.name

    ET.indent(root, space="  ")
    out = CATALOG / "VHF2OpenCPN.xml"
    ET.ElementTree(root).write(out, encoding="utf-8", xml_declaration=True)

    print("Gereed:")
    for p in (vhf_zip, icons_zip, rws_zip, out, release_zip):
        print(" ", p.relative_to(ROOT))

if __name__ == "__main__":
    main()
