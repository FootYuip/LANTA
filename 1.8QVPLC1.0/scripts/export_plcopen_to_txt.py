#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export CODESYS PLCopen XML to plc-src folder + txt structure."""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "http://www.plcopen.org/xml/tc6_0200"
XHTML = "http://www.w3.org/1999/xhtml"
OBJID_DATA = "http://www.3s-software.com/plcopenxml/objectid"

TASK_NAMES = frozenset({"MainTask", "SerialCom", "Canopen", "Task", "VISU_TASK"})
DEVICE_PLACEHOLDER_NAMES = frozenset(
    {
        "库管理器",
        "GCAN_IoDrv",
        "GCAN_IoMDP",
        "GC5016_Digital_Input_Output",
        "CANbus",
        "CANopen_Manager",
        "eDriver_El",
        "eDriver_Az",
        "eDriver_Ti",
        "SoftMotion General Axis Pool",
    }
)
MISSING_DUT_PLACEHOLDER = frozenset()  # all unions present in this export

VAR_SECTIONS = (
    ("inputVars", "VAR_INPUT"),
    ("outputVars", "VAR_OUTPUT"),
    ("inOutVars", "VAR_IN_OUT"),
    ("localVars", "VAR"),
    ("externalVars", "VAR_EXTERNAL"),
    ("globalVars", "VAR_GLOBAL"),
    ("tempVars", "VAR_TEMP"),
)


def q(tag: str) -> str:
    return f"{{{NS}}}{tag}"


def strip_ns(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def text_content(elem: ET.Element | None) -> str:
    if elem is None:
        return ""
    return "".join(elem.itertext()).strip()


def get_object_id(elem: ET.Element) -> str | None:
    for data in elem.iter():
        if strip_ns(data.tag) != "data":
            continue
        if data.get("name") != OBJID_DATA:
            continue
        for child in data:
            if strip_ns(child.tag) == "ObjectId":
                return (child.text or "").strip()
    return None


def find_xhtml_doc(parent: ET.Element) -> str:
    for doc in parent.findall(f".//{{{NS}}}documentation"):
        for xhtml in doc.findall(f"{{{NS}}}xhtml"):
            t = text_content(xhtml)
            if t:
                return t
    return ""


def type_to_iec(type_elem: ET.Element | None, indent: int = 0) -> str:
    if type_elem is None:
        return "UNKNOWN"

    for child in type_elem:
        tag = strip_ns(child.tag)
        if tag == "BOOL":
            return "BOOL"
        if tag == "INT":
            return "INT"
        if tag == "DINT":
            return "DINT"
        if tag == "UINT":
            return "UINT"
        if tag == "UDINT":
            return "UDINT"
        if tag == "WORD":
            return "WORD"
        if tag == "DWORD":
            return "DWORD"
        if tag == "BYTE":
            return "BYTE"
        if tag == "REAL":
            return "REAL"
        if tag == "LREAL":
            return "LREAL"
        if tag == "ULINT":
            return "ULINT"
        if tag == "TIME":
            return "TIME"
        if tag == "DATE":
            return "DATE"
        if tag == "TIME_OF_DAY":
            return "TIME_OF_DAY"
        if tag == "DATE_AND_TIME":
            return "DATE_AND_TIME"
        if tag == "DT":
            return "DT"
        if tag == "TOD":
            return "TOD"
        if tag == "STRING":
            length = child.get("length")
            return f"STRING({length})" if length else "STRING"
        if tag == "derived":
            return child.get("name", "UNKNOWN")
        if tag == "array":
            dims = child.findall(f"{{{NS}}}dimension")
            if dims:
                lo = dims[0].get("lower", "0")
                hi = dims[0].get("upper", "0")
                inner = type_to_iec(child.find(f"{{{NS}}}baseType"))
                return f"ARRAY[{lo}..{hi}] OF {inner}"
            inner = type_to_iec(child.find(f"{{{NS}}}baseType"))
            return f"ARRAY OF {inner}"
        if tag in ("struct", "enum", "union"):
            return tag.upper()
    return "UNKNOWN"


def format_variable(var: ET.Element, global_style: bool = False) -> str:
    name = var.get("name", "?")
    addr = var.get("address")
    type_elem = var.find(f"{{{NS}}}type")
    iec_type = type_to_iec(type_elem)
    doc = find_xhtml_doc(var)
    comment = f" // {doc}" if doc else ""

    if global_style:
        prefix = "VAR_GLOBAL"
        if addr:
            line = f"    {name} AT {addr} : {iec_type};{comment}"
        else:
            line = f"    {name} : {iec_type};{comment}"
        return line

    if addr:
        line = f"    {name} AT {addr} : {iec_type};{comment}"
    else:
        line = f"    {name} : {iec_type};{comment}"
    return line


def format_interface(interface: ET.Element | None, pou_type: str) -> str:
    if interface is None:
        return ""

    lines: list[str] = []
    is_fb = pou_type == "functionBlock"

    for section_tag, section_kw in VAR_SECTIONS:
        if section_tag == "globalVars":
            continue
        section = interface.find(f"{{{NS}}}{section_tag}")
        if section is None:
            continue
        vars_list = section.findall(f"{{{NS}}}variable")
        if not vars_list:
            continue

        if section_tag == "localVars" and is_fb:
            kw = "VAR"
        elif section_tag == "localVars":
            kw = "VAR"
        else:
            kw = section_kw

        lines.append(f"{kw}")
        for var in vars_list:
            lines.append(format_variable(var))
        lines.append(f"END_VAR")
        lines.append("")

    return "\n".join(lines).rstrip()


def extract_st_body(pou: ET.Element) -> str:
    body = pou.find(f"{{{NS}}}body")
    if body is None:
        return ""
    st = body.find(f".//{{{NS}}}ST")
    if st is None:
        return ""
    for xhtml in st.iter():
        if strip_ns(xhtml.tag) == "xhtml" or xhtml.tag.endswith("xhtml"):
            raw = text_content(xhtml)
            if raw:
                return html.unescape(raw)
    return text_content(st)


def format_pou(pou: ET.Element) -> str:
    name = pou.get("name", "")
    pou_type = pou.get("pouType", "program")
    obj_id = get_object_id(pou) or ""

    header = [
        f"# kind={pou_type}",
        f"# name={name}",
    ]
    if obj_id:
        header.append(f"# objectId={obj_id}")

    iface = format_interface(pou.find(f"{{{NS}}}interface"), pou_type)
    st = extract_st_body(pou)

    parts = header + [""]
    if iface:
        parts.append(iface)
        parts.append("")
    parts.append("// --- implementation (ST) ---")
    parts.append(st if st else "// (empty)")
    return "\n".join(parts) + "\n"


def format_gvl(gvl: ET.Element) -> str:
    name = gvl.get("name", "")
    retain = gvl.get("retain", "false")
    persistent = gvl.get("persistent", "false")
    obj_id = get_object_id(gvl) or ""

    header = [
        "# kind=gvl",
        f"# name={name}",
        f"# retain={retain}",
        f"# persistent={persistent}",
    ]
    if obj_id:
        header.append(f"# objectId={obj_id}")

    lines = header + ["", "VAR_GLOBAL"]
    for var in gvl.findall(f"{{{NS}}}variable"):
        lines.append(format_variable(var, global_style=True))
    lines.append("END_VAR")
    return "\n".join(lines) + "\n"


def format_struct(dtype: ET.Element) -> str:
    name = dtype.get("name", "")
    obj_id = get_object_id(dtype) or ""
    struct = dtype.find(f".//{{{NS}}}struct")
    if struct is None:
        return ""

    header = ["# kind=struct", f"# name={name}"]
    if obj_id:
        header.append(f"# objectId={obj_id}")

    lines = header + ["", f"TYPE {name} :", "STRUCT"]
    for var in struct.findall(f"{{{NS}}}variable"):
        doc = find_xhtml_doc(var)
        comment = f" // {doc}" if doc else ""
        iec_type = type_to_iec(var.find(f"{{{NS}}}type"))
        init = var.find(f"{{{NS}}}initialValue/{{{NS}}}simpleValue")
        init_s = ""
        if init is not None and init.get("value") is not None:
            init_s = f" := {init.get('value')}"
        lines.append(f"    {var.get('name')} : {iec_type}{init_s};{comment}")
    lines.extend(["END_STRUCT", "END_TYPE"])
    return "\n".join(lines) + "\n"


def format_enum(dtype: ET.Element) -> str:
    name = dtype.get("name", "")
    obj_id = get_object_id(dtype) or ""
    enum = dtype.find(f".//{{{NS}}}enum")
    if enum is None:
        return ""

    header = ["# kind=enum", f"# name={name}"]
    if obj_id:
        header.append(f"# objectId={obj_id}")

    doc_map: dict[str, str] = {}
    for data in dtype.findall(f".//{{{NS}}}addData/{{{NS}}}data"):
        if data.get("name", "").endswith("enumvaluedocumentation"):
            for ev in data.iter():
                if strip_ns(ev.tag) == "EnumValue":
                    n_el = None
                    d_el = None
                    for c in ev:
                        if strip_ns(c.tag) == "Name":
                            n_el = c
                        elif strip_ns(c.tag) == "Documentation":
                            d_el = c
                    if n_el is not None:
                        doc_map[text_content(n_el)] = find_xhtml_doc(ev) if d_el is not None else ""

    values = enum.findall(f"{{{NS}}}values/{{{NS}}}value")
    parts = []
    for v in values:
        vn = v.get("name", "")
        vv = v.get("value", "0")
        doc = doc_map.get(vn, "")
        comment = f" // {doc}" if doc else ""
        parts.append(f"    {vn} := {vv}{comment}")

    lines = header + ["", f"TYPE {name} : ("]
    lines.append(",\n".join(parts))
    lines.append(");")
    lines.append("END_TYPE")
    return "\n".join(lines) + "\n"


def format_union(union: ET.Element) -> str:
    name = union.get("name", "")
    obj_id = get_object_id(union) or ""

    header = ["# kind=union", f"# name={name}"]
    if obj_id:
        header.append(f"# objectId={obj_id}")

    lines = header + ["", f"TYPE {name} :", "UNION"]
    for var in union.findall(f"{{{NS}}}variable"):
        doc = find_xhtml_doc(var)
        comment = f" // {doc}" if doc else ""
        iec_type = type_to_iec(var.find(f"{{{NS}}}type"))
        lines.append(f"    {var.get('name')} : {iec_type};{comment}")
    lines.extend(["END_UNION", "END_TYPE"])
    return "\n".join(lines) + "\n"


def format_task(task: ET.Element) -> str:
    name = task.get("name", "")
    interval = task.get("interval", "")
    priority = task.get("priority", "")
    obj_id = get_object_id(task) or ""

    pou_instances = []
    for pi in task.findall(f"{{{NS}}}pouInstance"):
        pou_instances.append(pi.get("name", ""))

    interval_ms = ""
    for data in task.findall(f".//{{{NS}}}addData/{{{NS}}}data"):
        if "tasksettings" in (data.get("name") or ""):
            ts = data.find(".//{*}TaskSettings")
            if ts is not None:
                interval_ms = ts.get("Interval", "")
                unit = ts.get("IntervalUnit", "ms")

    header = [
        "# kind=task",
        f"# name={name}",
        f"# interval={interval}",
        f"# priority={priority}",
    ]
    if interval_ms:
        header.append(f"# intervalSetting={interval_ms}{unit}")
    if obj_id:
        header.append(f"# objectId={obj_id}")

    lines = header + ["", "# bound POUs:"]
    if pou_instances:
        for p in pou_instances:
            lines.append(f"#   - {p}")
    else:
        lines.append("#   (none)")
    return "\n".join(lines) + "\n"


def format_placeholder(name: str, note: str, obj_id: str = "") -> str:
    lines = [
        "# kind=device_node",
        f"# name={name}",
        "# source=projectstructure_only",
    ]
    if obj_id:
        lines.append(f"# objectId={obj_id}")
    lines.extend(["", f"# note={note}"])
    return "\n".join(lines) + "\n"


def parse_project_structure(root: ET.Element) -> ET.Element | None:
    for elem in root.iter():
        if strip_ns(elem.tag) == "ProjectStructure":
            return elem
    return None


def _child_nodes(node: ET.Element) -> list[ET.Element]:
    return [c for c in node if strip_ns(c.tag) in ("Folder", "Object")]


def walk_structure(
    node: ET.Element,
    base_path: Path,
    ctx: "ExportContext",
    stats: dict,
) -> None:
    tag = strip_ns(node.tag)
    if tag == "Folder":
        folder_name = node.get("Name", "Folder")
        folder_path = base_path / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        for child in _child_nodes(node):
            walk_structure(child, folder_path, ctx, stats)
        return

    if tag != "Object":
        return

    name = node.get("Name", "")
    children = _child_nodes(node)

    if children:
        if name in ("Device",):
            child_base = base_path
        else:
            child_base = base_path / name
            child_base.mkdir(parents=True, exist_ok=True)
        for child in children:
            walk_structure(child, child_base, ctx, stats)
        return

    obj_id = node.get("ObjectId", "")

    if name in TASK_NAMES:
        out_path = base_path / "_tasks" / f"{name}.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        content = ctx.tasks.get(name)
        if content:
            out_path.write_text(content, encoding="utf-8")
            stats["tasks"] += 1
        else:
            out_path.write_text(
                format_placeholder(name, "Task definition not found in XML.", obj_id),
                encoding="utf-8",
            )
            stats["placeholders"] += 1
        return

    out_path = base_path / f"{name}.txt"

    if name in ctx.pous:
        out_path.write_text(ctx.pous[name], encoding="utf-8")
        stats["pous"] += 1
        return

    if name in ctx.gvl:
        out_path.write_text(ctx.gvl[name], encoding="utf-8")
        stats["gvl"] += 1
        return

    if name in ctx.datatypes:
        out_path.write_text(ctx.datatypes[name], encoding="utf-8")
        stats["dut"] += 1
        return

    if name in ctx.unions:
        out_path.write_text(ctx.unions[name], encoding="utf-8")
        stats["union"] += 1
        return

    if name in MISSING_DUT_PLACEHOLDER:
        out_path.write_text(
            format_placeholder(
                name,
                "类型在工程树中存在，但本次 PLCopen 导出未包含定义体。请从 CODESYS 补导出或手工维护。",
                obj_id,
            ),
            encoding="utf-8",
        )
        stats["missing_dut"] += 1
        return

    if name in DEVICE_PLACEHOLDER_NAMES or name == "Device":
        if name == "Device":
            return  # root container, no file
        note = {
            "库管理器": "库管理器节点；引用库列表见 README.txt / Application 库配置。",
            "GCAN_IoDrv": "GCAN IO 驱动设备配置，请在 CODESYS 设备编辑器中查看。",
            "GCAN_IoMDP": "GCAN IO 模块配置占位。",
            "GC5016_Digital_Input_Output": "GC5016 数字量 IO 模块配置占位。",
            "CANbus": "CAN 总线设备配置占位。",
            "CANopen_Manager": "CANopen 管理器配置占位。",
            "eDriver_El": "CANopen 从站 eDriver_El（俯仰轴）设备配置。",
            "eDriver_Az": "CANopen 从站 eDriver_Az（方位轴）设备配置。",
            "eDriver_Ti": "CANopen 从站 eDriver_Ti（倾斜轴）设备配置。",
            "SoftMotion General Axis Pool": "SoftMotion 轴池配置占位。",
        }.get(name, "设备/配置节点，PLCopen 导出未包含详细配置。")
        out_path.write_text(format_placeholder(name, note, obj_id), encoding="utf-8")
        stats["placeholders"] += 1
        return

    out_path.write_text(
        format_placeholder(name, "工程树对象，无匹配的 POU/GVL/DUT 导出内容。", obj_id),
        encoding="utf-8",
    )
    stats["placeholders"] += 1


class ExportContext:
    def __init__(self) -> None:
        self.pous: dict[str, str] = {}
        self.gvl: dict[str, str] = {}
        self.datatypes: dict[str, str] = {}
        self.unions: dict[str, str] = {}
        self.tasks: dict[str, str] = {}
        self.libraries: list[str] = []
        self.project_name = ""
        self.codesys_version = ""
        self.creation_date = ""


def index_xml(root: ET.Element) -> ExportContext:
    ctx = ExportContext()

    fh = root.find(f"{{{NS}}}fileHeader")
    if fh is not None:
        ctx.codesys_version = fh.get("productVersion", "")
        ctx.creation_date = fh.get("creationDateTime", "")

    ch = root.find(f"{{{NS}}}contentHeader")
    if ch is not None:
        ctx.project_name = ch.get("name", "")

    for pou in root.iter(f"{{{NS}}}pou"):
        name = pou.get("name")
        if name:
            ctx.pous[name] = format_pou(pou)

    for gvl in root.iter(f"{{{NS}}}globalVars"):
        name = gvl.get("name")
        if name:
            ctx.gvl[name] = format_gvl(gvl)

    for dtype in root.iter(f"{{{NS}}}dataType"):
        name = dtype.get("name")
        if not name:
            continue
        if dtype.find(f".//{{{NS}}}struct") is not None:
            ctx.datatypes[name] = format_struct(dtype)
        elif dtype.find(f".//{{{NS}}}enum") is not None:
            ctx.datatypes[name] = format_enum(dtype)

    for union in root.iter(f"{{{NS}}}union"):
        name = union.get("name")
        if name:
            ctx.unions[name] = format_union(union)

    for task in root.iter(f"{{{NS}}}task"):
        name = task.get("name")
        if name:
            ctx.tasks[name] = format_task(task)

    for lib in root.iter():
        if strip_ns(lib.tag) == "Library":
            nm = lib.get("Name", "")
            res = lib.get("DefaultResolution", "")
            if nm:
                ctx.libraries.append(f"{nm} -> {res}" if res else nm)

    return ctx


def write_readme(out_dir: Path, ctx: ExportContext, stats: dict, xml_path: Path) -> None:
    lines = [
        "plc-src export index",
        "====================",
        "",
        f"Source XML: {xml_path.name}",
        f"Project: {ctx.project_name}",
        f"CODESYS: {ctx.codesys_version}",
        f"Export time (from XML): {ctx.creation_date}",
        "",
        "Statistics:",
        f"  POUs: {stats['pous']}",
        f"  GVL: {stats['gvl']}",
        f"  DUT (struct/enum): {stats['dut']}",
        f"  UNION types: {stats['union']}",
        f"  Tasks: {stats['tasks']}",
        f"  Placeholders: {stats['placeholders']}",
        f"  Missing DUT placeholders: {stats['missing_dut']}",
        "",
    ]

    if MISSING_DUT_PLACEHOLDER:
        lines.append("Missing type definitions (not in PLCopen XML):")
        for n in sorted(MISSING_DUT_PLACEHOLDER):
            lines.append(f"  - {n}")
        lines.append("")
    else:
        lines.append(
            "Note: Word2Bit, Dword2Bit, float2bit, UnionLREAL_WORD, Time2Word "
            "are exported as UNION types from XML."
        )
        lines.append("")

    lines.append("VisuElems.Visu_Prg: bound in VISU_TASK only (system library visu).")
    lines.append("")
    lines.append("Libraries (summary):")
    seen = set()
    for lib in ctx.libraries:
        if lib not in seen:
            seen.add(lib)
            lines.append(f"  - {lib}")
    lines.append("")
    lines.append("Regenerate: python scripts/export_plcopen_to_txt.py")

    (out_dir / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def find_xml(input_dir: Path) -> Path:
    xmls = list(input_dir.glob("*.xml"))
    if not xmls:
        raise FileNotFoundError(f"No .xml in {input_dir}")
    if len(xmls) == 1:
        return xmls[0]
    # prefer largest (main export)
    return max(xmls, key=lambda p: p.stat().st_size)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export PLCopen XML to plc-src txt tree")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "codesys-export",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "plc-src",
    )
    args = parser.parse_args()

    xml_path = find_xml(args.input_dir)
    tree = ET.parse(xml_path)
    root = tree.getroot()

    ctx = index_xml(root)
    ps = parse_project_structure(root)
    if ps is None:
        print("ERROR: ProjectStructure not found", file=sys.stderr)
        return 1

    out_dir = args.output_dir
    preserved_root_docs: list[tuple[Path, bytes]] = []
    if out_dir.exists():
        import shutil

        for doc in out_dir.glob("*.md"):
            preserved_root_docs.append((doc, doc.read_bytes()))
        shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)
        for doc, data in preserved_root_docs:
            doc.write_bytes(data)
    device_root = out_dir / "Device"
    device_root.mkdir(parents=True)

    stats = {
        "pous": 0,
        "gvl": 0,
        "dut": 0,
        "union": 0,
        "tasks": 0,
        "placeholders": 0,
        "missing_dut": 0,
    }

    for child in ps:
        if strip_ns(child.tag) != "Object":
            continue
        if child.get("Name") == "Device":
            for sub in _child_nodes(child):
                walk_structure(sub, device_root, ctx, stats)
        else:
            walk_structure(child, device_root, ctx, stats)

    write_readme(out_dir, ctx, stats, xml_path)

    print(f"Exported to {out_dir}")
    print(f"  POUs: {stats['pous']} (indexed {len(ctx.pous)})")
    print(f"  GVL: {stats['gvl']} (indexed {len(ctx.gvl)})")
    print(f"  DUT: {stats['dut']} (indexed {len(ctx.datatypes)})")
    print(f"  UNION: {stats['union']} (indexed {len(ctx.unions)})")
    print(f"  Tasks: {stats['tasks']}")
    print(f"  Placeholders: {stats['placeholders']}")

    expected_pous = 33
    if stats["pous"] != expected_pous:
        print(
            f"WARNING: expected {expected_pous} POU files, wrote {stats['pous']}",
            file=sys.stderr,
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
