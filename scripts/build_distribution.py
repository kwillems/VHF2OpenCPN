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
BASE_URL = "https://raw.githubusercontent.com/kwillems/VHF2OpenCPN/main"
PACKAGES.mkdir(exist_ok=True)
CATALOG.mkdir(exist_ok=True)

def add(zf, path, arcname):
    if not path.exists():
        raise SystemExit(f"Ontbrekend bestand: {path}")
    zf.write(path, arcname)

def package_vhfinfo():
    out = PACKAGES / "VHFinfo_Nederland.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        add(zf, LAYERS / "VHFinfo_Nederland.gpx", "layers/VHFinfo_Nederland.gpx")
        if (ICONS / "vhfinfo.png").exists(): add(zf, ICONS / "vhfinfo.png", "UserIcons/vhfinfo.png")
        for p in sorted(ICONS.glob("vhf_unknown_*.png")): add(zf, p, f"UserIcons/{p.name}")
    return out

def package_rws():
    out = PACKAGES / "RWS_Marifoonborden.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        add(zf, LAYERS / "RWS_Marifoonborden.gpx", "layers/RWS_Marifoonborden.gpx")
        for name in ("vhf_b11a.png", "vhf_b11b_unknown.png", "vhf_e23_unknown.png"):
            p = ICONS / name
            if p.exists(): add(zf, p, f"UserIcons/{p.name}")
        for pattern in ("vhf_b11b_*.png", "vhf_e23_*.png"):
            for p in sorted(ICONS.glob(pattern)):
                if not p.name.endswith("_unknown.png"): add(zf, p, f"UserIcons/{p.name}")
    return out

def make_catalog(vhf, rws):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    date = now.strftime("%Y-%m-%d"); tm = now.strftime("%H:%M:%S"); compact = now.strftime("%Y%m%d_%H%M%S"); iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    root = ET.Element("RncProductCatalogChartCatalogs")
    header = ET.SubElement(root, "Header")
    for tag, value in (("title","VHF2OpenCPN"),("date_created",date),("time_created",tm),("date_valid",date),("time_valid",tm),("dt_valid",iso),("ref_spec","Subset of NOAA RNC Product Catalog Technical Specifications"),("ref_spec_vers","1.0"),("s62AgencyCode","0")):
        ET.SubElement(header, tag).text = value
    for number, title, pkg, target in (("VHFinfo_Nederland","VHFinfo Nederland",vhf,"layers/VHFinfo_Nederland.gpx"),("RWS_Marifoonborden","Rijkswaterstaat marifoonborden",rws,"layers/RWS_Marifoonborden.gpx")):
        chart = ET.SubElement(root, "chart")
        for tag, value in (("number",number),("title",title),("format","OpenCPN GPX layer + UserIcons"),("zipfile_location",f"{BASE_URL}/packages/{pkg.name}"),("zipfile_datetime",compact),("zipfile_datetime_iso8601",iso),("zipfile_size",str(pkg.stat().st_size)),("target_filename",target),("reference_file",target)):
            ET.SubElement(chart, tag).text = value
    ET.indent(root, space="  ")
    out = CATALOG / "VHF2OpenCPN.xml"
    ET.ElementTree(root).write(out, encoding="utf-8", xml_declaration=True)
    return out

def main():
    vhf = package_vhfinfo(); rws = package_rws(); cat = make_catalog(vhf, rws)
    print(f"Gemaakt: {vhf.relative_to(ROOT)}")
    print(f"Gemaakt: {rws.relative_to(ROOT)}")
    print(f"Gemaakt: {cat.relative_to(ROOT)}")
if __name__ == "__main__": main()
