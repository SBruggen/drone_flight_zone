#!/usr/bin/env python3
"""Merge Aerial 3D waypoint exports into an experimental DJI Mavic 3T KMZ.

Standard library only. No aircraft connection; Pilot 2 validation is still required.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import time
import zipfile
from xml.etree import ElementTree as ET

KML = "http://www.opengis.net/kml/2.2"
WPML = "http://www.dji.com/wpmz/1.0.2"
LEGACY = "http://www.uav.com/wpmz/1.0.2"
NS = {"k": KML, "w": WPML}
ET.register_namespace("", KML)
ET.register_namespace("wpml", WPML)
MEMBERS = ("wpmz/template.kml", "wpmz/waylines.wpml")


def get(node, path):
    value = node.findtext(path, namespaces=NS)
    if value is None or not value.strip():
        raise ValueError(f"Ontbrekend veld: {path}")
    return value.strip()


def put(node, name, value=None, namespace=WPML):
    tag = f"{{{namespace}}}{name}"
    child = node.find(tag)
    if child is None:
        child = ET.SubElement(node, tag)
    if value is not None:
        child.text = str(value)
    return child


def number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Niet-eindig getal")
    return value


def signature(node):
    return (node.tag, (node.text or "").strip(), tuple(sorted(node.attrib.items())),
            tuple(signature(c) for c in node))


def parse(data):
    root = ET.fromstring(data)
    for node in root.iter():
        if node.tag.startswith("{" + LEGACY + "}"):
            node.tag = node.tag.replace(LEGACY, WPML, 1)
    return root


def natural_key(path):
    return [int(s) if s.isdigit() else s.lower() for s in re.split(r"(\d+)", path.name)]


def position(point):
    coords = [number(v) for v in get(point, "k:Point/k:coordinates").split(",")]
    if len(coords) != 2 or not -180 <= coords[0] <= 180 or not -90 <= coords[1] <= 90:
        raise ValueError("Ongeldige lengte/breedtegraad")
    return (*coords, number(get(point, "w:executeHeight")))


def distance(a, b):
    lon1, lat1, h1 = position(a)
    lon2, lat2, h2 = position(b)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    horizontal = 6371008.8 * 2 * math.asin(math.sqrt(min(1, d)))
    return math.hypot(horizontal, h2-h1)


def read_source(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f"{path}: dubbele ZIP-paden")
        for name in names:
            if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name:
                raise ValueError(f"{path}: ongeldig ZIP-pad")
        if not all(name in names for name in MEMBERS):
            raise ValueError(f"{path}: verwacht wpmz/template.kml en wpmz/waylines.wpml")
        roots = [parse(archive.read(name)) for name in MEMBERS]
        extras = {name: archive.read(name) for name in names if name not in MEMBERS}
    # Deliberately limited: rebuilding an existing rich template may lose semantics.
    if roots[0].findall("k:Document/k:Folder", NS):
        raise ValueError(f"{path}: alleen Aerial 3D-export met lege template ondersteund")
    folders = roots[1].findall("k:Document/k:Folder", NS)
    if len(folders) != 1:
        raise ValueError(f"{path}: precies één uitvoerroute vereist")
    folder = folders[0]
    allowed = {"templateId", "executeHeightMode", "waylineId", "distance", "duration", "autoFlightSpeed", "Placemark"}
    if any(c.tag.split("}")[-1] not in allowed for c in folder):
        raise ValueError(f"{path}: niet-ondersteunde routemetadata")
    if get(folder, "w:executeHeightMode") != "relativeToStartPoint":
        raise ValueError(f"{path}: alleen hoogten relatief aan hetzelfde vertrekpunt ondersteund")
    points = folder.findall("k:Placemark", NS)
    if len(points) < 2:
        raise ValueError(f"{path}: minimaal twee waypoints vereist")
    if [int(get(p, "w:index")) for p in points] != list(range(len(points))):
        raise ValueError(f"{path}: waypointindices moeten vanaf 0 opeenvolgen")
    config = roots[1].find("k:Document/w:missionConfig", NS)
    if config is None:
        raise ValueError(f"{path}: missionConfig ontbreekt")
    return config, folder, points, extras


def document(config):
    root = ET.Element(f"{{{KML}}}kml")
    doc = put(root, "Document", namespace=KML)
    put(doc, "author", "Aerial 3D merge / Mavic 3T experimental")
    put(doc, "createTime", int(time.time()*1000))
    put(doc, "updateTime", get(doc, "w:createTime"))
    doc.append(deepcopy(config))
    return root, put(doc, "Folder", namespace=KML)


def merge(paths, output, *, takeoff_height=None, rth_height=None, image_format="wide", max_waypoints=65535, dry_run=False):
    output = Path(output)
    paths = [Path(p).resolve() for p in paths]
    report_path = output.with_suffix(".report.json")
    if len(paths) < 2 or len(set(paths)) != len(paths):
        raise ValueError("Minimaal twee verschillende bronbestanden vereist")
    if output.suffix.lower() != ".kmz" or output.resolve() in paths:
        raise ValueError("Kies een nieuw .kmz-uitvoerbestand buiten de bronbestanden")
    if not dry_run and (output.exists() or report_path.exists()):
        raise ValueError("Uitvoer of rapport bestaat al; kies een andere naam")
    if not 2 <= max_waypoints <= 65535:
        raise ValueError("max-waypoints moet tussen 2 en 65535 liggen (formaatgrens, geen hardwaregarantie)")
    merged, extras, sources, joins = [], {}, [], []
    base_config = None
    group_id = 0
    warnings = ["Experimentele conversie; import en uitvoering niet getest in DJI Pilot 2.",
                "Alle relatieve hoogten veronderstellen hetzelfde vertrekhoogteniveau.",
                "Bestaande stops/hoveracties blijven behouden; batterij/RTH kan de route onderbreken."]
    parallel_count = 0
    for path in paths:
        config, folder, points, assets = read_source(path)
        if base_config is None:
            base_config = deepcopy(config)
            speed = get(folder, "w:autoFlightSpeed")
        elif signature(config) != signature(base_config) or get(folder, "w:autoFlightSpeed") != speed:
            raise ValueError(f"{path}: missie-instellingen of globale snelheid verschillen")
        for name, data in assets.items():
            if name in extras and extras[name] != data:
                raise ValueError(f"Botsende resource: {name}")
            extras[name] = data
        offset = len(merged)
        if merged:
            joins.append({"from_index": offset-1, "to_index": offset,
                          "distance_m": round(distance(merged[-1], points[0]), 3)})
        for local_index, point in enumerate(points):
            position(point)
            if not 0 < number(get(point, "w:waypointSpeed")) <= 15:
                raise ValueError(f"{path}: waypointSpeed buiten ondersteund bereik (0,15]")
            put(point, "index", offset+local_index)
            for group in point.findall("w:actionGroup", NS):
                start = int(get(group, "w:actionGroupStartIndex"))
                end = int(get(group, "w:actionGroupEndIndex"))
                if not 0 <= start <= end < len(points):
                    raise ValueError(f"{path}: ongeldige actie-index")
                actions = group.findall("w:action", NS)
                mode = get(group, "w:actionGroupMode")
                if mode == "parallel" and len(actions) == 1:
                    put(group, "actionGroupMode", "sequence")
                    parallel_count += 1
                elif mode != "sequence":
                    raise ValueError(f"{path}: parallelle acties kunnen niet zonder gedragswijziging worden omgezet")
                if get(group, "w:actionTrigger/w:actionTriggerType") != "reachPoint":
                    raise ValueError(f"{path}: alleen reachPoint-acties ondersteund")
                put(group, "actionGroupId", group_id)
                group_id += 1
                put(group, "actionGroupStartIndex", start+offset)
                put(group, "actionGroupEndIndex", end+offset)
                for action_id, action in enumerate(actions):
                    put(action, "actionId", action_id)
                    func = get(action, "w:actionActuatorFunc")
                    if func not in {"takePhoto", "gimbalRotate", "hover"}:
                        raise ValueError(f"{path}: niet-ondersteunde actie {func}")
                    params = action.find("w:actionActuatorFuncParam", NS)
                    if params is None:
                        raise ValueError("Actieparameters ontbreken")
                    if func == "takePhoto":
                        put(params, "payloadPositionIndex", 0)
                        put(params, "useGlobalPayloadLensIndex", 0)
                        put(params, "payloadLensIndex", image_format)
                    if func == "gimbalRotate":
                        if get(params, "w:gimbalRotateMode") != "absoluteAngle":
                            raise ValueError("Alleen absolute gimbalrotatie ondersteund")
                        if get(params, "w:gimbalPitchRotateEnable") == "1" and not -90 <= number(get(params, "w:gimbalPitchRotateAngle")) <= 35:
                            raise ValueError("Gimbal-pitch buiten Mavic 3T-bereik")
                    if func == "hover" and number(get(params, "w:hoverTime")) <= 0:
                        raise ValueError("Ongeldige hovertijd")
            merged.append(point)
        sources.append({"file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "waypoints": len(points), "first_index": offset, "last_index": len(merged)-1})
    if len(merged) > max_waypoints or group_id > 65536:
        raise ValueError(f"Te veel waypoints/actiegroepen: {len(merged)}/{group_id}")
    heights = {number(get(p, "w:executeHeight")) for p in merged}
    if len(heights) != 1:
        raise ValueError("Deze conversie vereist één relatieve vlieghoogte: absolute ellipsoïdehoogten ontbreken voor een variabele template")
    if not 0 < number(speed) <= 15 or not 0 < number(get(base_config, "w:globalTransitionalSpeed")) <= 15:
        raise ValueError("Globale snelheid buiten ondersteund bereik (0,15]")
    config = deepcopy(base_config)
    put(put(config, "droneInfo"), "droneEnumValue", 77)
    put(put(config, "droneInfo"), "droneSubEnumValue", 1)
    put(put(config, "payloadInfo"), "payloadEnumValue", 67)
    put(put(config, "payloadInfo"), "payloadPositionIndex", 0)
    if takeoff_height is None:
        takeoff_height = number(get(merged[0], "w:executeHeight"))
        warnings.append("takeOffSecurityHeight ingesteld op hoogte eerste waypoint; controleer obstakels bij vertrek.")
    if not 1.2 <= number(takeoff_height) <= 1500:
        raise ValueError("takeoff-height moet tussen 1.2 en 1500 m liggen")
    put(config, "takeOffSecurityHeight", takeoff_height)
    if rth_height is None:
        rth_height = max(20, takeoff_height, max(heights))
        warnings.append("RTH-hoogte ingesteld op max(20 m, vertrekhoogte, vlieghoogte); controleer terrein/obstakels.")
    if not 20 <= number(rth_height) <= 1500:
        raise ValueError("rth-height moet tussen 20 en 1500 m liggen")
    put(config, "globalRTHHeight", rth_height)
    wayroot, wayfolder = document(config)
    for name, value in [("templateId", 0), ("executeHeightMode", "relativeToStartPoint"),
                        ("waylineId", 0), ("autoFlightSpeed", speed)]:
        put(wayfolder, name, value)
    wayfolder.extend(merged)
    template, tfolder = document(config)
    put(tfolder, "templateType", "waypoint")
    put(tfolder, "templateId", 0)
    coordinate = put(tfolder, "waylineCoordinateSysParam")
    put(coordinate, "coordinateMode", "WGS84")
    put(coordinate, "heightMode", "relativeToStartPoint")
    put(coordinate, "positioningType", "GPS")
    put(tfolder, "autoFlightSpeed", speed)
    put(tfolder, "globalHeight", get(merged[0], "w:executeHeight"))
    put(tfolder, "gimbalPitchMode", "manual")
    heading = put(tfolder, "globalWaypointHeadingParam")
    put(heading, "waypointHeadingMode", "followWayline")
    put(heading, "waypointHeadingPathMode", "followBadArc")
    put(tfolder, "globalWaypointTurnMode", "toPointAndStopWithContinuityCurvature")
    put(tfolder, "globalUseStraightLine", 0)
    payload = put(tfolder, "payloadParam")
    put(payload, "payloadPositionIndex", 0)
    put(payload, "imageFormat", image_format)
    for point in merged:
        p = deepcopy(point)
        height = p.find("w:executeHeight", NS)
        height.tag = f"{{{WPML}}}height"
        for flag in ["useGlobalHeight", "useGlobalSpeed", "useGlobalHeadingParam", "useGlobalTurnParam"]:
            put(p, flag, 0)
        put(p, "useGlobalHeight", 1)
        tfolder.append(p)
    total_distance = sum(distance(a, b) for a, b in zip(merged, merged[1:]))
    photo_count = sum(get(a, "w:actionActuatorFunc") == "takePhoto" for p in merged for a in p.findall(".//w:action", NS))
    if not photo_count:
        warnings.append("Bronnen bevatten geen fotoacties; uitvoer maakt dus geen automatische foto's.")
    warnings.append(f"{parallel_count} parallelgroepen met één actie omgezet naar gedocumenteerde sequence-modus.")
    report = {"status": "experimental_not_validated_in_pilot2", "target": "DJI Mavic 3T",
              "waypoints": len(merged), "action_groups": group_id, "photo_actions": photo_count,
              "image_format": image_format, "finish_action": get(config, "w:finishAction"),
              "rc_lost": [get(config, "w:exitOnRCLost"), get(config, "w:executeRCLostAction")],
              "takeoff_security_height_m": takeoff_height,
              "rth_height_m": rth_height,
              "approximate_polyline_distance_m": round(total_distance, 2),
              "sources": sources, "connections": joins, "warnings": warnings}
    if not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in extras.items():
                archive.writestr(name, data)
            for name, root in zip(MEMBERS, [template, wayroot]):
                ET.indent(root)
                archive.writestr(name, ET.tostring(root, encoding="utf-8", xml_declaration=True))
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="Eén map (niet recursief), of bestanden in gewenste volgorde")
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--takeoff-height", type=float, help="Veilige vertrekhoogte in m; standaard eerste waypointhoogte")
    parser.add_argument("--rth-height", type=float, help="RTH-hoogte in m; standaard max(20, vertrekhoogte, vlieghoogte)")
    parser.add_argument("--image-format", choices=["wide", "ir", "wide,ir"], default="wide")
    parser.add_argument("--max-waypoints", type=int, default=65535, help="Eigen limiet; standaard alleen formaatgrens, geen hardwaregarantie")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    paths = args.inputs
    if len(paths) == 1 and paths[0].is_dir():
        paths = sorted(paths[0].glob("*.kmz"), key=natural_key)
    try:
        report = merge(paths, args.output, takeoff_height=args.takeoff_height,
                       rth_height=args.rth_height, image_format=args.image_format,
                       max_waypoints=args.max_waypoints, dry_run=args.dry_run)
    except (ValueError, OSError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Fout: {exc}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
