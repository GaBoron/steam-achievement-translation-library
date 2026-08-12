"""Binary KeyValues parsing and Steam achievement schema validation."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


TYPE_NAMES = {0: "BEGIN", 1: "STRING", 2: "INT32", 3: "FLOAT32", 4: "POINTER", 5: "WIDESTRING", 6: "COLOR", 7: "UINT64", 8: "END"}


@dataclass
class Node:
    type_id: int
    name: str
    children: list["Node"] = field(default_factory=list)
    value: str | None = None
    raw_value: bytes = b""


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def u8(self) -> int:
        if self.pos >= len(self.data):
            raise EOFError("unexpected EOF reading node type")
        value = self.data[self.pos]
        self.pos += 1
        return value

    def bytes(self, size: int) -> bytes:
        if self.pos + size > len(self.data):
            raise EOFError("unexpected EOF reading node value")
        value = self.data[self.pos:self.pos + size]
        self.pos += size
        return value

    def cbytes(self) -> bytes:
        end = self.data.find(b"\0", self.pos)
        if end < 0:
            raise EOFError("unterminated string")
        value = self.data[self.pos:end]
        self.pos = end + 1
        return value

    def cstr(self) -> str:
        return self.cbytes().decode("utf-8")


def parse_nodes(reader: Reader) -> list[Node]:
    nodes: list[Node] = []
    while True:
        type_id = reader.u8()
        if type_id == 8:
            return nodes
        if type_id not in TYPE_NAMES:
            raise ValueError(f"unknown Binary KeyValues node type {type_id} at offset {reader.pos - 1}")
        name = reader.cstr()
        node = Node(type_id, name)
        if type_id == 0:
            node.children = parse_nodes(reader)
        elif type_id == 1:
            raw = reader.cbytes()
            node.raw_value = raw
            node.value = raw.decode("utf-8")
        elif type_id in (2, 3, 4, 6):
            node.raw_value = reader.bytes(4)
        elif type_id == 7:
            node.raw_value = reader.bytes(8)
        elif type_id == 5:
            raise NotImplementedError("WideString nodes are not supported by the review parser")
        nodes.append(node)


def cstr(value: str) -> bytes:
    return value.encode("utf-8") + b"\0"


def serialize(nodes: list[Node]) -> bytes:
    output = bytearray()
    for node in nodes:
        output.append(node.type_id)
        output.extend(cstr(node.name))
        if node.type_id == 0:
            output.extend(serialize(node.children))
        elif node.type_id == 1:
            output.extend(cstr(node.value if node.value is not None else node.raw_value.decode("utf-8")))
        elif node.type_id in (2, 3, 4, 6, 7):
            output.extend(node.raw_value)
        else:
            raise NotImplementedError(f"cannot serialize Binary KeyValues node type {node.type_id}")
    output.append(8)
    return bytes(output)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def walk(nodes: list[Node]):
    for node in nodes:
        yield node
        if node.children:
            yield from walk(node.children)


def begins(node: Node, name: str) -> list[Node]:
    return [child for child in node.children if child.type_id == 0 and child.name == name]


def strings(node: Node, name: str) -> list[Node]:
    return [child for child in node.children if child.type_id == 1 and child.name == name]


def first_str(node: Node, name: str) -> str:
    matches = strings(node, name)
    return (matches[0].value or "") if matches else ""


def nested(node: Node, *names: str) -> Node | None:
    current: Node | None = node
    for name in names:
        if current is None:
            return None
        matches = begins(current, name)
        current = matches[0] if matches else None
    return current


def achievement_nodes(nodes: list[Node]) -> list[Node]:
    output: list[Node] = []
    for bits in [node for node in walk(nodes) if node.type_id == 0 and node.name == "bits"]:
        for child in bits.children:
            if child.type_id == 0 and strings(child, "name") and nested(child, "display", "name") and nested(child, "display", "desc"):
                output.append(child)
    return output


def load_schema(path: Path) -> tuple[bytes, list[Node]]:
    data = path.read_bytes()
    reader = Reader(data)
    nodes = parse_nodes(reader)
    if reader.pos != len(data):
        raise ValueError(f"parser stopped at offset {reader.pos}, file size is {len(data)}")
    return data, nodes


def validate_schema_structure(data: bytes, nodes: list[Node]) -> list[dict[str, str]]:
    """Validate invariants that every accepted schema must preserve."""
    if data != serialize(nodes):
        raise ValueError("schema 无法通过 Binary KeyValues 解析器保持字节级 roundtrip")
    rows = achievement_rows(nodes, [])
    if not rows:
        raise ValueError("schema 中没有找到 Steam 成就名称/描述记录")
    achievement_ids = [row.get("api_name", "") for row in rows]
    if any(not achievement_id for achievement_id in achievement_ids):
        raise ValueError("每个成就都必须有非空的 API name")
    if len(set(achievement_ids)) != len(achievement_ids):
        raise ValueError("成就 API name 必须唯一")
    return rows


def require_language_coverage(
    rows: list[dict[str, str]],
    languages: list[str],
) -> dict[str, int]:
    coverage, missing = language_coverage(rows, languages)
    missing_messages: list[str] = []
    for language, missing_ids in missing.items():
        if missing_ids:
            preview = ", ".join(missing_ids[:10])
            suffix = " ..." if len(missing_ids) > 10 else ""
            missing_messages.append(f"{language}: 缺少 {len(missing_ids)} 个成就文本：{preview}{suffix}")
    if missing_messages:
        raise ValueError("schema 语言覆盖不完整。" + "；".join(missing_messages))
    return coverage


def achievement_rows(nodes: list[Node], languages: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, achievement in enumerate(achievement_nodes(nodes), 1):
        display_name = nested(achievement, "display", "name")
        display_desc = nested(achievement, "display", "desc")
        if display_name is None or display_desc is None:
            continue
        row = {
            "index": str(index),
            "node_key": achievement.name,
            "api_name": first_str(achievement, "name"),
            "english_name": first_str(display_name, "english"),
            "english_description": first_str(display_desc, "english"),
        }
        for language in languages:
            row[f"{language}_name"] = first_str(display_name, language)
            row[f"{language}_description"] = first_str(display_desc, language)
        rows.append(row)
    return rows


def language_coverage(rows: list[dict[str, str]], languages: list[str]) -> tuple[dict[str, int], dict[str, list[str]]]:
    coverage: dict[str, int] = {}
    missing: dict[str, list[str]] = {}
    for language in languages:
        def is_complete(row: dict[str, str]) -> bool:
            name_present = bool(row.get(f"{language}_name", "").strip())
            description_present = bool(row.get(f"{language}_description", "").strip())
            original_has_description = bool(row.get("english_description", "").strip())
            # Some games intentionally define achievements with a name only.
            return name_present and (description_present or not original_has_description)

        present = [
            row for row in rows
            if is_complete(row)
        ]
        coverage[language] = len(present)
        missing[language] = [
            row.get("api_name", "")
            for row in rows
            if not is_complete(row)
        ]
    return coverage, missing


def row_map(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row.get("api_name", ""): row for row in rows if row.get("api_name", "")}


def summarize_update_diff(old_rows: list[dict[str, str]], new_rows: list[dict[str, str]], languages: list[str]) -> dict[str, Any]:
    old_by_id = row_map(old_rows)
    new_by_id = row_map(new_rows)
    old_ids = set(old_by_id)
    new_ids = set(new_by_id)
    compare_keys = ["english_name", "english_description"]
    for language in languages:
        compare_keys.extend([f"{language}_name", f"{language}_description"])
    changed: list[dict[str, Any]] = []
    for achievement_id in sorted(old_ids & new_ids):
        field_changes = []
        for key in compare_keys:
            old_value = old_by_id[achievement_id].get(key, "")
            new_value = new_by_id[achievement_id].get(key, "")
            if old_value != new_value:
                field_changes.append({
                    "field": key,
                    "old": old_value,
                    "new": new_value,
                })
        if field_changes:
            changed.append({"id": achievement_id, "fields": field_changes})
    return {
        "added": sorted(new_ids - old_ids),
        "deleted": sorted(old_ids - new_ids),
        "changed": changed,
    }
