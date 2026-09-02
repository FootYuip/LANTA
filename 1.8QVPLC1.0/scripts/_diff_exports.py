#!/usr/bin/env python3
"""Quick diff between two PLCopen XML exports."""
from __future__ import annotations

import difflib
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "http://www.plcopen.org/xml/tc6_0200"


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def pou_st_lines(root: ET.Element, name: str) -> list[str]:
    for pou in root.findall(f".//{{{NS}}}pou"):
        if pou.get("name") != name:
            continue
        lines: list[str] = []
        for elem in pou.iter():
            tag = strip_ns(elem.tag)
            if tag == "xhtml":
                t = "".join(elem.itertext()).strip()
                if t:
                    lines.extend(t.splitlines())
            elif tag == "ST" and (elem.text or "").strip():
                lines.extend(elem.text.strip().splitlines())
        return lines
    return []


def gvl_blocks(root: ET.Element) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for gv in root.findall(f".//{{{NS}}}globalVars"):
        name = gv.get("name", "(unnamed)")
        lines = []
        for v in gv.findall(f"{{{NS}}}variable"):
            lines.append(v.get("name", "?"))
        out[name] = sorted(lines)
    return out


def task_info(root: ET.Element) -> list[str]:
    rows = []
    for t in root.findall(f".//{{{NS}}}task"):
        rows.append(
            f"{t.get('name')}|interval={t.get('interval')}|priority={t.get('priority')}"
        )
    return sorted(rows)


def main() -> int:
    old_dir = Path(__file__).resolve().parent.parent / "project-rebuid"
    new_dir = Path(__file__).resolve().parent.parent / "codesys-export"
    old_xml = sorted(old_dir.glob("*.xml"))
    new_xml = sorted(new_dir.glob("*.xml"))
    if not old_xml or not new_xml:
        print("Missing xml for comparison")
        return 1

    old_root = ET.parse(old_xml[0]).getroot()
    new_root = ET.parse(new_xml[0]).getroot()

    oh = old_root.find(f"{{{NS}}}fileHeader")
    nh = new_root.find(f"{{{NS}}}fileHeader")
    print("OLD:", oh.get("creationDateTime") if oh is not None else "?")
    print("NEW:", nh.get("creationDateTime") if nh is not None else "?")
    print()

    og, ng = gvl_blocks(old_root), gvl_blocks(new_root)
    for gname in sorted(set(og) | set(ng)):
        if og.get(gname) != ng.get(gname):
            print(f"GVL '{gname}' variables changed")
            added = set(ng.get(gname, [])) - set(og.get(gname, []))
            removed = set(og.get(gname, [])) - set(ng.get(gname, []))
            if added:
                print("  +", ", ".join(sorted(added)))
            if removed:
                print("  -", ", ".join(sorted(removed)))

    ot, nt = task_info(old_root), task_info(new_root)
    if ot != nt:
        print("Tasks changed:")
        for line in difflib.unified_diff(ot, nt, lineterm=""):
            print(line)
    print()

    pou_names = sorted({p.get("name") for p in old_root.findall(f".//{{{NS}}}pou")})
    changed = []
    for name in pou_names:
        if pou_st_lines(old_root, name) != pou_st_lines(new_root, name):
            changed.append(name)

    print(f"POU ST changed ({len(changed)}):")
    for name in changed:
        print(f"  - {name}")

    print("\n--- Sample diffs (first 25 lines each) ---")
    for name in changed:
        diff = list(
            difflib.unified_diff(
                pou_st_lines(old_root, name),
                pou_st_lines(new_root, name),
                fromfile="old",
                tofile="new",
                lineterm="",
                n=1,
            )
        )
        if not diff:
            continue
        print(f"\n### {name}")
        for line in diff[:25]:
            print(line)
        if len(diff) > 25:
            print(f"... ({len(diff) - 25} more lines)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
