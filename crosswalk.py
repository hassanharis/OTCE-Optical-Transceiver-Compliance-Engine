"""Route datasheet parameters through the standards cross-reference taxonomy.

The crosswalk links each physical quantity to a vocabulary-neutral concept, and each
concept carries the term used by every standard plus the datasheet extraction fields.
Those datasheet fields are exactly the parameter names that appear in modes.json, so a
mode parameter can be routed to its equivalents in OIF-400ZR, OpenZR+, OpenROADM,
SFF-8024 and ITU-T.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

DEFAULT_CROSSWALK = Path(r"C:\Haris\Final\Standards\_crosswalk\parameter_taxonomy.crosswalk.json")
DATASHEET_ID = "transceiver_specs_fields"

_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def load_crosswalk(path: str | Path) -> tuple[dict[str, Any], bool]:
    """Return the crosswalk document and whether trailing commas had to be repaired."""
    raw = Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(raw), False
    except json.JSONDecodeError:
        return json.loads(_TRAILING_COMMA.sub(r"\1", raw)), True


def standard_ids(data: dict[str, Any]) -> list[str]:
    """Standards in index order, followed by any others that only appear in mappings."""
    indexed = [key for key in data.get("standards_index", {}) if key != DATASHEET_ID]
    referenced = {mapping["standard_id"] for concept in data["concepts"] for mapping in concept.get("mappings", [])}
    return indexed + sorted(referenced - set(indexed))


def standard_names(data: dict[str, Any]) -> dict[str, str]:
    return {key: value.get("name", key) for key, value in data.get("standards_index", {}).items()}


def field_index(data: dict[str, Any]) -> dict[str, list[tuple[dict[str, Any], str | None]]]:
    """Map each datasheet field to every concept claiming it, with the role it plays there.

    More than one concept may claim the same field; keeping them all stops a later concept
    from silently hiding an earlier one's route to a standard.
    """
    index: dict[str, list[tuple[dict[str, Any], str | None]]] = {}
    for concept in data["concepts"]:
        for entry in concept.get("transceiver_specs_fields", []):
            index.setdefault(entry["field"], []).append((concept, entry.get("role")))
    return index


def _terms(concept: dict[str, Any], standard: str, with_units: bool) -> str | None:
    terms = []
    for mapping in concept.get("mappings", []):
        if mapping["standard_id"] != standard:
            continue
        term = mapping.get("term") or mapping.get("source_path") or mapping.get("field")
        unit = mapping.get("unit")
        terms.append(f"{term} [{unit}]" if with_units and unit else term)
    return " | ".join(t for t in terms if t) or None


def route_parameters(
    data: dict[str, Any],
    parameters: list[str],
    with_units: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    """One row per datasheet parameter, one column per standard. Also returns unroutable names."""
    index = field_index(data)
    standards = standard_ids(data)

    rows, unmapped = [], []
    for name in parameters:
        claims = index.get(name)
        if not claims:
            unmapped.append(name)
            continue
        for concept, role in claims:
            row = {
                "parameter": name,
                "role": role,
                "concept": concept["canonical_id"],
                "concept label": concept.get("pref_label"),
                "dimension": concept.get("dimension"),
                "SI unit": concept.get("si_unit"),
            }
            row.update({standard: _terms(concept, standard, with_units) for standard in standards})
            rows.append(row)

    columns = ["parameter", "role", "concept", "concept label", "dimension", "SI unit", *standards]
    return pd.DataFrame(rows, columns=columns), unmapped


def route_concepts(data: dict[str, Any], with_units: bool = False) -> pd.DataFrame:
    """Every concept in the taxonomy, with the datasheet fields that reach it."""
    standards = standard_ids(data)
    rows = []
    for concept in data["concepts"]:
        row = {
            "concept": concept["canonical_id"],
            "concept label": concept.get("pref_label"),
            "dimension": concept.get("dimension"),
            "SI unit": concept.get("si_unit"),
            "datasheet parameters": ", ".join(
                entry["field"] for entry in concept.get("transceiver_specs_fields", [])
            )
            or None,
        }
        row.update({standard: _terms(concept, standard, with_units) for standard in standards})
        rows.append(row)

    columns = ["concept", "concept label", "dimension", "SI unit", "datasheet parameters", *standards]
    return pd.DataFrame(rows, columns=columns)


def mapping_details(concept: dict[str, Any]) -> pd.DataFrame:
    """Every attribute the crosswalk records for each standard's version of one concept."""
    rows = []
    for mapping in concept.get("mappings", []):
        rows.append(
            {
                "standard": mapping["standard_id"],
                "term": mapping.get("term") or mapping.get("source_path"),
                "aliases": ", ".join(mapping.get("aliases", [])) or None,
                "unit": mapping.get("unit"),
                "measurement bandwidth": mapping.get("measurement_bandwidth"),
                "check type": mapping.get("check_type"),
                "relation": mapping.get("mapping_relation"),
                "value role": mapping.get("value_role"),
                "reference": mapping.get("reference"),
                "notes": mapping.get("notes"),
            }
        )
    frame = pd.DataFrame(rows)
    return frame.dropna(axis="columns", how="all") if not frame.empty else frame


def search_concepts(data: dict[str, Any], query: str) -> list[dict[str, Any]]:
    """Find concepts whose labels, definitions, terms or aliases mention the query."""
    needle = query.strip().lower()
    if not needle:
        return []

    hits = []
    for concept in data["concepts"]:
        haystack = [
            concept["canonical_id"],
            concept.get("pref_label", ""),
            concept.get("definition", ""),
            *concept.get("acronyms", []),
            *(entry["field"] for entry in concept.get("transceiver_specs_fields", [])),
        ]
        for mapping in concept.get("mappings", []):
            haystack.append(mapping.get("term", ""))
            haystack.extend(mapping.get("aliases", []))
        if any(needle in str(item).lower() for item in haystack):
            hits.append(concept)
    return hits
