"""Independent, offline content audit of existing merge outputs against sources.

Does not generate missions and is not a DJI firmware/schema validator.
Run from any directory: python audit_merged_kmz.py
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import zipfile
from xml.etree import ElementTree as ET

BASE = Path(__file__).resolve().parent
NS = {"k": "http://www.opengis.net/kml/2.2", "w": "http://www.dji.com/wpmz/1.0.2"}
MEMBER = "wpmz/waylines.wpml"


def parse(data):
    root = ET.fromstring(data)
    for node in root.iter():
        node.tag = node.tag.replace("http://www.uav.com/wpmz/1.0.2", NS["w"])
    return root


def value(node, path):
    return node.findtext(path, namespaces=NS).strip()


def shape(node):
    # Ignore formatting only; preserve child order, attributes and every value.
    return (node.tag, (node.text or "").strip(), tuple(sorted(node.attrib.items())), tuple(shape(c) for c in node))


def set_value(node, path, text):
    node.find(path, NS).text = str(text)


def audit(report_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    kmz = report_path.with_name(report_path.name.replace(".report.json", ".kmz"))
    errors = []
    changes = Counter()
    all_points = []
    source_size = 0
    group_id = 0
    expected_assets = {}
    for source in report["sources"]:
        path = Path(source["file"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            errors.append(f"Source hash differs: {path}")
        with zipfile.ZipFile(path) as z:
            raw = z.read(MEMBER)
            for n in z.namelist():
                if n not in (MEMBER, "wpmz/template.kml"):
                    expected_assets[n] = z.read(n)
        source_size += len(raw)
        points = parse(raw).findall("k:Document/k:Folder/k:Placemark", NS)
        offset = len(all_points)
        for i, p in enumerate(points):
            set_value(p, "w:index", offset+i)
            for g in p.findall("w:actionGroup", NS):
                set_value(g, "w:actionGroupId", group_id)
                group_id += 1
                for field in ("actionGroupStartIndex", "actionGroupEndIndex"):
                    set_value(g, "w:"+field, int(value(g, "w:"+field))+offset)
                if value(g, "w:actionGroupMode") == "parallel":
                    if len(g.findall("w:action", NS)) != 1:
                        errors.append("Unexpected parallel group with multiple actions")
                    set_value(g, "w:actionGroupMode", "sequence")
                    changes["single_action_parallel_to_sequence"] += 1
                for j, a in enumerate(g.findall("w:action", NS)):
                    set_value(a, "w:actionId", j)
                    if value(a, "w:actionActuatorFunc") == "takePhoto":
                        params = a.find("w:actionActuatorFuncParam", NS)
                        lens = params.find("w:payloadLensIndex", NS)
                        if lens is None:
                            lens = ET.SubElement(params, "{"+NS["w"]+"}payloadLensIndex")
                        lens.text = report["image_format"]
                        set_value(params, "w:payloadPositionIndex", 0)
                        set_value(params, "w:useGlobalPayloadLensIndex", 0)
                        changes["explicit_photo_lens"] += 1
            all_points.append(p)
    with zipfile.ZipFile(kmz) as z:
        info = z.getinfo(MEMBER)
        root = parse(z.read(MEMBER))
        template = parse(z.read("wpmz/template.kml"))
        if z.testzip() is not None:
            errors.append("ZIP CRC error")
        for name, data in expected_assets.items():
            if z.read(name) != data:
                errors.append(f"Resource changed: {name}")
    points = root.findall("k:Document/k:Folder/k:Placemark", NS)
    template_points = template.findall("k:Document/k:Folder/k:Placemark", NS)
    if len(points) != len(all_points) or len(template_points) != len(points):
        errors.append("Waypoint count differs")
    if len(root.findall("k:Document/k:Folder", NS)) != 1:
        errors.append("Not exactly one executable route")
    for i, (expected, actual) in enumerate(zip(all_points, points)):
        if shape(expected) != shape(actual):
            errors.append(f"Unexpected executable waypoint change: {i}")
    for i, (p, t) in enumerate(zip(points, template_points)):
        t = deepcopy(t)
        for name in ("useGlobalHeight", "useGlobalSpeed", "useGlobalHeadingParam", "useGlobalTurnParam"):
            flag = t.find("w:"+name, NS)
            expected = "1" if name == "useGlobalHeight" else "0"
            if flag is None or flag.text != expected:
                errors.append(f"Template override differs: {i}/{name}")
            if flag is not None:
                t.remove(flag)
        height = t.find("w:height", NS)
        if height is None:
            errors.append(f"Missing template height: {i}")
        else:
            height.tag = "{"+NS["w"]+"}executeHeight"
        if shape(t) != shape(p):
            errors.append(f"Template/wayline mismatch: {i}")
        if value(template, "k:Document/k:Folder/w:globalHeight") != value(p, "w:executeHeight"):
            errors.append(f"Global template height mismatch: {i}")
    if shape(root.find("k:Document/w:missionConfig", NS)) != shape(template.find("k:Document/w:missionConfig", NS)):
        errors.append("Mission configs differ between template and waylines")
    actions = Counter(value(a, "w:actionActuatorFunc") for a in root.findall(".//w:action", NS))
    return {"dataset": kmz.parent.name, "waypoints": len(points), "actions": dict(actions),
            "source_waylines_bytes_total": source_size, "merged_waylines_bytes": info.file_size,
            "merged_waylines_compressed_bytes": info.compress_size,
            "expected_changes": dict(changes), "unexpected_differences": errors,
            "scope": "All waypoint XML descendants, order, values and attributes; template parity; source hashes; resources; ZIP CRC. Not DJI schema/firmware validation."}


def main():
    reports = sorted((BASE / "output/merged").glob("*/Mavic3T_merged.report.json"))
    results = [audit(p) for p in reports]
    destination = BASE / "output/merged/structure_audit.json"
    destination.write_text(json.dumps(results, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    for r in results:
        print(r["dataset"], r["waypoints"], r["actions"], "unexpected:", len(r["unexpected_differences"]))
    if not results or any(r["unexpected_differences"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
