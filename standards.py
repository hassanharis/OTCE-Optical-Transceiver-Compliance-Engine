"""Resolve a mode into standard records via its identity fields, then read mapped values.

A mode's STANDARDS_IDENTITY_FIELDS (host/media interface names and IDs, operational-mode
code, framing) say *which* record of a standard the mode claims to be. Once that record is
located, every other parameter the crosswalk maps for that standard can be read straight out
of the standard's own dataset, giving the standard's value next to the datasheet's value.

Identifiers are written differently in each source, so all comparisons are made on parsed
integers or on alphanumeric-folded names:

    modes.json  0x64        OpenROADM  "64"        SFF-8024  "64"      OpenZR+  "46h"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STANDARDS_ROOT = Path(r"C:\Haris\Final\Standards")

FALLBACK_IDENTITY_FIELDS = [
    "host_interface_name",
    "host_interface_id_hex",
    "host_interface_id",
    "media_interface_name",
    "media_interface_id_hex",
    "media_interface_id",
    "standards_code",
    "frame",
]

# Words that corroborate a numeric identifier actually belonging to a given standard.
STANDARD_KEYWORDS = {
    "OIF-400ZR": ("400zr", "oif"),
    "OpenZR+": ("openzr", "zr+", "zr400", "zr300", "zr200", "zr100"),
    "OpenROADM": ("openroadm", "or-w-", "flexo", "foic"),
    "SFF-8024": (),
}

_HEX = re.compile(r"^(?:0x)?([0-9a-f]+)h?$", re.IGNORECASE)


def identity_fields() -> list[str]:
    try:
        from transceiver_models import STANDARDS_IDENTITY_FIELDS

        return list(STANDARDS_IDENTITY_FIELDS)
    except Exception:
        return list(FALLBACK_IDENTITY_FIELDS)


def hex_int(value: Any) -> int | None:
    """Parse 0x64 / 64 / 46h / 100 into an integer, treating bare digits as hexadecimal."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    match = _HEX.match(str(value).strip())
    return int(match.group(1), 16) if match else None


def dec_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None


def fold(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def name_match(left: Any, right: Any) -> bool:
    a, b = fold(left), fold(right)
    if len(a) < 4 or len(b) < 4:
        return False
    return a == b or a in b or b in a


def mentions(mode: dict[str, Any], keywords: tuple[str, ...]) -> bool:
    if not keywords:
        return False
    haystack = " ".join(
        str(mode.get(key, "")) for key in ("standards_code", "media_interface_name", "label", "frame")
    ).lower()
    return any(word in haystack for word in keywords)


@dataclass
class Match:
    """One standard record that a mode's identity resolves to."""

    standard: str
    scope: str
    label: str
    record: dict[str, Any]
    evidence: list[str] = field(default_factory=list)
    corroborated: bool = False
    exact_name: bool = False

    @property
    def confidence(self) -> str:
        """A bare identifier is never enough: the same number means different things in
        different registries, so only a name or an explicit standard claim confirms a record."""
        return "corroborated" if self.corroborated else "identifier only"


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------


def load_standards(root: str | Path, standards_index: dict[str, Any]) -> tuple[dict[str, dict], dict[str, str]]:
    """Load each standard dataset named in the crosswalk index. Returns docs and load errors."""
    import json

    base = Path(root)
    docs: dict[str, dict] = {}
    problems: dict[str, str] = {}

    for standard, entry in standards_index.items():
        if standard == "transceiver_specs_fields":
            continue
        candidates = entry.get("paths") or ([entry["path"]] if entry.get("path") else [])
        for relative in candidates:
            path = base / relative
            if not path.is_file():
                continue
            try:
                docs[standard] = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                problems[standard] = f"{relative}: {error}"
            break
        else:
            if candidates:
                problems[standard] = f"file not found: {candidates[0]}"
    return docs, problems


# --------------------------------------------------------------------------------------
# Identity resolution
# --------------------------------------------------------------------------------------


def _match_sff(mode: dict[str, Any], doc: dict[str, Any]) -> list[Match]:
    tables = doc.get("Interfaces", {})
    plans = [
        ("host", "Host Electrical Interface IDs", "host_electrical_interface",
         "host_interface_id_hex", "host_interface_id", "host_interface_name"),
        ("media", "MMF and SMF media interface IDs", "media_interface",
         "media_interface_id_hex", "media_interface_id", "media_interface_name"),
    ]

    matches: list[Match] = []
    for scope, table_name, name_column, hex_field, dec_field, name_field in plans:
        table = tables.get(table_name)
        if not table:
            continue
        wanted_hex = hex_int(mode.get(hex_field))
        wanted_dec = dec_int(mode.get(dec_field))
        wanted_name = mode.get(name_field)

        for row in table.get("rows", []):
            evidence = []
            if wanted_hex is not None and hex_int(row.get("id_hex")) == wanted_hex:
                evidence.append(f"{hex_field} {mode[hex_field]} = id_hex {row.get('id_hex')}")
            if wanted_dec is not None and dec_int(row.get("id")) == wanted_dec:
                evidence.append(f"{dec_field} {mode[dec_field]} = id {row.get('id')}")
            named = wanted_name and name_match(wanted_name, row.get(name_column, ""))
            if named:
                evidence.append(f"{name_field} matches {name_column} '{row.get(name_column)}'")
            if not evidence:
                continue
            matches.append(
                Match(
                    standard="SFF-8024",
                    scope=scope,
                    label=f"{row.get('id_hex')}h {row.get(name_column)}"
                    + (f" ({row['media']})" if row.get("media") else ""),
                    record=row,
                    evidence=evidence,
                    corroborated=bool(named),
                    exact_name=bool(wanted_name) and fold(wanted_name) == fold(row.get(name_column, "")),
                )
            )
    return matches


def _match_openzrplus(mode: dict[str, Any], doc: dict[str, Any]) -> list[Match]:
    wanted_hex = hex_int(mode.get("media_interface_id_hex"))
    wanted_dec = dec_int(mode.get("media_interface_id"))
    wanted_name = mode.get("media_interface_name")
    claims = mentions(mode, STANDARD_KEYWORDS["OpenZR+"])

    matches = []
    for record in doc.get("identity", []):
        evidence = []
        if wanted_hex is not None and hex_int(record.get("sff8024_id_hex")) == wanted_hex:
            evidence.append(f"media_interface_id_hex = sff8024_id_hex {record['sff8024_id_hex']}")
        if wanted_dec is not None and record.get("sff8024_id_decimal") == wanted_dec:
            evidence.append(f"media_interface_id = sff8024_id_decimal {wanted_dec}")
        named = bool(wanted_name) and name_match(wanted_name, record.get("media_interface_id", ""))
        if named:
            evidence.append(f"media_interface_name matches media_interface_id '{record['media_interface_id']}'")
        if not evidence:
            continue
        matches.append(
            Match(
                standard="OpenZR+",
                scope="media",
                label=record.get("media_interface_id", "?"),
                record=record,
                evidence=evidence,
                corroborated=claims or named,
                exact_name=bool(wanted_name) and fold(wanted_name) == fold(record.get("media_interface_id", "")),
            )
        )
    return matches


def openroadm_records(doc: dict[str, Any]) -> list[dict[str, Any]]:
    node = doc.get("input", {}).get("operational-mode-info", {}).get("xponders-pluggables", {})
    records = node.get("xponder-pluggable-openroadm-operational-mode", [])
    return [record for record in records if isinstance(record, dict)]


def _match_openroadm(mode: dict[str, Any], doc: dict[str, Any]) -> list[Match]:
    wanted_hex = hex_int(mode.get("media_interface_id_hex"))
    code = mode.get("standards_code")
    claims = mentions(mode, STANDARD_KEYWORDS["OpenROADM"])

    matches = []
    for record in openroadm_records(doc):
        evidence = []
        if wanted_hex is not None and hex_int(record.get("media-interface-id")) == wanted_hex:
            evidence.append(f"media_interface_id_hex = media-interface-id {record.get('media-interface-id')}")
        mode_id = record.get("openroadm-operational-mode-id", "")
        named = bool(code) and fold(code) == fold(mode_id)
        if named:
            evidence.append(f"standards_code = openroadm-operational-mode-id {mode_id}")
        if not evidence:
            continue
        matches.append(
            Match(
                standard="OpenROADM",
                scope="operational mode",
                label=mode_id or "?",
                record=record,
                evidence=evidence,
                corroborated=claims or named,
                exact_name=named,
            )
        )
    return matches


OIF_CODE_FIELDS = ("media_interface_id_hex", "standards_code")


def _claimed_codes(mode: dict[str, Any]) -> dict[int, list[str]]:
    """Application codes the mode states, as integers, each with the fields that stated it.

    A datasheet puts its application code wherever its own layout suggests: an app-code column
    is extracted into media_interface_id_hex, while prose such as 'Application Code 0x01' is
    extracted into standards_code. Either field can also hold something that is not a code at
    all (a name, a registry ID), which simply parses to nothing here.
    """
    claimed: dict[int, list[str]] = {}
    for name in OIF_CODE_FIELDS:
        raw = mode.get(name)
        for item in raw if isinstance(raw, list) else [raw]:
            code = hex_int(item)
            if code is not None:
                claimed.setdefault(code, []).append(f"{name} {item}")
    return claimed


def _match_oif(mode: dict[str, Any], doc: dict[str, Any]) -> list[Match]:
    """OIF is axis-factored: the 'record' is an application_code, not a row."""
    if not mentions(mode, STANDARD_KEYWORDS["OIF-400ZR"]):
        return []

    claimed = _claimed_codes(mode)
    if not claimed:
        return []

    descriptions = doc.get("meta", {}).get("application_codes", {})
    matches = []
    for code in doc.get("axes", {}).get("application_code", []):
        stated_by = claimed.get(hex_int(code))
        if not stated_by:
            continue
        matches.append(
            Match(
                standard="OIF-400ZR",
                scope="application code",
                label=f"{code} — {descriptions.get(code, '')}".strip(" —"),
                record={"application_code": code},
                evidence=[f"{source} = application_code {code}" for source in stated_by],
                corroborated=True,
            )
        )
    return matches


_MATCHERS = {
    "SFF-8024": _match_sff,
    "OpenZR+": _match_openzrplus,
    "OpenROADM": _match_openroadm,
    "OIF-400ZR": _match_oif,
}


def resolve(mode: dict[str, Any], docs: dict[str, dict]) -> dict[str, list[Match]]:
    """Identity fields of one mode -> the standard records they select."""
    return {
        standard: matcher(mode, docs[standard])
        for standard, matcher in _MATCHERS.items()
        if standard in docs
    }


def usable_matches(
    matches: list[Match], scope: str | None = None, include_uncorroborated: bool = False
) -> list[Match]:
    candidates = [m for m in matches if scope is None or m.scope == scope]
    if not include_uncorroborated:
        candidates = [m for m in candidates if m.corroborated]
    return sorted(candidates, key=lambda m: (not m.corroborated, not m.exact_name, -len(m.evidence)))


SFF_SCOPES = ("host", "media")


def default_selection(
    matches: dict[str, list[Match]], include_uncorroborated: bool = False
) -> dict[str, Any]:
    """Pick the record each standard's values should be read from."""
    selection: dict[str, Any] = {}
    for standard, found in matches.items():
        if standard == "SFF-8024":
            selection[standard] = {
                scope: next(iter(usable_matches(found, scope, include_uncorroborated)), None)
                for scope in SFF_SCOPES
            }
        else:
            selection[standard] = next(iter(usable_matches(found, None, include_uncorroborated)), None)
    return selection


# --------------------------------------------------------------------------------------
# Value extraction
# --------------------------------------------------------------------------------------

_PARENTHETICAL = re.compile(r"\s*\([^)]*\)")


def _get_key(node: Any, key: str) -> Any:
    return node.get(key) if isinstance(node, dict) else None


def _walk(node: Any, path: str) -> Any:
    """Resolve a dotted path. A list is mapped over, so 'a.b' works when 'a' is a list."""
    current = node
    for part in path.split("."):
        part = part.strip()
        if not part:
            return None
        key = part.removesuffix("[*]").removesuffix("[]")
        if isinstance(current, list):
            collected = [_get_key(item, key) for item in current]
            current = [item for item in collected if item is not None]
            if not current:
                return None
        else:
            current = _get_key(current, key)
        if current is None:
            return None
    return current


def _render(value: Any, limit: int = 140) -> str | None:
    import json

    if value is None or value == "" or value == []:
        return None
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            unique = list(dict.fromkeys(str(item) for item in value))
            return ", ".join(unique)
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return f"{len(value)} entries: {rendered}"[:limit]
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:limit]
    return str(value)


def _render_bound(entry: dict[str, Any]) -> str | None:
    if not entry:
        return None
    low, high = entry.get("min"), entry.get("max")
    parts = []
    if low is not None and high is not None:
        parts.append(f"{low} \u2026 {high}")
    elif low is not None:
        parts.append(f"min {low}")
    elif high is not None:
        parts.append(f"max {high}")
    for key in ("expected", "default", "value", "typical", "nominal"):
        if entry.get(key) is not None:
            parts.append(f"{key} {entry[key]}")
    return " ".join(parts) or None


def _alternatives(term: str) -> list[str]:
    """Split a crosswalk term into candidate paths ('a | b', 'a / b', 'a and b')."""
    cleaned = _PARENTHETICAL.sub("", term)
    parts: list[str] = []
    for chunk in re.split(r"\s*\|\s*|\s+and\s+", cleaned):
        if "/" in chunk and "." in chunk:
            prefix, _, tail = chunk.rpartition(".")
            head, *rest = [piece.strip() for piece in tail.split("/")]
            parts.append(f"{prefix}.{head}")
            parts.extend(f"{prefix}.{piece}" for piece in rest)
        else:
            parts.extend(piece.strip() for piece in chunk.split("/") if piece.strip())
    return [part for part in parts if part]


def _oif_value(doc: dict, term: str, code: str) -> tuple[str | None, str | None]:
    for path in _alternatives(term):
        if path.startswith("axes."):
            values = doc.get("axes", {}).get(path.removeprefix("axes."))
            if isinstance(values, list) and code in values:
                return code, "axes"  # this axis is the selected record, not a property of it
            if values is not None:
                return _render(values), "axes"
            continue
        if path.startswith("meta."):
            value = _walk(doc, path)
            if isinstance(value, dict) and code in value:
                return _render(value[code]), "meta"
            if value is not None:
                return _render(value), "meta"
            continue
        spec = doc.get("specifications", {}).get(path)
        if spec is None:
            continue

        base = spec.get("base")
        entries = [base] if isinstance(base, dict) else list(base or [])
        entries += list(spec.get("overrides") or [])

        resolved: dict[str, Any] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            allowed = (entry.get("when") or {}).get("application_code")
            if allowed is None or code in allowed or "ALL" in allowed:
                resolved = entry
        rendered = _render_bound(resolved)
        if rendered is None:
            continue
        unit = spec.get("unit")
        reference = resolved.get("reference") or spec.get("section")
        return f"{rendered} {unit}".strip() if unit else rendered, reference
    return None, None


def _zr_axes(identity: dict[str, Any], mode: dict[str, Any], doc: dict) -> dict[str, Any]:
    axes = doc.get("axes", {})
    assignment = {
        "payload_rate": identity.get("format"),
        "modulation": identity.get("modulation"),
        "power_profile": identity.get("power_class"),
        "add_drop": identity.get("add_drop_type"),
        "grid_GHz": mode.get("channel_spacing_ghz"),
    }
    symbol_rate = identity.get("symbol_rate_GBd")
    if symbol_rate is not None:
        classes = [value for value in axes.get("symbol_rate_G", []) if isinstance(value, (int, float))]
        nearest = min(classes, key=lambda value: abs(value - symbol_rate), default=None)
        if nearest is not None and abs(nearest - symbol_rate) <= 5:
            assignment["symbol_rate_G"] = nearest
    return assignment


def _same_axis_value(actual: Any, allowed: Any) -> bool:
    if isinstance(actual, (int, float)) and isinstance(allowed, (int, float)):
        return abs(float(actual) - float(allowed)) < 1e-6
    try:
        return abs(float(actual) - float(allowed)) < 1e-6
    except (TypeError, ValueError):
        return fold(actual) == fold(allowed)


def _zr_rule_matches(when: dict[str, Any], assignment: dict[str, Any], aliases: dict[str, str]) -> bool:
    for axis, allowed in (when or {}).items():
        axis = aliases.get(axis, axis)
        values = allowed if isinstance(allowed, list) else [allowed]
        if not values or any(str(value).upper() == "ALL" for value in values):
            continue
        actual = assignment.get(axis)
        if actual is None or not any(_same_axis_value(actual, value) for value in values):
            return False
    return True


def _zr_value(doc: dict, term: str, identity: dict | None, assignment: dict) -> tuple[str | None, str | None]:
    aliases = doc.get("when_axis_aliases", {})
    for path in _alternatives(term):
        if path.startswith("identity[]"):
            if identity is None:
                continue
            value = _walk(identity, path.removeprefix("identity[]").lstrip("."))
            if value is not None:
                return _render(value), "identity"
            continue
        if path.startswith("axes."):
            axis = path.removeprefix("axes.")
            value = assignment.get(axis) or doc.get("axes", {}).get(axis)
            if value is not None:
                return _render(value), "axes"
            continue
        if path.startswith("meta."):
            value = _walk(doc, path)
            if value is not None:
                return _render(value), "meta"
            continue

        parameter = doc.get("optical_parameters", {}).get(path)
        if parameter is None:
            continue
        resolved, reference = None, None
        for rule in parameter.get("rules", []):
            if not _zr_rule_matches(rule.get("when", {}), assignment, aliases):
                continue
            if rule.get("role") == "base" and resolved is not None:
                continue
            resolved = rule.get("bound") or {}
            reference = rule.get("reference")
        rendered = _render_bound(resolved or {})
        if rendered is None:
            continue
        unit = (parameter.get("measure") or {}).get("display_unit")
        first_line = (reference or "").splitlines()[0] if reference else None
        return f"{rendered} {unit}".strip() if unit else rendered, first_line
    return None, None


def _openroadm_value(doc: dict, term: str, record: dict | None) -> tuple[str | None, str | None]:
    grid = doc.get("input", {}).get("operational-mode-info", {}).get("grid-parameters", {})
    rendered_parts = []
    for path in _alternatives(term):
        if path.startswith("grid-parameters."):
            value = _walk(grid, path.removeprefix("grid-parameters."))
        elif record is None:
            continue
        else:
            value = _walk(record, path)
        rendered = _render(value)
        if rendered is not None:
            leaf = path.rsplit(".", 1)[-1]
            rendered_parts.append(f"{leaf} {rendered}" if len(_alternatives(term)) > 1 else rendered)
    if not rendered_parts:
        return None, None
    return " | ".join(dict.fromkeys(rendered_parts)), record.get("openroadm-operational-mode-id") if record else None


def _sff_value(term: str, rows: dict[str, dict | None]) -> tuple[str | None, str | None]:
    lowered = term.lower()
    scope = "host" if "host electrical" in lowered else "media" if "mmf and smf" in lowered else None
    order = [scope] if scope else ["media", "host"]

    leaves = [path.rsplit(".", 1)[-1].removesuffix("[]") for path in _alternatives(term)]
    if "hex" in lowered:  # 'rows[].id | id_hex' must not answer a hex concept with the decimal id
        leaves.sort(key=lambda leaf: "hex" not in leaf)

    for candidate in order:
        row = rows.get(candidate)
        if not row:
            continue
        for leaf in leaves:
            rendered = _render(row.get(leaf))
            if rendered is not None:
                return rendered, f"{candidate} row {row.get('id_hex')}h"
    return None, None


def standard_value(
    standard: str,
    term: str,
    docs: dict[str, dict],
    selection: dict[str, Any],
    mode: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Read one standard's value for one crosswalk term, in the context of the selected record."""
    doc = docs.get(standard)
    chosen = selection.get(standard)
    if doc is None or not term or chosen is None:
        return None, None

    if standard == "OIF-400ZR":
        return _oif_value(doc, term, chosen.record["application_code"])

    if standard == "OpenZR+":
        identity = chosen.record
        return _zr_value(doc, term, identity, _zr_axes(identity, mode, doc))

    if standard == "OpenROADM":
        return _openroadm_value(doc, term, chosen.record)

    if standard == "SFF-8024":
        rows = {scope: (match.record if match else None) for scope, match in chosen.items()}
        return _sff_value(term, rows) if any(rows.values()) else (None, None)

    return None, None


def compare_mode(
    mode: dict[str, Any],
    taxonomy: dict[str, Any],
    docs: dict[str, dict],
    selection: dict[str, Any],
    standards: list[str],
):
    """Concept-by-concept table of the mode's value beside each standard's value."""
    import pandas as pd

    rows, details = [], []
    for concept in taxonomy["concepts"]:
        fields = [entry["field"] for entry in concept.get("transceiver_specs_fields", [])]
        present = [name for name in fields if mode.get(name) is not None]
        mode_value = (
            "; ".join(
                f"{name} {_render(mode[name])}" if len(present) > 1 else _render(mode[name]) for name in present
            )
            or None
        )

        values: dict[str, str | None] = {}
        for mapping in concept.get("mappings", []):
            standard = mapping["standard_id"]
            if standard not in standards:
                continue
            value, reference = standard_value(standard, mapping.get("term", ""), docs, selection, mode)
            if value is None:
                continue
            values[standard] = value
            details.append(
                {
                    "concept": concept["canonical_id"],
                    "standard": standard,
                    "term": mapping.get("term"),
                    "value": value,
                    "unit": mapping.get("unit"),
                    "reference": mapping.get("reference") or reference,
                    "measurement bandwidth": mapping.get("measurement_bandwidth"),
                    "notes": mapping.get("notes") or concept.get("notes"),
                }
            )

        if mode_value is None and not values:
            continue
        row = {
            "concept": concept["canonical_id"],
            "SI unit": concept.get("si_unit"),
            "mode parameter": ", ".join(present) or None,
            "mode value": mode_value,
        }
        row.update({standard: values.get(standard) for standard in standards})
        rows.append(row)

    columns = ["concept", "SI unit", "mode parameter", "mode value", *standards]
    return pd.DataFrame(rows, columns=columns), pd.DataFrame(details)


COMPARISON = "comparison"
ENRICHMENT = "enrichment"
MODE_ONLY = "datasheet only"


def split_values(wide, standards: list[str]) -> dict[str, Any]:
    """Group the mapped concepts by which side of the comparison actually stated a value.

    A concept only carries a claim about conformance when both sides answered it; the rest
    is either the standard filling in what the datasheet left out, or the reverse.
    """
    import pandas as pd

    from_mode = wide["mode value"].notna()
    from_standard = (
        wide[standards].notna().any(axis=1) if standards else pd.Series(False, index=wide.index, dtype=bool)
    )
    return {
        COMPARISON: wide[from_mode & from_standard],
        ENRICHMENT: wide[~from_mode & from_standard],
        MODE_ONLY: wide[from_mode & ~from_standard],
    }


def by_standard(wide, detail, standard: str):
    """One standard on its own: only what it defines, beside the mode's value for the same concept."""
    import pandas as pd

    if detail.empty or wide.empty:
        return pd.DataFrame()
    rows = detail[(detail["standard"] == standard) & detail["concept"].isin(set(wide["concept"]))]
    if rows.empty:
        return pd.DataFrame()

    parameters = dict(zip(wide["concept"], wide["mode parameter"]))
    mode_values = dict(zip(wide["concept"], wide["mode value"]))

    frame = pd.DataFrame(
        {
            "parameter": rows["concept"].tolist(),
            "mode parameter": [parameters.get(key) for key in rows["concept"]],
            "mode value": [mode_values.get(key) for key in rows["concept"]],
            standard: rows["value"].tolist(),
            "unit": rows["unit"].tolist(),
            "measurement bandwidth": rows["measurement bandwidth"].tolist(),
            "term": rows["term"].tolist(),
            "reference": rows["reference"].tolist(),
        }
    )
    if frame["reference"].nunique(dropna=True) <= 1:
        # A single shared reference is just the matched record, which the caller already names.
        frame = frame.drop(columns="reference")
    return frame.dropna(axis="columns", how="all")


def resolved_standards(selection: dict[str, Any]) -> list[str]:
    """Standards whose selection actually landed on a record."""
    names = []
    for standard, chosen in selection.items():
        if isinstance(chosen, dict):
            if any(chosen.values()):
                names.append(standard)
        elif chosen is not None:
            names.append(standard)
    return names


def selection_label(standard: str, chosen: Any) -> str:
    if chosen is None:
        return "no record"
    if isinstance(chosen, dict):
        parts = [f"{scope}: {match.label}" for scope, match in chosen.items() if match]
        return " · ".join(parts) or "no record"
    return chosen.label
