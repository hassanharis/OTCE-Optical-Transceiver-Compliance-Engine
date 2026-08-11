"""Streamlit viewer for the per-mode parameters stored in runs/*/modes.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

import crosswalk

DEFAULT_RUNS_DIR = Path(r"C:\Haris\Final\runs")
MODES_FILE = "modes.json"
LABEL_KEY = "label"


def _load_schema_hints(runs_dir: Path) -> tuple[list[str], dict[str, str]]:
    """Canonical parameter order and descriptions from the extraction schema, if reachable."""
    project_root = str(runs_dir.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    try:
        from transceiver_models import MODE_FIELDS, TransceiverSpecs
    except Exception:
        return [], {}
    descriptions = {
        name: field.description
        for name, field in TransceiverSpecs.model_fields.items()
        if field.description
    }
    return list(MODE_FIELDS), descriptions


def _flatten(value: object) -> object:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item is not None) or None
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def _read_modes(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    modes = data.get("modes", []) if isinstance(data, dict) else data
    if not isinstance(modes, list):
        return []
    return [mode for mode in modes if isinstance(mode, dict)]


@st.cache_data(show_spinner=False)
def list_runs(runs_dir: str) -> list[str]:
    base = Path(runs_dir)
    if not base.is_dir():
        return []
    runs = [p.name for p in base.iterdir() if (p / MODES_FILE).is_file()]
    return sorted(runs, reverse=True)


@st.cache_data(show_spinner=False)
def load_parameters(runs_dir: str, run: str, _mtime: float, canonical: tuple[str, ...]) -> pd.DataFrame:
    """One row per mode, one column per parameter. Nothing outside modes.json is read."""
    modes = _read_modes(Path(runs_dir) / run / MODES_FILE)

    rows, labels = [], []
    for index, mode in enumerate(modes, start=1):
        label = mode.get(LABEL_KEY) or f"Mode {index}"
        labels.append(str(label))
        rows.append({key: _flatten(value) for key, value in mode.items() if key != LABEL_KEY})

    frame = pd.DataFrame(rows, index=pd.Index(labels, name="Mode"))
    ordered = [name for name in canonical if name in frame.columns]
    ordered += sorted(column for column in frame.columns if column not in ordered)
    return frame[ordered]


def mtime_of(runs_dir: str, run: str) -> float:
    return (Path(runs_dir) / run / MODES_FILE).stat().st_mtime


@st.cache_data(show_spinner=False)
def load_taxonomy(crosswalk_path: str, _mtime: float) -> tuple[dict, bool]:
    return crosswalk.load_crosswalk(crosswalk_path)


st.set_page_config(page_title="Mode Parameters", page_icon="", layout="wide")
st.title("Mode parameters")
st.caption(f"Reads only `{MODES_FILE}` from each run folder.")

runs_dir = st.sidebar.text_input("Runs folder", value=str(DEFAULT_RUNS_DIR))
runs = list_runs(runs_dir)

if not Path(runs_dir).is_dir():
    st.error(f"Folder not found: {runs_dir}")
    st.stop()
if not runs:
    st.warning(f"No run folder under {runs_dir} contains a {MODES_FILE} file.")
    st.stop()

if st.sidebar.button("Reload from disk", width="stretch"):
    st.cache_data.clear()
    st.rerun()

canonical_order, descriptions = _load_schema_hints(Path(runs_dir))
compare_runs = st.sidebar.toggle("Compare all runs", value=False)
selected_runs = runs if compare_runs else [st.sidebar.selectbox("Run", runs)]

frames = {run: load_parameters(runs_dir, run, mtime_of(runs_dir, run), tuple(canonical_order)) for run in selected_runs}

if compare_runs:
    table = pd.concat(frames, names=["Run"]).reset_index()
else:
    table = frames[selected_runs[0]]

if table.empty:
    st.info("This run has no modes recorded.")
    st.stop()

fixed_columns = [column for column in ("Run", "Mode") if column in table.columns]
parameters = [column for column in table.columns if column not in fixed_columns]
populated = [name for name in parameters if table[name].notna().any()]

hide_empty = st.sidebar.toggle("Hide empty parameters", value=True)
choices = populated if hide_empty else parameters
selection = st.sidebar.multiselect("Parameters", options=choices, default=choices)

parameters_tab, crosswalk_tab = st.tabs(["Mode parameters", "Standards crosswalk"])

with parameters_tab:
    search = st.text_input("Filter modes", placeholder="Search across mode names and values")
    view = table[fixed_columns + selection] if fixed_columns else table[selection]

    if search:
        haystack = view.astype("string").fillna("")
        if not fixed_columns:
            haystack.insert(0, "Mode", view.index.astype("string"))
        mask = haystack.apply(lambda column: column.str.contains(search, case=False, regex=False)).any(axis=1)
        view = view[mask.to_numpy()]

    left, middle, right = st.columns(3)
    left.metric("Modes", len(view))
    middle.metric("Parameters shown", len(selection))
    right.metric("Parameters populated", len(populated))

    st.dataframe(
        view,
        width="stretch",
        column_config={name: st.column_config.Column(name, help=descriptions.get(name)) for name in selection},
    )

    st.download_button(
        "Download parameters (CSV)",
        data=view.to_csv(index=not fixed_columns).encode("utf-8"),
        file_name=f"{'all_runs' if compare_runs else selected_runs[0]}_parameters.csv",
        mime="text/csv",
    )

    with st.expander("Parameter coverage"):
        coverage = pd.DataFrame(
            {
                "parameter": parameters,
                "modes with a value": [int(table[name].notna().sum()) for name in parameters],
                "description": [descriptions.get(name, "") for name in parameters],
            }
        ).sort_values("modes with a value", ascending=False, ignore_index=True)
        st.dataframe(coverage, width="stretch", hide_index=True)

with crosswalk_tab:
    crosswalk_path = st.text_input("Crosswalk file", value=str(crosswalk.DEFAULT_CROSSWALK))

    if not Path(crosswalk_path).is_file():
        st.error(f"Crosswalk not found: {crosswalk_path}")
        st.stop()

    taxonomy, repaired = load_taxonomy(crosswalk_path, Path(crosswalk_path).stat().st_mtime)
    if repaired:
        st.warning(
            "The crosswalk file is not strictly valid JSON (a trailing comma in `meta.coverage`). "
            "It was parsed with trailing commas removed."
        )

    standards = crosswalk.standard_ids(taxonomy)
    names = crosswalk.standard_names(taxonomy)
    st.caption(
        "Each parameter is routed through its canonical concept to the term used by every other standard. "
        f"Standards indexed: {', '.join(standards)}."
    )

    scope_all = st.toggle("Show every concept in the taxonomy", value=False)
    with_units = st.toggle("Show units alongside terms", value=False)

    by_parameter, unmapped = crosswalk.route_parameters(taxonomy, selection, with_units)
    routed = crosswalk.route_concepts(taxonomy, with_units) if scope_all else by_parameter

    chosen_standards = st.multiselect("Standards", options=standards, default=standards)
    fixed = [column for column in routed.columns if column not in standards]
    routed = routed[fixed + chosen_standards]

    reached = int(routed[chosen_standards].notna().any(axis=1).sum()) if chosen_standards else 0
    left, middle, right = st.columns(3)
    left.metric("Rows routed", len(routed))
    middle.metric("Reaching a standard", reached)
    right.metric("Not routed", len(unmapped))

    st.dataframe(
        routed,
        width="stretch",
        hide_index=True,
        column_config={
            standard: st.column_config.Column(standard, help=names.get(standard)) for standard in chosen_standards
        },
    )

    st.download_button(
        "Download crosswalk (CSV)",
        data=routed.to_csv(index=False).encode("utf-8"),
        file_name="parameter_crosswalk.csv",
        mime="text/csv",
        key="download_crosswalk",
    )

    if unmapped:
        st.info(
            "No concept in the crosswalk claims these parameters: "
            + ", ".join(f"`{name}`" for name in unmapped)
        )

    index = crosswalk.field_index(taxonomy)
    routable = [name for name in selection if name in index]
    if routable:
        st.subheader("Mapping detail")
        parameter = st.selectbox("Parameter", routable)
        concept, role = index[parameter]

        st.markdown(f"**{concept.get('pref_label')}** — `{concept['canonical_id']}`")
        if concept.get("definition"):
            st.write(concept["definition"])

        facts = {
            "dimension": concept.get("dimension"),
            "SI unit": concept.get("si_unit"),
            "quantity kind": concept.get("quantity_kind"),
            "check type": concept.get("check_type"),
            "reference point": concept.get("reference_point"),
            "role of this parameter": role,
            "acronyms": ", ".join(concept.get("acronyms", [])) or None,
        }
        st.dataframe(
            pd.DataFrame({"property": list(facts), "value": list(facts.values())}).dropna(),
            width="stretch",
            hide_index=True,
        )

        details = crosswalk.mapping_details(concept)
        if details.empty:
            st.info("This concept is defined in the taxonomy but no standard term is mapped to it yet.")
        else:
            st.dataframe(details, width="stretch", hide_index=True)

        if concept.get("notes"):
            st.caption(f"Comparability note: {concept['notes']}")

    st.subheader("Reverse lookup")
    query = st.text_input(
        "Find a concept by any standard's term",
        placeholder="e.g. osnr_tolerance, min-RX-osnr-tolerance, tx_output_power_window",
    )
    if query:
        hits = crosswalk.search_concepts(taxonomy, query)
        st.caption(f"{len(hits)} concept(s) matched.")
        for concept in hits:
            fields = ", ".join(entry["field"] for entry in concept.get("transceiver_specs_fields", []))
            with st.expander(f"{concept.get('pref_label')} — {concept['canonical_id']}"):
                st.caption(f"Datasheet parameters: {fields or 'none'}")
                st.dataframe(crosswalk.mapping_details(concept), width="stretch", hide_index=True)
