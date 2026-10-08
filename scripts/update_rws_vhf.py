#!/usr/bin/env python3

import json
import re
import sys
import tempfile
import urllib.request
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET


RWS_BASE_URL = (
    "https://geo.rijkswaterstaat.nl/services/ogc/gdr/"
    "geografische_areaalregistratie/ows"
)

def build_rws_url(server_filter=True):
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "OUTPUTFORMAT": "application/json",
        "TYPENAMES": "scheepvaartverkeerstekens",
    }

    if server_filter:
        # Deliberately broad filter: '%' also covers missing or different
        # punctuation/spacing, e.g. B.11.a, B11.a, B.11a, B 11 a.
        params["CQL_FILTER"] = (
            "(code_rvs LIKE 'B%11%a%') OR "
            "(code_rvs LIKE 'B%11%b%') OR "
            "(code_rvs LIKE 'E%23%')"
        )

    return RWS_BASE_URL + "?" + urllib.parse.urlencode(params)


CHUNK_SIZE = 1024 * 256  # 256 KiB

# A filtered RWS response with fewer locally recognized marifoonborden than
# this is considered suspicious and triggers a fallback to the full dataset.
MIN_EXPECTED_SERVER_RECORDS = 100


def project_root() -> Path:
    """Return the project root; this script is expected in PROJECT/scripts/."""
    return Path(__file__).resolve().parent.parent


def download_to_tempfile(url, server_filtered=False):
    if server_filtered:
        print("Alleen de relevante RWS-marifoonborden downloaden...")
        print("  Server-side filter: ruim filter op B.11.a, B.11.b en E.23")
        print("  Lokale controle   : exacte classificatie na normalisatie")
    else:
        print("Volledige Rijkswaterstaat-dataset downloaden (ongeveer 50 MB)...")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "VHF2OpenCPN/1.0"
        },
    )

    temp = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix="rws_vhf_",
        suffix=".json",
        delete=False,
    )
    temp_path = Path(temp.name)

    try:
        with temp:
            with urllib.request.urlopen(request, timeout=120) as response:
                content_length = response.headers.get("Content-Length")
                total_bytes = (
                    int(content_length)
                    if content_length and content_length.isdigit()
                    else None
                )
                downloaded = 0

                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break

                    temp.write(chunk)
                    downloaded += len(chunk)

                    downloaded_mb = downloaded / (1024 * 1024)

                    if total_bytes:
                        percentage = min(
                            100.0,
                            downloaded * 100.0 / total_bytes,
                        )
                        total_mb = total_bytes / (1024 * 1024)
                        print(
                            f"\r  Voortgang: {percentage:6.2f}%  "
                            f"({downloaded_mb:.1f} / {total_mb:.1f} MB)",
                            end="",
                            flush=True,
                        )
                    else:
                        print(
                            f"\r  Gedownload: {downloaded_mb:.1f} MB",
                            end="",
                            flush=True,
                        )

        print()
        print("Download voltooid. Tijdelijk bestand opgeslagen.")
        return temp_path

    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def get_code(feature):
    properties = feature.get("properties", {})
    return str(properties.get("code_rvs", "")).strip()


def normalize_board_code(code):
    """
    Normalize an RWS board code for robust matching.

    Examples:
      B.11.a  -> B11A
      B11.a   -> B11A
      B.11a   -> B11A
      B 11 a  -> B11A
    """
    return re.sub(r"[^A-Za-z0-9]", "", str(code or "")).upper()


def classify(code):
    normalized = normalize_board_code(code)

    if normalized.startswith("B11A"):
        return "B.11.a"
    if normalized.startswith("B11B"):
        return "B.11.b"
    if normalized.startswith("E23"):
        return "E.23"

    return "onbekend"


def is_marifoonbord(feature):
    return classify(get_code(feature)) != "onbekend"


def rd_to_wgs84(x, y):
    dx = (x - 155000.0) * 1e-5
    dy = (y - 463000.0) * 1e-5

    lat = 52.15517440 + (
        3235.65389 * dy
        - 32.58297 * dx**2
        - 0.2475 * dy**2
        - 0.84978 * dx**2 * dy
        - 0.0655 * dy**3
        - 0.01709 * dx**2 * dy**2
        - 0.00738 * dx
        + 0.0053 * dx**4
        - 0.00039 * dx**2 * dy**3
        + 0.00033 * dx**4 * dy
        - 0.00012 * dx * dy
    ) / 3600.0

    lon = 5.38720621 + (
        5260.52916 * dx
        + 105.94684 * dx * dy
        + 2.45656 * dx * dy**2
        - 0.81885 * dx**3
        + 0.05594 * dx * dy**3
        - 0.05607 * dx**3 * dy
        + 0.01199 * dy
        - 0.00256 * dx**3 * dy**2
        + 0.00128 * dx * dy**4
        + 0.00022 * dy**2
        - 0.00022 * dx**2
        + 0.00026 * dx**5
    ) / 3600.0

    return lat, lon


def normalize_channel(text):
    if text is None:
        return None
    s = str(text).strip()
    if not s or s.lower() in {"geen informatie", "niet van toepassing", "--"}:
        return None
    m = re.search(r"(?i)(?:vhf\s*)?(\d{1,2})", s)
    return f"VHF {m.group(1)}" if m else s


def channel_number(text):
    if text is None:
        return None
    s = str(text).strip()
    if not s or s.lower() in {"geen informatie", "niet van toepassing", "--"}:
        return None
    m = re.search(r"(?i)(?:vhf\s*)?(\d{1,2})", s)
    if not m:
        return None
    n = int(m.group(1))
    return n if 1 <= n <= 88 else None


def classify_board(code_rvs):
    board_type = classify(code_rvs)
    return None if board_type == "onbekend" else board_type


def icon_for(board_code, channel_no):
    if board_code == "B.11.a":
        return "vhf_b11a"

    if board_code == "B.11.b":
        return (
            f"vhf_b11b_{channel_no}"
            if channel_no is not None
            else "vhf_b11b_unknown"
        )

    if board_code == "E.23":
        return (
            f"vhf_e23_{channel_no}"
            if channel_no is not None
            else "vhf_e23_unknown"
        )

    return "circle"


def clean(props, key):
    value = props.get(key)
    if value is None:
        return None

    value = str(value).strip()

    if value in {"", "Geen informatie", "Niet van toepassing", "--", "-777", "-999"}:
        return None

    return value


def make_description(props, channel):
    lines = []

    code = clean(props, "code_rvs")
    if code:
        lines.append(code)

    if channel:
        lines.append(channel)

    obj = clean(props, "object_omschrijving")
    if obj:
        lines += ["", f"Locatie: {obj}"]

    km = props.get("kilometer_vaarweg")
    if isinstance(km, (int, float)) and km not in (-777, -999):
        lines.append(f"Vaarwegkilometer: {km:g}")

    direction = clean(props, "stroomrichting_omschrijving")
    if direction:
        lines.append(f"Stroomrichting: {direction}")

    bank = clean(props, "oeverzijde_plaatsing_code")
    if bank:
        lines.append(f"Plaatsing: {bank}")

    orientation = props.get("orientatie")
    if isinstance(orientation, (int, float)) and orientation not in (-777, -999):
        lines.append(f"Orientatie: {orientation:g}°")

    uri = clean(props, "gns_uri")
    if uri:
        lines += ["", uri]

    return "\n".join(lines)


def iter_geojson_features(path, chunk_size=1024 * 1024):
    """
    Stream the objects from the top-level GeoJSON 'features' array without
    loading the complete dataset into memory.
    """
    decoder = json.JSONDecoder()
    buffer = ""
    pos = 0
    in_features = False
    eof = False

    with path.open("r", encoding="utf-8") as f:
        while True:
            # Refill the buffer when needed.
            if pos >= len(buffer) and not eof:
                chunk = f.read(chunk_size)
                if chunk:
                    buffer = chunk
                    pos = 0
                else:
                    eof = True

            if not in_features:
                # Search for the "features" key. Keep a tail between chunks so
                # the key may safely span a chunk boundary.
                while True:
                    idx = buffer.find('"features"', pos)
                    if idx != -1:
                        pos = idx + len('"features"')
                        break

                    if eof:
                        raise ValueError(
                            "Geen 'features'-array gevonden in de RWS GeoJSON."
                        )

                    tail = buffer[max(0, len(buffer) - 32):]
                    chunk = f.read(chunk_size)
                    if chunk:
                        buffer = tail + chunk
                        pos = 0
                    else:
                        eof = True
                        buffer = tail
                        pos = 0

                # Find the opening '[' of the features array.
                while True:
                    bracket = buffer.find("[", pos)
                    if bracket != -1:
                        pos = bracket + 1
                        in_features = True
                        break

                    if eof:
                        raise ValueError(
                            "Ongeldige GeoJSON: features-array begint niet."
                        )

                    chunk = f.read(chunk_size)
                    if chunk:
                        buffer = buffer[pos:] + chunk
                        pos = 0
                    else:
                        eof = True

            # Parse feature objects one at a time.
            while in_features:
                # Skip whitespace and commas.
                while True:
                    while pos < len(buffer) and buffer[pos] in " \t\r\n,":
                        pos += 1

                    if pos < len(buffer):
                        break

                    if eof:
                        raise ValueError(
                            "Onverwacht einde van bestand in features-array."
                        )

                    chunk = f.read(chunk_size)
                    if chunk:
                        buffer = chunk
                        pos = 0
                    else:
                        eof = True

                if buffer[pos] == "]":
                    return

                try:
                    feature, new_pos = decoder.raw_decode(buffer, pos)
                    pos = new_pos
                    yield feature
                except json.JSONDecodeError:
                    # The object probably crosses a chunk boundary. Preserve the
                    # unparsed tail and append more data until raw_decode works.
                    if eof:
                        raise ValueError(
                            "Ongeldige JSON in een feature-object."
                        )

                    buffer = buffer[pos:]
                    pos = 0
                    chunk = f.read(chunk_size)
                    if chunk:
                        buffer += chunk
                    else:
                        eof = True


def filter_features_streaming(temp_path):
    filtered = []
    original_count = 0
    rejected_count = 0
    counts = Counter()

    for feature in iter_geojson_features(temp_path):
        original_count += 1

        if is_marifoonbord(feature):
            filtered.append(feature)
            counts[classify(get_code(feature))] += 1
        else:
            rejected_count += 1

        if original_count % 1000 == 0:
            print(
                f"\r  Verwerkt: {original_count} records"
                f"  | marifoonborden: {len(filtered)}",
                end="",
                flush=True,
            )

    if original_count:
        print(
            f"\r  Verwerkt: {original_count} records"
            f"  | marifoonborden: {len(filtered)}"
        )

    # Only the small filtered set remains in memory.
    result = {
        "type": "FeatureCollection",
        "features": filtered,
    }

    return result, original_count, counts, rejected_count


def convert_to_gpx(data, output_path):
    root = ET.Element(
        "gpx",
        {
            "version": "1.1",
            "creator": "update_rws_vhf.py",
            "xmlns": "http://www.topografix.com/GPX/1/1",
            "xmlns:opencpn": "http://www.opencpn.org",
        },
    )

    metadata = ET.SubElement(root, "metadata")
    ET.SubElement(metadata, "name").text = "Rijkswaterstaat marifoonborden"
    ET.SubElement(metadata, "desc").text = (
        "Rijkswaterstaat marifoonborden, automatisch gegenereerd "
        "uit de RWS WFS-service"
    )
    ET.SubElement(metadata, "time").text = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    counts = {"B.11.a": 0, "B.11.b": 0, "E.23": 0}
    no_channel = {"B.11.b": 0, "E.23": 0}
    skipped = 0

    features = data.get("features", [])
    total = len(features)

    print("OpenCPN-layer genereren...")

    for index, feature in enumerate(features, start=1):
        props = feature.get("properties", {})
        geom = feature.get("geometry") or {}
        board_code = classify_board(props.get("code_rvs"))
        coords = geom.get("coordinates")

        valid = (
            board_code
            and geom.get("type") == "Point"
            and isinstance(coords, list)
            and len(coords) >= 2
        )

        if valid:
            try:
                lat, lon = rd_to_wgs84(float(coords[0]), float(coords[1]))
            except (TypeError, ValueError, OverflowError):
                valid = False

        if not valid:
            skipped += 1
        else:
            channel = normalize_channel(props.get("tekenopschrift"))
            channel_no = channel_number(props.get("tekenopschrift"))
            symbol = icon_for(board_code, channel_no)

            if channel_no is None and board_code in no_channel:
                no_channel[board_code] += 1

            wpt = ET.SubElement(
                root,
                "wpt",
                {
                    "lat": f"{lat:.7f}",
                    "lon": f"{lon:.7f}",
                },
            )

            name = board_code + (f" - {channel}" if channel else "")
            ET.SubElement(wpt, "name").text = name
            ET.SubElement(wpt, "desc").text = make_description(props, channel)
            ET.SubElement(wpt, "sym").text = symbol
            ET.SubElement(wpt, "type").text = "RWS VHF-bord"

            extensions = ET.SubElement(wpt, "extensions")
            ET.SubElement(
                extensions,
                "opencpn:scale_min_max",
                {
                    "UseScale": "true",
                    "ScaleMin": "200000",
                    "ScaleMax": "0",
                },
            )

            counts[board_code] += 1

        # Update progress independently of whether the record was usable.
        if total and (index == total or index % 25 == 0):
            percentage = index * 100.0 / total
            print(
                f"\r  Voortgang: {percentage:6.2f}%  "
                f"({index} / {total} records)",
                end="",
                flush=True,
            )

    if total:
        print()

    tree = ET.ElementTree(root)

    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass

    # Write to a temporary file in the same directory. Only after the complete
    # GPX has been written successfully do we replace the existing layer.
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp = tempfile.NamedTemporaryFile(
        mode="wb",
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
        delete=False,
    )
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
        tmp_path.replace(output_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    return counts, no_channel, skipped


def main():
    root = project_root()
    gpx_output = root / "layers" / "RWS_Marifoonborden.gpx"
    temp_path = None

    print("=== RWS marifoonborden bijwerken ===")
    print()

    try:
        filtered_on_server = True
        server_failure = None

        # First try the small server-filtered response. Download errors,
        # invalid GeoJSON and suspiciously small results all trigger fallback.
        try:
            temp_path = download_to_tempfile(
                build_rws_url(server_filter=True),
                server_filtered=True,
            )

            print()
            print("Gedownloade marifoonborden controleren...")

            (
                filtered_data,
                original_count,
                json_counts,
                rejected_count,
            ) = filter_features_streaming(temp_path)

            recognized_count = len(filtered_data.get("features", []))

            if recognized_count < MIN_EXPECTED_SERVER_RECORDS:
                raise ValueError(
                    "serverfilter leverde slechts "
                    f"{recognized_count} lokaal herkende marifoonborden op "
                    f"(minimumcontrole: {MIN_EXPECTED_SERVER_RECORDS})"
                )

        except Exception as exc:
            server_failure = exc

        if server_failure is not None:
            print()
            print(
                "Server-side filtering gaf geen betrouwbare dataset:"
            )
            print(f"  {server_failure}")
            print("Terugvallen op de volledige RWS-dataset...")

            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
                temp_path = None

            filtered_on_server = False
            temp_path = download_to_tempfile(
                build_rws_url(server_filter=False),
                server_filtered=False,
            )

            print()
            print("Marifoonborden lokaal selecteren...")

            (
                filtered_data,
                original_count,
                json_counts,
                rejected_count,
            ) = filter_features_streaming(temp_path)

        temp_size_mb = temp_path.stat().st_size / (1024 * 1024)
        recognized_count = len(filtered_data.get("features", []))

        print(f"  Ontvangen records : {original_count} records")
        print(f"  Marifoonborden    : {recognized_count} records")
        print(f"  Niet herkend      : {rejected_count} records")
        print(f"  B.11.a            : {json_counts['B.11.a']}")
        print(f"  B.11.b            : {json_counts['B.11.b']}")
        print(f"  E.23              : {json_counts['E.23']}")
        print(f"  Downloadgrootte   : {temp_size_mb:.2f} MB")
        print(
            "  Filtering         : "
            + ("op de RWS-server" if filtered_on_server else "lokaal")
        )

        print()

        gpx_counts, no_channel, skipped = convert_to_gpx(
            filtered_data,
            gpx_output,
        )

    except Exception as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        sys.exit(1)

    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
                print()
                print("Tijdelijk downloadbestand verwijderd.")
            except Exception as exc:
                print(
                    f"Waarschuwing: tijdelijk bestand kon niet worden "
                    f"verwijderd: {exc}",
                    file=sys.stderr,
                )

    gpx_total = sum(gpx_counts.values())

    print()
    print("Klaar.")
    print(f"GPX-punten  : {gpx_total}")
    print(f"Overgeslagen: {skipped}")
    print(f"B.11.a      : {gpx_counts['B.11.a']}  (algemeen marifoonplichtbord)")
    print(
        f"B.11.b      : {gpx_counts['B.11.b']}  "
        f"(zonder kanaal: {no_channel['B.11.b']})"
    )
    print(
        f"E.23        : {gpx_counts['E.23']}  "
        f"(zonder kanaal: {no_channel['E.23']})"
    )
    print(f"GPX         : {gpx_output.resolve()}")


if __name__ == "__main__":
    main()
