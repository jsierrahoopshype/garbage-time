# HoopsMatic — NBA Garbage Time

A single-page site that splits NBA box-score production into **official**, **real**, and
**garbage-time** buckets, so you can see who pads their numbers in blowouts.

- **Player search** with type-ahead → per-season + career drilldown (official vs real vs garbage, Δ highlighted), switchable across PTS/REB/AST/STL/BLK/TOV/3PM/eFG%/FG%.
- **Three leaderboards:** Stat-Padders (most garbage-time points), Biggest Droppers (largest Δ PPG), Star Stat-Padders (filtered by official PPG, 15/20/25 toggle).
- **Totals vs Per-Game** toggle, **season selector**, **min-games filter**.
- Headshots from cdn.nba.com with a silhouette fallback. Dark theme, no frameworks, no build step.

## Running locally

    python3 -m http.server 8000
    # open http://localhost:8000

## Data

Reads `data/garbage_time_for_web.json`, produced by an external pipeline. Every stat
(except `gp`) is a `[official, real, garbage]` triple where `official = real + garbage`.

## Deploying on GitHub Pages

Settings → Pages → Source: Deploy from a branch, branch `main`, folder `/ (root)`.
