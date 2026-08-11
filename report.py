"""A self-contained HTML report for one run.

The template here is fixed and its content is not: every section is filled from the selected
run's folder and from the standards datasets, so any run exports the same report without the
template being touched. A section whose source the run does not carry is left out rather than
rendered empty, which is what lets one template serve runs that extracted very different
amounts of detail.

The report is a single file with no external assets, so it can be mailed or archived as is.
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

import standards
from modes import LABEL_KEY, flatten, mode_label

SPECS_FILE = "specs.json"
ATOMS_FILE = "mode_atoms.json"
META_FILE = "meta.json"

EMPTY = "—"

CSS = """
  :root { --bg: #f8fafc; --surface: #ffffff; --card: #f1f5f9; --accent: #0369a1; --accent2: #7c3aed;
          --accent3: #047857; --accent4: #c2410c; --text: #1e293b; --muted: #64748b; --border: #cbd5e1; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace; background: var(--bg);
         color: var(--text); line-height: 1.6; padding: 2rem; }
  .container { max-width: 1100px; margin: 0 auto; }
  header { text-align: center; margin-bottom: 2rem; }
  header h1 { font-size: 1.5rem; color: var(--accent); }
  header .model-name { font-size: 1.1rem; color: var(--accent3); margin-top: 0.5rem; font-weight: 600; }
  header .subtitle { color: var(--muted); font-size: 0.85rem; margin-top: 0.3rem; }
  .section { margin-bottom: 2rem; }
  .section-header { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.75rem; }
  .section-icon { width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center;
                  justify-content: center; font-size: 0.7rem; font-weight: 700; color: #fff; flex: none; }
  .section-icon.g { background: var(--accent); }
  .section-icon.m { background: var(--accent4); }
  .section-icon.mv { background: var(--accent2); }
  .section-icon.s { background: var(--accent3); }
  .section-title { font-size: 1rem; font-weight: 600; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem;
          overflow-x: auto; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
  .card + .card { margin-top: 0.9rem; }
  .spec-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.6rem; }
  .spec-item { background: var(--card); border-radius: 6px; padding: 0.5rem 0.75rem; }
  .spec-item .label { font-size: 0.68rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .spec-item .value { font-size: 0.88rem; font-weight: 600; margin-top: 0.1rem; word-break: break-word; }
  .spec-item.wide { grid-column: 1 / -1; }
  .spec-item.wide .value { font-weight: 400; font-size: 0.78rem; }
  .tally { margin-bottom: 1.5rem; }
  .tally .spec-item { text-align: center; }
  .tally .value { font-size: 1.1rem; color: var(--accent); }
  table { width: 100%; border-collapse: collapse; table-layout: auto; font-size: 0.8rem; }
  th, td { border: 1px solid var(--border); padding: 0.45rem 0.65rem; text-align: left; vertical-align: top; }
  th { background: var(--card); color: var(--accent); font-weight: 600; white-space: normal; }
  td { white-space: nowrap; }
  table.wrap td { white-space: normal; }
  tr:hover td { background: rgba(3,105,161,0.05); }
  .badge { display: inline-block; background: rgba(3,105,161,0.1); color: var(--accent); padding: 0.15rem 0.45rem;
           border-radius: 3px; font-size: 0.72rem; margin: 0.1rem; border: 1px solid rgba(3,105,161,0.2); }
  .mode { border: 1px solid var(--border); border-radius: 8px; background: var(--surface); padding: 1.25rem;
          margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
  .mode > h3 { font-size: 0.95rem; color: var(--accent4); }
  .mode > h3 .reached { font-size: 0.72rem; color: var(--muted); font-weight: 400; }
  .group { margin-top: 1rem; }
  .group h4 { font-size: 0.8rem; color: var(--accent); text-transform: uppercase; letter-spacing: 0.05em; }
  .group p.why { color: var(--muted); font-size: 0.72rem; margin-bottom: 0.4rem; }
  .empty { color: var(--muted); font-size: 0.75rem; font-style: italic; }
  .note-box { background: rgba(124,58,237,0.06); border-left: 3px solid var(--accent2); border-radius: 0 6px 6px 0;
              padding: 0.75rem 1rem; margin-top: 0.75rem; font-size: 0.75rem; }
  details { margin-top: 0.9rem; font-size: 0.78rem; }
  summary { cursor: pointer; color: var(--accent); }
  details table { margin-top: 0.6rem; }
  footer { text-align: center; color: var(--muted); font-size: 0.72rem; margin-top: 3rem; padding-top: 1rem;
           border-top: 1px solid var(--border); }
  @media print {
    body { padding: 0; background: #fff; }
    .card, .mode { break-inside: avoid; box-shadow: none; }
    details { display: none; }
  }
"""

# Label rendering: 'rx_osnr_tolerance_db_max' reads as 'RX OSNR Tolerance Max (dB)'.
_ACRONYMS = {
    "tx": "TX", "rx": "RX", "osnr": "OSNR", "cd": "CD", "pmd": "PMD", "pdl": "PDL", "dgd": "DGD",
    "sop": "SOP", "fec": "FEC", "ber": "BER", "los": "LOS", "rin": "RIN", "lo": "LO", "id": "ID",
    "hex": "Hex", "msa": "MSA", "oif": "OIF", "itu": "ITU", "sff": "SFF", "si": "SI", "ip": "IP",
}
_UNITS = {  # longest suffix first, so 'ps_nm' is not read as 'nm'
    "ps_nm": "ps/nm", "gbaud": "GBd", "gbps": "Gbps", "krad_s": "krad/s", "dbm": "dBm",
    "thz": "THz", "ghz": "GHz", "mhz": "MHz", "db": "dB", "km": "km", "nm": "nm", "ps": "ps",
    "w": "W", "c": "\u00b0C",
}
_QUALIFIERS = {"min", "max", "typ"}


def label_for(field: str) -> str:
    """A datasheet field name as a report heading, with its unit lifted into parentheses."""
    tokens = field.split("_")
    qualifier = tokens.pop() if len(tokens) > 1 and tokens[-1] in _QUALIFIERS else None

    unit = None
    for suffix, symbol in _UNITS.items():
        parts = suffix.split("_")
        if len(tokens) > len(parts) and tokens[-len(parts):] == parts:
            del tokens[-len(parts):]
            unit = symbol
            break

    words = [_ACRONYMS.get(token, token.capitalize()) for token in tokens]
    if qualifier:
        words.append(qualifier.capitalize())
    heading = " ".join(words)
    return f"{heading} ({unit})" if unit else heading


def _read_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _text(value: Any) -> str:
    rendered = flatten(value)
    return html.escape(str(rendered)) if rendered is not None and rendered != "" else EMPTY


def _frame(frame: pd.DataFrame | None, columns: list[str] | None = None, wrap: bool = True) -> str:
    """A table, or a note in its place. Columns nothing filled in are dropped."""
    if frame is None or frame.empty:
        return '<p class="empty">Nothing in this group for this mode.</p>'
    view = frame[columns] if columns else frame
    view = view.dropna(axis="columns", how="all")
    if view.empty or not len(view.columns):
        return '<p class="empty">Nothing in this group for this mode.</p>'
    return view.to_html(index=False, na_rep=EMPTY, border=0, justify="left", classes="wrap" if wrap else None)


_ICONS = {"general": ("g", "G"), "modes": ("m", "M"), "atoms": ("mv", "\u22ef"), "standards": ("s", "S")}


def _section(kind: str, title: str, body: str) -> str:
    style, glyph = _ICONS[kind]
    return (
        f'<div class="section"><div class="section-header">'
        f'<span class="section-icon {style}">{glyph}</span>'
        f'<span class="section-title">{html.escape(title)}</span></div>{body}</div>'
    )


def _spec_grid(items: list[tuple[str, str, bool]], style: str = "") -> str:
    cells = [
        f'<div class="spec-item{" wide" if wide else ""}"><div class="label">{html.escape(label)}</div>'
        f'<div class="value">{value}</div></div>'
        for label, value, wide in items
    ]
    return f'<div class="spec-grid{" " + style if style else ""}">{"".join(cells)}</div>'


# --------------------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------------------


def _general(specs: dict[str, Any], atoms: dict[str, Any]) -> str:
    """Module-wide specifications: whatever the datasheet states once for the whole part.

    Fields the extraction found several values for belong to the modes, not here, so they are
    left to the mode table and to the multi-valued section that explains where the modes came from.
    """
    per_mode = set(atoms.get("multi_valued", {}))
    plain = [key for key in specs if key not in per_mode and key != "notes" and specs[key] not in (None, [], "")]
    items = [(label_for(key), _text(specs[key]), False) for key in plain]
    if specs.get("notes"):
        items.append(("Notes", _text(specs["notes"]), True))
    return _spec_grid(items) if items else '<p class="empty">This run recorded no module-wide specifications.</p>'


def _mode_columns(modes: list[dict[str, Any]], field_order: tuple[str, ...]) -> list[str]:
    present = {
        key for mode in modes for key, value in mode.items() if key != LABEL_KEY and value is not None
    }
    ordered = [name for name in field_order if name in present]
    return ordered + sorted(present - set(ordered))


def _modes_table(modes: list[dict[str, Any]], field_order, descriptions: dict[str, str]) -> str:
    names = _mode_columns(modes, tuple(field_order))
    if not names:
        return '<p class="empty">This run recorded no mode parameters.</p>'

    heads = "".join(
        f'<th title="{html.escape(descriptions.get(name, name))}">{html.escape(label_for(name))}</th>'
        for name in names
    )
    body = "".join(
        f"<tr><td><strong>{html.escape(mode_label(mode, position))}</strong></td>"
        + "".join(f"<td>{_text(mode.get(name))}</td>" for name in names)
        + "</tr>"
        for position, mode in enumerate(modes, start=1)
    )
    return f"<table><tr><th>Mode</th>{heads}</tr>{body}</table>"


def _atoms_table(atoms: dict[str, Any]) -> str:
    multi = atoms.get("multi_valued", {})
    if not multi:
        return ""
    rows = "".join(
        f"<tr><td>{html.escape(field)}</td><td>"
        + " ".join(f'<span class="badge">{html.escape(str(value))}</span>' for value in values)
        + "</td></tr>"
        for field, values in multi.items()
        if values
    )
    body = (
        f'<div class="card"><table class="wrap"><tr><th>Field</th><th>Values</th></tr>{rows}</table>'
        '<div class="note-box">Each mode above is one combination of these values, linked back to the '
        "datasheet section they were read from.</div></div>"
    )
    return _section("atoms", "Multi-valued fields (source for mode generation)", body)


def _records(selection: dict[str, Any], standard_names: list[str]) -> str:
    rows = []
    for standard in standard_names:
        chosen = selection.get(standard)
        scoped = chosen.items() if isinstance(chosen, dict) else [(None, chosen)]
        for scope, match in scoped:
            rows.append(
                {
                    "standard": standard,
                    "scope": scope,
                    "record": match.label if match else None,
                    "confidence": match.confidence if match else "no record matched",
                    "why": " \u00b7 ".join(match.evidence) if match else None,
                }
            )
    return _frame(pd.DataFrame(rows))


def _mode_section(
    position: int,
    mode: dict[str, Any],
    selection: dict[str, Any],
    groups: dict[str, pd.DataFrame],
    detail: pd.DataFrame,
    standard_names: list[str],
) -> str:
    label = mode_label(mode, position)
    reached = standards.resolved_standards(selection)
    identity = {name: mode[name] for name in standards.identity_fields() if mode.get(name) is not None}

    parts = [
        f"<h3>{html.escape(label)} "
        f'<span class="reached">{html.escape(", ".join(reached) or "no standard record matched")}</span></h3>'
    ]

    if identity:
        badges = " ".join(
            f'<span class="badge">{html.escape(name)} = {_text(value)}</span>' for name, value in identity.items()
        )
        parts.append(f'<div class="group"><h4>Identity</h4>{badges}</div>')
        parts.append(f'<div class="group"><h4>Matched records</h4>{_records(selection, standard_names)}</div>')
    else:
        parts.append(
            '<div class="group"><p class="empty">This mode carries none of the identity parameters, '
            "so it cannot be located in any standard.</p></div>"
        )

    parts.append(
        '<div class="group"><h4>Comparison</h4>'
        '<p class="why">The mode and at least one standard both state a value.</p>'
        f'{_frame(groups[standards.COMPARISON])}</div>'
    )
    parts.append(
        '<div class="group"><h4>Enrichment</h4>'
        '<p class="why">The standard states a value the datasheet is silent on.</p>'
        f'{_frame(groups[standards.ENRICHMENT])}</div>'
    )

    only = groups[standards.MODE_ONLY]
    if not only.empty:
        parts.append(
            '<div class="group"><h4>Only in the datasheet</h4>'
            '<p class="why">No selected standard gives a value for these concepts.</p>'
            f'{_frame(only, ["concept", "mode parameter", "mode value"])}</div>'
        )

    if not detail.empty:
        parts.append(
            "<details><summary>Where each standard value came from</summary>"
            f"{_frame(detail)}</details>"
        )

    return f'<div class="mode">{"".join(parts)}</div>'


# --------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------


def build(
    run: str,
    runs_dir: str | Path,
    modes: list[dict[str, Any]],
    selections: list[dict[str, Any]],
    taxonomy: dict[str, Any],
    docs: dict[str, dict],
    standard_names: list[str],
    *,
    crosswalk_path: str | None = None,
    standards_root: str | None = None,
    include_weak: bool = False,
    field_order: tuple[str, ...] = (),
    descriptions: dict[str, str] | None = None,
) -> str:
    """Render the whole report for one run. `selections` holds the record chosen per mode."""
    base = Path(runs_dir) / run
    specs = _read_json(base / SPECS_FILE)
    atoms = _read_json(base / ATOMS_FILE)
    meta = _read_json(base / META_FILE)
    descriptions = descriptions or {}

    per_mode = []
    for position, (mode, selection) in enumerate(zip(modes, selections), start=1):
        wide, detail = standards.compare_mode(mode, taxonomy, docs, selection, standard_names)
        groups = standards.split_values(wide, standard_names)
        per_mode.append((position, mode, selection, groups, detail))

    reached = sorted({name for _, _, selection, _, _ in per_mode for name in standards.resolved_standards(selection)})
    compared = sum(len(groups[standards.COMPARISON]) for *_, groups, _ in per_mode)
    enriched = sum(len(groups[standards.ENRICHMENT]) for *_, groups, _ in per_mode)

    vendor_model = " ".join(str(specs[key]) for key in ("vendor", "model") if specs.get(key)) or run
    subtitle = " \u00b7 ".join(
        _text(specs[key]) for key in ("form_factor", "wavelength_band") if specs.get(key)
    )

    tally = _spec_grid(
        [
            ("Modes", str(len(modes)), False),
            ("Standards resolved", html.escape(", ".join(reached)) if reached else EMPTY, False),
            ("Concepts compared", str(compared), False),
            ("Added by a standard", str(enriched), False),
        ],
        style="tally",
    )

    body = [
        "<header>",
        "<h1>Transceiver Standards Report</h1>",
        f'<div class="model-name">{html.escape(vendor_model)}</div>',
        f'<div class="subtitle">{subtitle}</div>' if subtitle else "",
        f'<div class="subtitle">Run {html.escape(run)}</div>',
        "</header>",
        tally,
        _section("general", "General specifications", f'<div class="card">{_general(specs, atoms)}</div>'),
        _section(
            "modes",
            "Operating modes",
            f'<div class="card">{_modes_table(modes, field_order, descriptions)}</div>',
        ),
        _atoms_table(atoms),
        _section(
            "standards",
            "Standards values, mode by mode",
            "".join(_mode_section(*entry, standard_names) for entry in per_mode)
            + '<div class="note-box">Values are read from each standard as published. Reference points, '
            "measurement bandwidths and min/max orientation differ between standards, so treat the columns "
            "as side-by-side evidence rather than directly comparable numbers.</div>",
        ),
    ]

    provenance = " \u00b7 ".join(
        html.escape(str(fact))
        for fact in (
            f"Run {run}",
            f"extracted {str(meta.get('timestamp', ''))[:16].replace('T', ' ')}" if meta.get("timestamp") else "",
            f"model {meta['model_id']}" if meta.get("model_id") else "",
            f"identifier-only matches {'accepted' if include_weak else 'rejected'}",
            f"crosswalk {Path(crosswalk_path).name}" if crosswalk_path else "",
            f"standards {standards_root}" if standards_root else "",
            f"report generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        )
        if fact
    )

    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>Standards Report \u2014 {html.escape(vendor_model)}</title>\n"
        f"<style>{CSS}</style>\n</head>\n<body>\n"
        f'<div class="container">{"".join(body)}<footer>{provenance}</footer></div>\n'
        "</body>\n</html>\n"
    )
