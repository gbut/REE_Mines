# Burma Rare Earth Mines Dashboard

A satellite-map dashboard of in-situ leach rare earth mines in Kachin and Shan states, Burma (Myanmar). It is served by GitHub Pages from this repository.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole dashboard in one page (Leaflet map, tabs and saved copies of the data). Built by `build.py`; don't edit it by hand. |
| `reports.json` | The **Reports** tab: references found by Claude. The scheduled Reports task adds to this file. |
| `src/template.html` | Source for `index.html`: markup, styles and script. |
| `src/data/` | The saved copies of the data embedded as fallbacks, plus state and province boundaries. |
| `build.py` | Builds `index.html` from `src/` and `reports.json`. Run `python3 build.py`; `--check` confirms the built file is current. |
| `changes.json` | Changes found in Stimson's Burma rare earth rows by the weekly comparison. Shown in the **Data** tab and on each site's card. |
| `scripts/refresh_data.py` | Fetches the sources, refreshes the saved copies and updates `changes.json`. |
| `.github/workflows/refresh-data.yml` | Runs the refresh weekly (Sundays) and commits the result. |
| `CLAUDE.md` | Working notes for Claude sessions that maintain this repository. |

## Where the data comes from

The page loads each source live every time it opens. If a source can't be reached, it falls back to the copy saved inside `index.html`. The **Data** tab shows which sources loaded live.

| Tab or layer | Live source | Fallback |
|---|---|---|
| Stimson mine points | Stimson Center "Mining in Southeast Asia" Google Sheet, filtered to `Country = Myanmar` and `Metal = Rare Earth` | Copy refreshed weekly |
| Myanmar Witness points | Myanmar Witness / CIR public ArcGIS layer | Copy refreshed weekly |
| BVC Archive | BVC "REE Mines – Archive" Google Sheet, read through its CSV export (columns A–F: Date, Title, Source, Author, Notes, Link). Only rows under the **Articles and Reports** header row are shown; rows under **Social Media** are left out. | Copy refreshed weekly |
| Reports | `reports.json` in this repository | Copy saved inside `index.html` |

Notes on the live sources:

- **Stimson site IDs** are the row number in Stimson's sheet (S0634 is row 634). Edits to a row, or to other rows, don't change them; only inserting or deleting rows above does, and the change log records that.
- **Stimson changes:** Stimson's own "Last Updated" column is shown on each site card and can be filtered on. Each week the sheet is also compared with the previous saved copy, and any additions, removals or edited values are listed in the **Data** tab.
- **BVC Archive sections:** a section header is a row with text in column A and nothing in columns B–F. Every row after a header belongs to that section until the next header. Dates are shown as typed (full dates, `YYYY-MM` or a bare year).
- **BVC Archive changes** appear on the next page load, usually within a few minutes of the edit.

## `reports.json` format

The file is a JSON array with one object per reference:

```json
{
  "type": "News",
  "org": "Reuters",
  "date": "2026-11-11",
  "title": "Article title",
  "url": "https://…",
  "note": "One sentence on why it matters (optional)",
  "added": "2026-11-21"
}
```

| Field | Values |
|---|---|
| `type` | `News`, `Report`, `Analysis` or `Data` |
| `date` | Publication date: `YYYY-MM-DD`, `YYYY-MM`, `YYYY`, or `""` if unknown |
| `added` | The date the item was added |

Items added in the last 30 days show a **New** tag. A reference already in the BVC Archive should not also be added here.
