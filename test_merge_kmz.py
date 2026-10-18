"""Regression checks using the supplied Aerial 3D exports; no flight execution."""
from copy import deepcopy
from pathlib import Path
import shutil
from types import SimpleNamespace
from uuid import uuid4
import unittest
import zipfile
from xml.etree import ElementTree as ET

import merge_kmz as m

DATA = Path(__file__).parent / "data" / "ZOL_zone_1_2026-09-24"


class MergeTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parent / ("merge_test_" + uuid4().hex)
        path.mkdir()
        self.temp = SimpleNamespace(name=str(path))
        assert Path(self.temp.name).resolve().parent == Path(__file__).resolve().parent
        self.addCleanup(shutil.rmtree, path)
        self.output = Path(self.temp.name) / "merged.kmz"
        self.inputs = sorted(DATA.glob("*.kmz"), key=m.natural_key)
        self.assertEqual(len(self.inputs), 10)

    def mutate(self, index, change):
        path = Path(self.temp.name) / f"changed{index}.kmz"
        with zipfile.ZipFile(self.inputs[index]) as src, zipfile.ZipFile(path, "w") as dst:
            for name in src.namelist():
                data = src.read(name)
                if name == m.MEMBERS[1]:
                    root = m.parse(data)
                    change(root)
                    data = ET.tostring(root)
                dst.writestr(name, data)
        return path

    def test_full_merge_preserves_route_and_actions(self):
        before = [p.read_bytes() for p in self.inputs]
        report = m.merge(self.inputs, self.output)
        self.assertEqual(report["waypoints"], 912)
        self.assertEqual(report["photo_actions"], 912)
        self.assertEqual([p.read_bytes() for p in self.inputs], before)
        source_points = [p for path in self.inputs for p in m.read_source(path)[2]]
        with zipfile.ZipFile(self.output) as z:
            self.assertEqual(set(z.namelist()), {"wpmz/", *m.MEMBERS})
            roots = [m.parse(z.read(n)) for n in m.MEMBERS]
        for root in roots:
            points = root.findall("k:Document/k:Folder/k:Placemark", m.NS)
            self.assertEqual([int(m.get(p, "w:index")) for p in points], list(range(912)))
            groups = root.findall(".//w:actionGroup", m.NS)
            self.assertEqual([int(m.get(g, "w:actionGroupId")) for g in groups], list(range(922)))
            for g in groups:
                self.assertTrue(0 <= int(m.get(g, "w:actionGroupStartIndex")) <= int(m.get(g, "w:actionGroupEndIndex")) < 912)
            cfg = root.find("k:Document/w:missionConfig", m.NS)
            self.assertEqual(m.get(cfg, "w:droneInfo/w:droneEnumValue"), "77")
            self.assertEqual(m.get(cfg, "w:droneInfo/w:droneSubEnumValue"), "1")
            self.assertEqual(m.get(cfg, "w:payloadInfo/w:payloadEnumValue"), "67")
        output_points = roots[1].findall(".//k:Placemark", m.NS)
        for old, new in zip(source_points, output_points):
            self.assertEqual(m.position(old), m.position(new))
            for path in ["w:waypointSpeed", "w:waypointHeadingParam", "w:waypointTurnParam"]:
                self.assertEqual(m.signature(old.find(path, m.NS)), m.signature(new.find(path, m.NS)))
            old_actions = old.findall(".//w:action", m.NS)
            new_actions = new.findall(".//w:action", m.NS)
            self.assertEqual(len(old_actions), len(new_actions))
            for a, b in zip(old_actions, new_actions):
                self.assertEqual(m.get(a, "w:actionActuatorFunc"), m.get(b, "w:actionActuatorFunc"))
                if m.get(a, "w:actionActuatorFunc") != "takePhoto":
                    self.assertEqual(m.signature(a.find("w:actionActuatorFuncParam", m.NS)), m.signature(b.find("w:actionActuatorFuncParam", m.NS)))
        # First action at the second source must now point to waypoint 99.
        self.assertEqual(m.get(output_points[99], "w:actionGroup/w:actionGroupStartIndex"), "99")

    def test_rejects_invalid_reference(self):
        changed = self.mutate(1, lambda r: setattr(r.find(".//w:actionGroupEndIndex", m.NS), "text", "9999"))
        with self.assertRaisesRegex(ValueError, "actie-index"):
            m.merge([self.inputs[0], changed], self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_conflicting_settings(self):
        changed = self.mutate(1, lambda r: setattr(r.find(".//w:finishAction", m.NS), "text", "autoLand"))
        with self.assertRaisesRegex(ValueError, "instellingen"):
            m.merge([self.inputs[0], changed], self.output)

    def test_limits_dry_run_and_no_overwrite(self):
        with self.assertRaisesRegex(ValueError, "Te veel"):
            m.merge(self.inputs, self.output, max_waypoints=99)
        m.merge(self.inputs, self.output, dry_run=True)
        self.assertFalse(self.output.exists())
        self.output.write_bytes(b"existing")
        with self.assertRaisesRegex(ValueError, "bestaat al"):
            m.merge(self.inputs, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing")
        with self.assertRaises(ValueError):
            m.merge(self.inputs, self.inputs[0])

    def test_resource_collision_and_multiple_parallel_actions(self):
        def change(root):
            group = root.findall(".//w:actionGroup", m.NS)[1]
            group.append(deepcopy(group.find("w:action", m.NS)))
        changed = self.mutate(1, change)
        with self.assertRaisesRegex(ValueError, "parallelle"):
            m.merge([self.inputs[0], changed], self.output)
        copies = []
        for i in range(2):
            p = Path(self.temp.name) / f"asset{i}.kmz"
            p.write_bytes(self.inputs[i].read_bytes())
            with zipfile.ZipFile(p, "a") as z:
                z.writestr("wpmz/res/example.bin", bytes([i]))
            copies.append(p)
        with self.assertRaisesRegex(ValueError, "Botsende resource"):
            m.merge(copies, self.output)


if __name__ == "__main__":
    unittest.main()
