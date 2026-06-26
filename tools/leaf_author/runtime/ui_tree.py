from __future__ import annotations

import json
from typing import Any


def parse_layout(raw_layout: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_layout)
    except json.JSONDecodeError:
        return {"attributes": {}, "children": [], "parse_error": "JSON_DECODE_ERROR", "raw_excerpt": raw_layout[:2000]}
    return payload if isinstance(payload, dict) else {"attributes": {}, "children": [], "parse_error": "ROOT_NOT_OBJECT"}


def build_index(tree: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    for node_id, attributes in enumerate(_iter_attributes(tree)):
        indexed = _indexed_node(f"n{node_id}", attributes)
        nodes.append(indexed)
    foreground = _foreground(nodes)
    return {
        "schema_version": "1.0",
        "foreground": foreground,
        "node_count": len(nodes),
        "clickable_count": sum(1 for node in nodes if node["clickable"]),
        "nodes": nodes,
    }


def find_candidates(index: dict[str, Any], selectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for node in index.get("nodes", []):
        if not isinstance(node, dict):
            continue
        matched = _matched_selectors(node, selectors)
        if matched:
            candidates.append({**node, "score": len(matched), "matched": matched})
    candidates.sort(key=lambda node: (-int(node["score"]), str(node.get("node_id", ""))))
    return candidates


def diff_indexes(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_ids = _stable_ids(before)
    after_ids = _stable_ids(after)
    before_foreground = before.get("foreground", {})
    after_foreground = after.get("foreground", {})
    return {
        "schema_version": "1.0",
        "before_foreground": before_foreground,
        "after_foreground": after_foreground,
        "foreground_changed": before_foreground != after_foreground,
        "before_node_count": int(before.get("node_count", 0)),
        "after_node_count": int(after.get("node_count", 0)),
        "node_count_delta": int(after.get("node_count", 0)) - int(before.get("node_count", 0)),
        "added_node_ids": sorted(after_ids - before_ids),
        "removed_node_ids": sorted(before_ids - after_ids),
    }


def _iter_attributes(node: Any):
    if not isinstance(node, dict):
        return
    attributes = node.get("attributes", {})
    if isinstance(attributes, dict):
        yield attributes
    children = node.get("children", [])
    if isinstance(children, list):
        for child in children:
            yield from _iter_attributes(child)


def _indexed_node(node_id: str, attributes: dict[str, Any]) -> dict[str, Any]:
    bounds = _parse_bounds(str(attributes.get("bounds") or ""))
    return {
        "node_id": node_id,
        "id": str(attributes.get("id") or attributes.get("key") or ""),
        "type": str(attributes.get("type") or ""),
        "text": str(attributes.get("text") or attributes.get("originalText") or ""),
        "bundle": str(attributes.get("bundleName") or ""),
        "ability": str(attributes.get("abilityName") or ""),
        "clickable": _bool_attr(attributes.get("clickable")),
        "visible": not _bool_attr(attributes.get("invisible")),
        "bounds": bounds,
        "center": _center(bounds),
    }


def _foreground(nodes: list[dict[str, Any]]) -> dict[str, str]:
    for node in nodes:
        if node.get("bundle") or node.get("ability"):
            return {"bundle": str(node.get("bundle", "")), "ability": str(node.get("ability", ""))}
    return {"bundle": "", "ability": ""}


def _matched_selectors(node: dict[str, Any], selectors: list[dict[str, Any]]) -> list[str]:
    matched = []
    for selector in selectors:
        if "id" in selector and selector["id"] and node.get("id") == selector["id"]:
            matched.append("id")
        if "text" in selector and selector["text"] and node.get("text") == selector["text"]:
            matched.append("text")
        if "type" in selector and selector["type"] and node.get("type") == selector["type"]:
            matched.append("type")
        if "clickable" in selector and bool(node.get("clickable")) is bool(selector["clickable"]):
            matched.append("clickable")
    return list(dict.fromkeys(matched))


def _stable_ids(index: dict[str, Any]) -> set[str]:
    values = set()
    for node in index.get("nodes", []):
        if not isinstance(node, dict):
            continue
        stable = str(node.get("id") or node.get("text") or node.get("node_id") or "")
        if stable:
            values.add(stable)
    return values


def _parse_bounds(bounds: str) -> list[int] | None:
    parts = [int(value) for value in bounds.replace("[", ",").replace("]", ",").split(",") if value.strip().lstrip("-").isdigit()]
    return parts if len(parts) == 4 else None


def _center(bounds: list[int] | None) -> dict[str, int] | None:
    if bounds is None:
        return None
    x1, y1, x2, y2 = bounds
    return {"x": (x1 + x2) // 2, "y": (y1 + y2) // 2}


def _bool_attr(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() == "true"
