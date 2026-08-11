# Mode parameter viewer

A Streamlit app that shows the per-mode parameters extracted into `modes.json`.

It reads **only** `modes.json` from each run folder under `C:\Haris\Final\runs`. The other
artifacts in a run (`specs.json`, `content.md`, `raw_llm.json`, `mode_atoms.json`, `meta.json`)
are never opened.

## Run

```powershell
pip install -r requirements.txt
streamlit run app.py
```

The **Standards crosswalk** tab additionally reads
`C:\Haris\Final\Standards\_crosswalk\parameter_taxonomy.crosswalk.json` to map those
parameters onto their equivalents in other standards.

## What it shows

Each `modes.json` holds `{"modes": [...]}`, where every mode has a `label` plus whichever
parameters were extracted. The app renders one row per mode and one column per parameter,
with the mode label as the row index.

- **Run** — pick any run folder that contains a `modes.json`, newest first.
- **Compare all runs** — stack every run into one table with a `Run` column. Because runs
  extract different parameter sets, the combined table is the union of their columns.
- **Hide empty parameters** — drop columns where no mode has a value (on by default).
- **Parameters** — choose the subset of columns to display.
- **Filter modes** — free-text search across mode names and values.
- **Parameter coverage** — how many modes carry a value for each parameter.

Columns are ordered by `MODE_FIELDS` from `../transceiver_models.py`, and hovering a column
header shows that field's schema description. If that module cannot be imported, the app
falls back to alphabetical ordering with no tooltips.

List values in the JSON (for example `"modulation_formats": ["DP-QPSK", "DP-16QAM"]`) are
joined into a comma-separated string so they fit in a table cell.

## Standards crosswalk

The crosswalk taxonomy defines 81 vocabulary-neutral concepts. Each concept records the term
used by every standard (OIF-400ZR, OpenZR+, OpenROADM, SFF-8024, ITU-T G.652/G.694.1/G.698.1)
and the datasheet extraction fields that feed it. Those datasheet field names are exactly the
parameter names in `modes.json`, so each mode parameter routes to a concept and from there to
every other standard's name for the same quantity.

The tab shows a routing matrix: one row per parameter, one column per standard, with the
canonical concept, dimension and SI unit in between. Below it:

- **Show every concept in the taxonomy** — browse all 81 concepts instead of only this run's
  parameters, to see which standard terms exist that the extraction never produced.
- **Show units alongside terms** — append each standard's unit to the term. Worth switching on:
  it exposes cases like OSNR, quoted as `dB/12.5GHz` by OIF-400ZR, `dB/0.1nm` by OpenZR+ and
  plain `dB` by OpenROADM.
- **Mapping detail** — for one parameter, the concept definition plus every recorded attribute
  of each standard's mapping: aliases, unit, measurement bandwidth, check type, mapping
  relation, and the clause or table reference in the source standard.
- **Reverse lookup** — search any standard's term or alias to find the concept and the
  datasheet parameter it corresponds to.

Parameters with no concept, and concepts with no standard term, are called out rather than
silently dropped, since both are gaps worth seeing.

Values are deliberately **not** compared across standards. The taxonomy's own
`reference_point_guard` rule warns that mappings with different reference points or measurement
bandwidths are not directly comparable without a documented transform, so the app routes names
and records the caveats (shown as a comparability note under the mapping detail).

### A note on the crosswalk file

`parameter_taxonomy.crosswalk.json` is not strictly valid JSON: there is a trailing comma after
`meta.coverage.standards_indexed`, which makes `json.loads` fail at line 13. The app retries
with trailing commas stripped and shows a warning, so it works as-is. Removing that comma in the
source file will silence the warning.

## Pointing at a different folder

The runs folder is a text input in the sidebar, so you can point the app at any directory whose
subfolders contain `modes.json`. **Reload from disk** clears the cache after a new run lands.
