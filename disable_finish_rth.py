"""Copy original KMZ missions, changing only finishAction goHome to noAction.

Preserves XML bytes except that value, ZIP member paths, metadata and compression.
Usage: python disable_finish_rth.py data -o output/no_finish_rth
"""
import argparse
from copy import copy
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

MEMBERS = {'wpmz/template.kml', 'wpmz/waylines.wpml'}
PATTERN = re.compile(rb'(<wpml:finishAction>\s*)goHome(\s*</wpml:finishAction>)')


def patch_xml(data):
    root = ET.fromstring(data)
    nodes = root.findall('./{*}Document/{*}missionConfig/{*}finishAction')
    if len(nodes) != 1 or nodes[0].text.strip() != 'goHome':
        raise ValueError('Verwacht precies één finishAction=goHome in missionConfig')
    updated, count = PATTERN.subn(rb'\g<1>noAction\g<2>', data)
    if count != 1:
        raise ValueError('Onverwachte XML-opmaak; bestand niet aangepast')
    # Check that the textual replacement targeted precisely the parsed setting.
    nodes[0].text = nodes[0].text.replace('goHome', 'noAction')
    if ET.tostring(root) != ET.tostring(ET.fromstring(updated)):
        raise ValueError('Onverwachte XML-wijziging')
    return updated


def prepare(source):
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or not MEMBERS.issubset(names):
            raise ValueError(f'{source}: ontbrekende of dubbele ZIP-members')
        entries = [(copy(info), patch_xml(archive.read(info)) if info.filename in MEMBERS
                    else archive.read(info)) for info in archive.infolist()]
        return entries, archive.comment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('-o', '--output', required=True, type=Path)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if not source.is_dir() or output == source or source in output.parents:
        parser.error('Kies een bronmap en een uitvoermap buiten de bronmap')
    paths = sorted(source.rglob('*.kmz'))
    if not paths:
        parser.error('Geen KMZ-bestanden gevonden')
    prepared = []
    # Validate the complete batch before creating any output.
    for path in paths:
        target = output / path.relative_to(source)
        if target.exists():
            parser.error(f'Uitvoer bestaat al: {target}')
        entries, comment = prepare(path)
        prepared.append((target, entries, comment))
    for target, entries, comment in prepared:
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, 'x') as archive:
            archive.comment = comment
            for info, data in entries:
                archive.writestr(info, data)
        print(target.relative_to(output))
    print(f'{len(prepared)} kopieën gemaakt; uitsluitend finishAction aangepast in beide XML-bestanden.')


if __name__ == '__main__':
    main()
