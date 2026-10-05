#!/usr/bin/env python3
"""
Convert VHFinfo GeoJSON to an OpenCPN-compatible GPX layer.

By default the current Netherlands dataset is downloaded from:
https://raw.githubusercontent.com/htool/vhfinfo/main/data/NLD.json

Examples:
  python3 scripts/update_vhfinfo.py
  python3 scripts/update_vhfinfo.py --input NLD.json
  python3 scripts/update_vhfinfo.py --types vts area territorial lock bridge
  python3 scripts/update_vhfinfo.py --no-labels

The GPX contains:
- tracks for GeoJSON polygon/line boundaries;
- marks at representative points using gray per-channel OpenCPN icons;
- VHFinfo properties in each mark description.

No third-party Python modules are required.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Optional


def project_root() -> Path:
    """Return the project root; this script is expected in PROJECT/scripts/."""
    return Path(__file__).resolve().parent.parent


def project_layers_dir() -> Path:
    """Return the project layers directory and create it when necessary."""
    layers_dir = project_root() / "layers"
    layers_dir.mkdir(parents=True, exist_ok=True)
    return layers_dir

DEFAULT_URL = "https://raw.githubusercontent.com/htool/vhfinfo/main/data/NLD.json"
DEFAULT_OUTPUT = "VHFinfo_Nederland.gpx"

GPX_NS = "http://www.topografix.com/GPX/1/1"
GPXX_NS = "http://www.garmin.com/xmlschemas/GpxExtensions/v3"
OPENCPN_NS = "http://www.opencpn.org"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

ET.register_namespace("", GPX_NS)
ET.register_namespace("gpxx", GPXX_NS)
ET.register_namespace("opencpn", OPENCPN_NS)
ET.register_namespace("xsi", XSI_NS)

# OpenCPN/Garmin named colors. These are deliberately chosen from the
# Garmin GPX DisplayColor enumeration understood by OpenCPN.
TYPE_COLORS = {
    "vts": "Red",
    "vts radar support": "Magenta",
    "area": "Yellow",
    "territorial": "Magenta",
    "lock": "Blue",
    "bridge": "Cyan",
    "marina": "Green",
    "information": "DarkGray",
}


# OpenCPN track presentation. Width is in pixels. Large operational areas are
# intentionally more prominent than point-like objects such as locks/bridges.
TYPE_WIDTHS = {
    "vts": 7,
    "vts radar support": 7,
    "area": 7,
    "territorial": 7,
    "lock": 5,
    "bridge": 5,
    "marina": 4,
    "information": 4,
}

def q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"

def load_geojson(
    input_path: Optional[Path],
    url: str,
    retries: int = 1,
) -> dict[str, Any]:
    if input_path:
        print(f"Local VHFinfo dataset lezen: {input_path}")
        with input_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    attempts = retries + 1

    for attempt in range(1, attempts + 1):
        if attempt == 1:
            print("VHFinfo Nederland downloaden...")
        else:
            print("VHFinfo Nederland downloaden (tweede poging)...")

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "VHF2OpenCPN/1.0"},
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)

        except (
            urllib.error.URLError,
            TimeoutError,
            json.JSONDecodeError,
        ) as exc:
            if attempt >= attempts:
                raise

            print(f"Download mislukt: {exc}")
            print("Opnieuw proberen...")
            time.sleep(1)

    raise RuntimeError("VHFinfo dataset kon niet worden geladen.")


def normalize_type(value: Any) -> str:
    return str(value or "").strip().lower()

def channel_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()

def merged_generic_properties(props: dict[str, Any]) -> dict[str, Any]:
    # Current VHFinfo data may have some fields at top level and others
    # inside vhfdata.generic. Keep both.
    merged: dict[str, Any] = {}
    vhfdata = props.get("vhfdata")
    if isinstance(vhfdata, dict):
        generic = vhfdata.get("generic")
        if isinstance(generic, dict):
            merged.update(generic)
    for key in ("mode", "note", "url", "phone"):
        if props.get(key) not in (None, ""):
            merged[key] = props[key]
    return merged

def description(props: dict[str, Any]) -> str:
    generic = merged_generic_properties(props)
    lines: list[str] = []

    callname = str(props.get("callname") or "").strip()
    feature_type = str(props.get("type") or "").strip()
    channel = channel_text(props.get("channel"))
    mode = str(generic.get("mode") or "").strip()
    note = str(generic.get("note") or "").strip()
    phone = str(generic.get("phone") or props.get("phone") or "").strip()
    url = str(generic.get("url") or props.get("url") or "").strip()

    if callname:
        lines.append(f"Oproepnaam: {callname}")
    if feature_type:
        lines.append(f"Type: {feature_type}")
    if channel:
        lines.append(f"VHF-kanaal: {channel}")
    if mode:
        lines.append(f"Gebruik: {mode}")
    if note:
        lines.append(f"Opmerking: {note}")
    if phone and phone != "+":
        lines.append(f"Telefoon: {phone}")
    if url and url not in ("https://", "http://"):
        lines.append(f"Bron/info: {url}")

    return "\n".join(lines)

def polygon_centroid(ring: list[list[float]]) -> tuple[float, float]:
    """Return an approximate planar centroid as (lon, lat)."""
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    if not pts:
        return (0.0, 0.0)
    if len(pts) < 3:
        return (
            sum(float(p[0]) for p in pts) / len(pts),
            sum(float(p[1]) for p in pts) / len(pts),
        )

    twice_area = 0.0
    cx = 0.0
    cy = 0.0
    for i, p1 in enumerate(pts):
        p2 = pts[(i + 1) % len(pts)]
        x1, y1 = float(p1[0]), float(p1[1])
        x2, y2 = float(p2[0]), float(p2[1])
        cross = x1 * y2 - x2 * y1
        twice_area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross

    if abs(twice_area) < 1e-12:
        return (
            sum(float(p[0]) for p in pts) / len(pts),
            sum(float(p[1]) for p in pts) / len(pts),
        )

    factor = 1.0 / (3.0 * twice_area)
    return (cx * factor, cy * factor)


def point_in_ring(point: tuple[float, float], ring: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test for one ring."""
    x, y = point
    inside = False
    if len(ring) < 3:
        return False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = float(ring[i][0]), float(ring[i][1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-15) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_polygon(point: tuple[float, float], polygon: list[list[list[float]]]) -> bool:
    """Return True when point is in outer ring and not in a hole."""
    if not polygon or not polygon[0] or not point_in_ring(point, polygon[0]):
        return False
    for hole in polygon[1:]:
        if hole and point_in_ring(point, hole):
            return False
    return True


def bbox_of_ring(ring: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in ring]
    ys = [float(p[1]) for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def safe_point_in_polygon(polygon: list[list[list[float]]]) -> Optional[tuple[float, float]]:
    """
    Pick a label point guaranteed to be inside a polygon when possible.

    A geometric centroid may lie outside a strongly concave polygon, which is
    exactly what happens for some large VHFinfo water areas. We therefore try
    the centroid first, then scan a grid for an interior point furthest from
    the bounding-box edges.
    """
    if not polygon or not polygon[0]:
        return None
    outer = polygon[0]
    centroid = polygon_centroid(outer)
    if point_in_polygon(centroid, polygon):
        return centroid

    minx, miny, maxx, maxy = bbox_of_ring(outer)
    best = None
    best_score = -1.0
    steps = 20
    for iy in range(1, steps):
        y = miny + (maxy - miny) * iy / steps
        for ix in range(1, steps):
            x = minx + (maxx - minx) * ix / steps
            pt = (x, y)
            if not point_in_polygon(pt, polygon):
                continue
            score = min(x - minx, maxx - x, y - miny, maxy - y)
            if score > best_score:
                best = pt
                best_score = score
    return best or (float(outer[0][0]), float(outer[0][1]))


def polygon_label_points(
    polygon: list[list[list[float]]],
    feature_type: str,
) -> list[tuple[float, float]]:
    """
    Return one or more useful label positions for a polygon.

    Large 'area'/'territorial' polygons get additional interior labels so a
    mariner does not have to find a remote boundary to discover the VHF
    channel. Smaller objects keep a single label.
    """
    if not polygon or not polygon[0]:
        return []

    primary = safe_point_in_polygon(polygon)
    if primary is None:
        return []

    outer = polygon[0]
    minx, miny, maxx, maxy = bbox_of_ring(outer)
    width = maxx - minx
    height = maxy - miny

    if feature_type not in {"area", "territorial", "vts", "vts radar support"}:
        return [primary]

    # Roughly >25-30 km in either dimension at Dutch latitudes. These are the
    # big operational areas where one label can easily be far out of view.
    if width < 0.35 and height < 0.25:
        return [primary]

    candidates: list[tuple[float, float]] = []
    nx = 4 if width >= height else 3
    ny = 4 if height > width else 3
    for iy in range(1, ny + 1):
        y = miny + (maxy - miny) * iy / (ny + 1)
        for ix in range(1, nx + 1):
            x = minx + (maxx - minx) * ix / (nx + 1)
            pt = (x, y)
            if point_in_polygon(pt, polygon):
                candidates.append(pt)

    # Keep points spread apart; always include the primary point.
    result = [primary]
    min_sep = max(width, height) * 0.22
    for pt in candidates:
        if all(math.hypot(pt[0] - q[0], pt[1] - q[1]) >= min_sep for q in result):
            result.append(pt)
        if len(result) >= 4:
            break
    return result


def representative_points(
    geometry: dict[str, Any],
    feature_type: str,
) -> list[tuple[float, float]]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")

    if gtype == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return [(float(coords[0]), float(coords[1]))]

    if gtype == "Polygon" and coords:
        return polygon_label_points(coords, feature_type)

    if gtype == "MultiPolygon" and coords:
        points: list[tuple[float, float]] = []
        # Give each substantial polygon component at least one label. This is
        # preferable to selecting only the largest component.
        for polygon in coords:
            points.extend(polygon_label_points(polygon, feature_type))
            if len(points) >= 6:
                break
        return points[:6]

    if gtype == "LineString" and coords:
        p = coords[len(coords) // 2]
        return [(float(p[0]), float(p[1]))]

    if gtype == "MultiLineString" and coords:
        longest = max(coords, key=len, default=[])
        if longest:
            p = longest[len(longest) // 2]
            return [(float(p[0]), float(p[1]))]

    if gtype == "GeometryCollection":
        points: list[tuple[float, float]] = []
        for child in geometry.get("geometries", []):
            points.extend(representative_points(child, feature_type))
        return points

    return []

def iter_track_segments(geometry: dict[str, Any]) -> Iterable[list[list[float]]]:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")

    if gtype == "Polygon":
        for ring in coords or []:
            if ring:
                yield ring
    elif gtype == "MultiPolygon":
        for polygon in coords or []:
            for ring in polygon or []:
                if ring:
                    yield ring
    elif gtype == "LineString":
        if coords:
            yield coords
    elif gtype == "MultiLineString":
        for line in coords or []:
            if line:
                yield line
    elif gtype == "GeometryCollection":
        for child in geometry.get("geometries", []):
            yield from iter_track_segments(child)

def add_track(
    root: ET.Element,
    name: str,
    desc: str,
    feature_type: str,
    geometry: dict[str, Any],
) -> bool:
    segments = list(iter_track_segments(geometry))
    if not segments:
        return False

    trk = ET.SubElement(root, q(GPX_NS, "trk"))
    ET.SubElement(trk, q(GPX_NS, "name")).text = name
    if desc:
        ET.SubElement(trk, q(GPX_NS, "desc")).text = desc

    color = TYPE_COLORS.get(feature_type, "DarkGray")
    width = TYPE_WIDTHS.get(feature_type, 4)
    extensions = ET.SubElement(trk, q(GPX_NS, "extensions"))
    ET.SubElement(extensions, q(OPENCPN_NS, "viz")).text = "1"
    ET.SubElement(
        extensions,
        q(OPENCPN_NS, "style"),
        {"width": str(width), "style": "101"},  # 101 = solid line in OpenCPN
    )
    track_ext = ET.SubElement(extensions, q(GPXX_NS, "TrackExtension"))
    ET.SubElement(track_ext, q(GPXX_NS, "DisplayColor")).text = color

    for segment in segments:
        trkseg = ET.SubElement(trk, q(GPX_NS, "trkseg"))
        for p in segment:
            if not isinstance(p, list) or len(p) < 2:
                continue
            ET.SubElement(
                trkseg,
                q(GPX_NS, "trkpt"),
                {"lat": f"{float(p[1]):.9f}", "lon": f"{float(p[0]):.9f}"},
            )
    return True

def add_label(
    root: ET.Element,
    point: tuple[float, float],
    label: str,
    desc: str,
    channel: str,
    url: str = "",
    phone: str = "",
) -> None:
    """Add a real OpenCPN mark/waypoint carrying the VHF information."""
    lon, lat = point
    wpt = ET.SubElement(
        root,
        q(GPX_NS, "wpt"),
        {"lat": f"{lat:.9f}", "lon": f"{lon:.9f}"},
    )

    # Store the actual VHFinfo object name as the OpenCPN waypoint/mark name.
    ET.SubElement(wpt, q(GPX_NS, "name")).text = label

    # Full information shown in Mark Properties when opened.
    if desc:
        ET.SubElement(wpt, q(GPX_NS, "desc")).text = desc

    # Add clickable links to OpenCPN Mark Properties.
    clean_url = str(url or "").strip()
    if clean_url.startswith(("http://", "https://")):
        link = ET.SubElement(wpt, q(GPX_NS, "link"), {"href": clean_url})
        ET.SubElement(link, q(GPX_NS, "text")).text = clean_url

    clean_phone = str(phone or "").strip()
    if clean_phone and clean_phone != "+":
        tel_number = "".join(ch for ch in clean_phone if ch.isdigit() or ch == "+")
        if tel_number:
            link = ET.SubElement(wpt, q(GPX_NS, "link"), {"href": f"tel:{tel_number}"})
            ET.SubElement(link, q(GPX_NS, "text")).text = f"tel:{tel_number}"

    # Per-channel gray custom icon. Example: channel 68 -> vhf_unknown_68.png.
    # Keep a generic fallback for any unexpected non-numeric channel value.
    channel_key = str(channel).strip()
    if channel_key.isdigit() and 1 <= int(channel_key) <= 88:
        symbol = f"vhf_unknown_{int(channel_key)}"
        show_name = False
    else:
        symbol = "vhfinfo"
        show_name = True
    ET.SubElement(wpt, q(GPX_NS, "sym")).text = symbol

    # Treat it explicitly as a waypoint/mark.
    ET.SubElement(wpt, q(GPX_NS, "type")).text = "WPT"

    # One clean OpenCPN extension block.
    extensions = ET.SubElement(wpt, q(GPX_NS, "extensions"))
    ET.SubElement(extensions, q(OPENCPN_NS, "viz")).text = "1"
    ET.SubElement(extensions, q(OPENCPN_NS, "viz_name")).text = "0" if not show_name else "1"
    ET.SubElement(
        extensions,
        q(OPENCPN_NS, "scale_min_max"),
        {"UseScale": "false", "ScaleMin": "2147483646", "ScaleMax": "0"},
    )

def build_gpx(
    geojson: dict[str, Any],
    selected_types: set[str],
    include_without_channel: bool,
    labels: bool,
) -> tuple[ET.ElementTree, int, int, int, int, int]:
    root = ET.Element(
        q(GPX_NS, "gpx"),
        {
            "version": "1.1",
            "creator": "vhfinfo_to_opencpn.py",
            q(XSI_NS, "schemaLocation"):
                "http://www.topografix.com/GPX/1/1 "
                "http://www.topografix.com/GPX/1/1/gpx.xsd "
                "http://www.garmin.com/xmlschemas/GpxExtensions/v3 "
                "http://www8.garmin.com/xmlschemas/GpxExtensionsv3.xsd",
        },
    )

    metadata = ET.SubElement(root, q(GPX_NS, "metadata"))
    ET.SubElement(metadata, q(GPX_NS, "name")).text = "VHFinfo Nederland"
    ET.SubElement(metadata, q(GPX_NS, "desc")).text = (
        "OpenCPN layer generated from VHFinfo; numeric channels use gray per-channel clickable icons."
    )
    ET.SubElement(metadata, q(GPX_NS, "time")).text = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    track_count = 0
    label_count = 0
    processed_count = 0
    skipped_count = 0

    features = geojson.get("features", [])
    if not isinstance(features, list):
        raise ValueError("GeoJSON does not contain a valid FeatureCollection.")

    received_count = len(features)

    for feature in features:
        try:
            if not isinstance(feature, dict):
                skipped_count += 1
                continue

            props = feature.get("properties") or {}
            geometry = feature.get("geometry") or {}

            if not isinstance(props, dict) or not isinstance(geometry, dict):
                skipped_count += 1
                continue

            ftype = normalize_type(props.get("type"))
            channel = channel_text(props.get("channel"))

            if selected_types and ftype not in selected_types:
                continue
            if not include_without_channel and not channel:
                continue

            name = str(
                props.get("name")
                or props.get("callname")
                or "VHFinfo"
            ).strip()

            track_name = f"VHF {channel} - {name}" if channel else name

            # Use the actual VHFinfo object name as the OpenCPN waypoint/mark
            # name. The numeric VHF channel remains visible in the custom icon
            # and is also included in the description.
            label = name
            desc = description(props)

            generic = merged_generic_properties(props)
            url = str(
                generic.get("url")
                or props.get("url")
                or ""
            ).strip()
            phone = str(
                generic.get("phone")
                or props.get("phone")
                or ""
            ).strip()

            if add_track(root, track_name, desc, ftype, geometry):
                track_count += 1

            if labels:
                for point in representative_points(geometry, ftype):
                    add_label(
                        root,
                        point,
                        label,
                        desc,
                        channel,
                        url=url,
                        phone=phone,
                    )
                    label_count += 1

            processed_count += 1

        except (
            TypeError,
            ValueError,
            IndexError,
            OverflowError,
        ):
            skipped_count += 1
            continue

    return (
        ET.ElementTree(root),
        track_count,
        label_count,
        received_count,
        processed_count,
        skipped_count,
    )

def indent(tree: ET.ElementTree) -> None:
    # Python 3.9+
    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass


def write_tree_atomically(tree: ET.ElementTree, output_path: Path) -> None:
    """
    Write the GPX to a temporary file in the destination directory and replace
    the existing file only after the complete write succeeds.
    """
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

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert VHFinfo GeoJSON to an OpenCPN GPX layer."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Local VHFinfo GeoJSON file. If omitted, the Netherlands file is downloaded.",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Download URL used when --input is omitted (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=project_layers_dir() / DEFAULT_OUTPUT,
        help=f"Output GPX file (default: layers/{DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--types",
        nargs="*",
        default=[],
        help=(
            "Only include these VHFinfo types, e.g. "
            "--types vts area territorial lock bridge marina"
        ),
    )
    parser.add_argument(
        "--include-without-channel",
        action="store_true",
        help="Also include features for which no VHF channel is specified.",
    )
    parser.add_argument(
        "--no-labels",
        action="store_true",
        help="Do not create waypoint labels; create only boundary tracks.",
    )
    args = parser.parse_args()

    selected_types = {normalize_type(t) for t in args.types}

    try:
        geojson = load_geojson(args.input, args.url)
        (
            tree,
            tracks,
            labels,
            received,
            processed,
            skipped,
        ) = build_gpx(
            geojson,
            selected_types=selected_types,
            include_without_channel=args.include_without_channel,
            labels=not args.no_labels,
        )
        indent(tree)
        write_tree_atomically(tree, args.output)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Created:            {args.output}")
    print(f"Received features:  {received}")
    print(f"Processed features: {processed}")
    print(f"Skipped invalid:    {skipped}")
    print(f"Boundaries/tracks:  {tracks}")
    print(f"Labels/marks:       {labels}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
