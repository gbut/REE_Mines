# Burma Rare Earth Mines Dashboard

A satellite-map dashboard of in-situ leach rare earth mines in Kachin and Shan states, Burma (Myanmar). It is served by GitHub Pages from this repository.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole dashboard in one page (Leaflet map, tabs and saved copies of the data). |
| `reports.json` | The **Reports** tab: references found by Claude. The scheduled Reports task adds to this file. |

## Where the data comes from

The page loads each source live every time it opens. If a source can't be reached, it falls back to the copy saved inside `index.html`. The **Data** tab shows which sources loaded live.

| Tab or layer | Live source | Fallback |
|---|---|---|
| Stimson mine points | Stimson Center "Mining in Southeast Asia" Google Sheet, filtered to `Country = Myanmar` and `Metal = Rare Earth` | Copy saved 20 Nov 2026 |
| Myanmar Witness points | Myanmar Witness / CIR public ArcGIS layer | Copy saved 20 Nov 2026 |
| BVC Archive | BVC "REE Mines – Archive" Google Sheet (columns A–F: Date, Title, Source, Author, Notes, Link) | Copy saved 20 Nov 2026 |
| Reports | `reports.json` in this repository | Copy saved inside `index.html` |

Notes on the live sources:

- **Stimson site IDs** (S001, S002, …) follow row order in Stimson's sheet. They stay stable as long as Stimson doesn't insert or delete rows above existing ones.
- **BVC Archive dates:** Google's sheet export drops values in the Date column that don't match the column's main type. For example, a bare year such as `2025` in a column of full dates comes through empty. Rows that were in the saved copy keep their saved date. For new rows, enter full dates, or format the Date column as plain text.
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
