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
parameters onto their equivalents in other standards, and the **Standards values** tab reads
the standards' own datasets under `C:\Haris\Final\Standards` to show their published values
beside the mode's.

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit UI: the three tabs |
| `modes.py` | Reading `modes.json` |
| `crosswalk.py` | Routing parameter names through the taxonomy |
| `standards.py` | Locating standard records by identity and reading their values |

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

## Standards values

The crosswalk tab routes parameter *names*. The **Standards values** tab goes one step further
and reads the standards' own *values* for a single mode.

The mode's `STANDARDS_IDENTITY_FIELDS` (from `transceiver_models.py`: host and media interface
names and IDs, `standards_code`, `frame`) say which record of a standard the mode claims to be.
Once that record is located, every parameter the crosswalk maps for that standard can be read
out of the standard's own dataset and shown beside the datasheet's value.

How each standard is joined and read:

| Standard | Record located by | Values read from |
| --- | --- | --- |
| SFF-8024 | host/media interface ID or name, against the Table 4-5 and 4-6/4-7 registries | the matched registry row |
| OpenZR+ | media interface name or SFF-8024 ID, against `identity[]` | the identity record, plus `optical_parameters` resolved on the mode's axes (payload rate, modulation, symbol rate, power profile, add/drop, grid) |
| OpenROADM | media interface ID or operational-mode ID, against the xponder-pluggable modes | the matched operational-mode record, plus shared grid parameters |
| OIF-400ZR | media interface ID, against the `application_code` axis | each specification's `base` plus the overrides selected by that application code |

Identifiers are spelled differently in every source — `0x64` in modes.json, `64` in SFF-8024
and OpenROADM, `46h` in OpenZR+ — so matching is done on parsed integers, and names are
compared with punctuation and case folded away.

### Why a matching ID is not enough

The same number means different things in different registries. A mode whose
`media_interface_id_hex` is `0x01` because that is its *OIF application code* will also "match"
SFF-8024 media ID 1, which is `10GBASE-LW` — a completely unrelated interface.

So a record counts as **corroborated** only when a name also matches or the mode explicitly
claims the standard (via `standards_code` or its label). Uncorroborated records are listed as
*identifier only* and are excluded from the value table unless you switch on **Accept
identifier-only matches**. Where several records legitimately match — `0x64` maps to both
`OR-W-400G-oFEC-118Gbd` and its `_type2` variant — each one is a dropdown so you choose which
record the values are read from.

The values themselves come in two layouts:

- **All standards side by side** — one row per concept, one column per standard. Best for
  spotting where the standards disagree, at the cost of empty cells where a standard says
  nothing about a concept.
- **One standard at a time** — a section per standard, listing only what that standard actually
  defines for this mode, grouped by dimension, with the mode's value beside it and the source
  term and unit alongside. The heading names the record the values were read from. Columns that
  would repeat the same value on every row, such as a single shared reference, are dropped.

Both layouts honour the "only rows where the mode and a standard both have a value" filter, and
the download button exports whichever layout is on screen.

Values are shown as each standard publishes them, including the bound (`min 80 km`,
`-10 … -6 dBm`, `expected 100 GHz`) and its unit. They are **not** normalised into a common
reference: reference points, measurement bandwidths and min/max orientation differ between
standards. The "Where each standard value came from" panel gives the term, unit, measurement
bandwidth and source clause behind every cell.

### A note on the crosswalk file

`parameter_taxonomy.crosswalk.json` is not strictly valid JSON: there is a trailing comma after
`meta.coverage.standards_indexed`, which makes `json.loads` fail at line 13. The app retries
with trailing commas stripped and shows a warning, so it works as-is. Removing that comma in the
source file will silence the warning.

## Pointing at a different folder

The runs folder is a text input in the sidebar, so you can point the app at any directory whose
subfolders contain `modes.json`. **Reload from disk** clears the cache after a new run lands.
