#!/usr/bin/env python3
"""Pre-render static, indexable HTML for the HoopsMatic NBA garbage-time site.
Usage:  python3 build_pages.py
"""

import bisect
import html
import json
import os
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "data", "garbage_time_for_web.json")

BASE_URL = "https://jsierrahoopshype.github.io/garbage-time"

MIN_GAMES = 30
STAR_THRESHOLD = 20
TOP_N = 100
HUB_TOP_N = 25

GARBAGE_PCT_MAX = 35.0

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700'
    '&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">'
)

GARBAGE_STATS = [
    ("pts", "PTS", "Points", "points"),
    ("reb", "REB", "Rebounds", "rebounds"),
    ("ast", "AST", "Assists", "assists"),
    ("stl", "STL", "Steals", "steals"),
    ("blk", "BLK", "Blocks", "blocks"),
]
STAT_LABEL = {s: lab for s, lab, _n, _f in GARBAGE_STATS}
STAT_NAME = {s: name for s, _l, name, _f in GARBAGE_STATS}
STAT_FULL = {s: full for s, _l, _n, full in GARBAGE_STATS}

SCORING_TITLE = {
    "biggest-droppers": "Biggest Droppers",
    "star-stat-padders": "Stars in Garbage Time",
}
SCORING_BLURB = {
    "biggest-droppers": "Players whose scoring falls the most once garbage time is removed (Δ = real PPG − official PPG).",
    "star-stat-padders": "Real rotation stars (%d+ official PPG) who still pad the most in garbage time." % STAR_THRESHOLD,
}

NAV_BOARDS = ([("garbage-%s" % s, "Garbage %s" % lab) for s, lab, _n, _f in GARBAGE_STATS]
              + [("biggest-droppers", "Biggest Droppers"),
                 ("star-stat-padders", "Stars in Garbage Time")])

COUNT_STATS = [("pts", "PTS"), ("reb", "REB"), ("ast", "AST"), ("stl", "STL"),
               ("blk", "BLK"), ("tov", "TOV"), ("fg3m", "3PM")]


SORT_SCRIPT = """<script>
(function () {
  function val(td) {
    var raw = td.getAttribute("data-sort");
    if (raw === null) raw = td.textContent;
    raw = raw.trim();
    var num = raw.replace(/,/g, "").replace(/\\s*pp$/, "").replace(/[%+]/g, "").trim();
    if (num !== "" && /^[-+]?[0-9]*\\.?[0-9]+$/.test(num)) return { n: parseFloat(num), s: null };
    return { n: null, s: raw.toLowerCase() };
  }
  Array.prototype.forEach.call(document.querySelectorAll("table.lb.sortable"), function (table) {
    var head = table.tHead && table.tHead.rows[0];
    if (!head) return;
    Array.prototype.forEach.call(head.cells, function (th, idx) {
      if (th.classList.contains("rank")) return;
      th.classList.add("sortable-th");
      th.addEventListener("click", function () {
        var cur = th.classList.contains("sort-desc") ? "desc"
                : th.classList.contains("sort-asc") ? "asc" : null;
        var dir = cur === "desc" ? "asc"
                : cur === "asc" ? "desc"
                : th.classList.contains("left") ? "asc" : "desc";
        Array.prototype.forEach.call(head.cells, function (h) {
          h.classList.remove("sort-asc", "sort-desc");
        });
        th.classList.add(dir === "asc" ? "sort-asc" : "sort-desc");
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows).filter(function (r) {
          return !r.querySelector("td.empty");
        });
        rows.sort(function (a, b) {
          var x = val(a.cells[idx]), y = val(b.cells[idx]), c;
          if (x.n !== null && y.n !== null) c = x.n - y.n;
          else c = (x.s || "").localeCompare(y.s || "");
          return dir === "asc" ? c : -c;
        });
        rows.forEach(function (r) { body.appendChild(r); });
        var rk = 1;
        rows.forEach(function (r) {
          var c = r.querySelector("td.rank");
          if (c) c.textContent = rk++;
        });
      });
    });
  });
})();
</script>"""


def esc(s):
    return html.escape(str(s), quote=True)


def headshot(pid):
    return "https://cdn.nba.com/headshots/nba/latest/260x190/%s.png" % pid


def bucket(o, key, b):
    if key == "efg":
        return (o["fgm"][b] + 0.5 * o["fg3m"][b]) / o["fga"][b] if o["fga"][b] else 0.0
    if key == "fgpct":
        return o["fgm"][b] / o["fga"][b] if o["fga"][b] else 0.0
    v = o.get(key)
    return v[b] if isinstance(v, list) else 0


def pg(total, gp):
    return total / gp if gp else 0.0


def fmt_total(total):
    return "{:,}".format(int(round(total)))


def fmt_pct(v):
    return "%.2f%%" % (v * 100)


def signed(n, digits=1):
    return ("%+." + str(digits) + "f") % n


def delta_cls(n):
    if n < -1e-9:
        return "neg"
    if n > 1e-9:
        return "pos"
    return "flat"


def garbage_pct_color(pct):
    t = pct / GARBAGE_PCT_MAX
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    hue = int(round(120 * (1 - t)))
    return "hsl(%d, 80%%, 85%%)" % hue


def season_label(season):
    return "Career" if season == "career" else season


def stat_obj(player, season):
    return player["career"] if season == "career" else player["seasons"].get(season)


def build_slug_map(players):
    counts = {}
    for p in players:
        counts[p["slug"]] = counts.get(p["slug"], 0) + 1
    dup = {s for s, n in counts.items() if n > 1}
    slug_of = {}
    for p in players:
        slug_of[p["id"]] = ("%s-%s" % (p["slug"], p["id"])) if p["slug"] in dup else p["slug"]
    return slug_of


def compute_neighbors(players, k=6):
    def share(p):
        c = p["career"]
        return (c["pts"][2] / c["pts"][0] * 100) if c["pts"][0] else 0.0

    gpct_by_id = {p["id"]: share(p) for p in players}
    pool = sorted((p for p in players if p["career"]["gp"] >= MIN_GAMES),
                  key=lambda p: gpct_by_id[p["id"]])
    vals = [gpct_by_id[p["id"]] for p in pool]
    n = len(pool)

    neighbors_by_id = {}
    for p in players:
        v = gpct_by_id[p["id"]]
        i = bisect.bisect_left(vals, v)
        lo, hi = i - 1, i
        picked = []
        while len(picked) < k and (lo >= 0 or hi < n):
            d_lo = (v - vals[lo]) if lo >= 0 else None
            d_hi = (vals[hi] - v) if hi < n else None
            if d_hi is None or (d_lo is not None and d_lo <= d_hi):
                cand = pool[lo]
                lo -= 1
            else:
                cand = pool[hi]
                hi += 1
            if cand["id"] != p["id"]:
                picked.append(cand)
        picked.sort(key=lambda q: gpct_by_id[q["id"]])
        neighbors_by_id[p["id"]] = picked
    return neighbors_by_id, gpct_by_id


def page_head(title, description, canonical_path, og_image=None, og_type="website"):
    canonical = BASE_URL + "/" + canonical_path
    img = og_image or (BASE_URL + "/")
    tags = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>%s</title>" % esc(title),
        '<meta name="description" content="%s">' % esc(description),
        '<link rel="canonical" href="%s">' % esc(canonical),
        '<meta property="og:type" content="%s">' % og_type,
        '<meta property="og:site_name" content="HoopsMatic">',
        '<meta property="og:title" content="%s">' % esc(title),
        '<meta property="og:description" content="%s">' % esc(description),
        '<meta property="og:url" content="%s">' % esc(canonical),
        '<meta property="og:image" content="%s">' % esc(img),
        '<meta name="twitter:card" content="summary">',
        FONTS,
        '<link rel="stylesheet" href="../styles.css">',
        "</head>",
        "<body>",
        '<div class="container">',
    ]
    return "\n".join(tags)


def page_foot(updated):
    stamp = (" · updated " + esc(updated)) if updated else ""
    return (
        '<div class="foot">HoopsMatic · Garbage-time splits derived from play-by-play. '
        '"Real" numbers exclude garbage-time stretches; "official" match the box score.'
        + stamp + "</div>\n</div>\n</body>\n</html>\n"
    )


def nav_tabs(active):
    items = [("Search & Drilldown", "../index.html", "home"),
             ("Leaderboards", "../leaderboards/index.html", "lb"),
             ("All Players", "../p/index.html", "players")]
    out = ['<div class="tabs">']
    for label, href, key in items:
        cls = ' class="active"' if key == active else ""
        out.append('<a href="%s"%s>%s</a>' % (href, cls, esc(label)))
    out.append("</div>")
    return "".join(out)


def board_tabs(active_stem, season):
    out = ['<div class="chips">']
    for stem, label in NAV_BOARDS:
        cls = "chip active" if stem == active_stem else "chip"
        out.append('<a class="%s" href="%s-%s.html">%s</a>' % (cls, stem, season, esc(label)))
    out.append("</div>")
    return "".join(out)


def season_tabs(stem, seasons, active_season):
    chips = ['<a class="chip%s" href="%s-career.html">Career</a>'
             % (" active" if active_season == "career" else "", stem)]
    for s in seasons:
        cls = " active" if s == active_season else ""
        chips.append('<a class="chip%s" href="%s-%s.html">%s</a>' % (cls, stem, s, esc(s)))
    return '<div class="chips" style="margin:.6rem 0 1rem">' + "".join(chips) + "</div>"


def render_player(player, slug, slug_of, neighbors, gpct_of, updated):
    name = player["name"]
    car = player["career"]
    gp = car["gp"]
    off_ppg = pg(car["pts"][0], gp)
    real_ppg = pg(car["pts"][1], gp)
    gar_pts = car["pts"][2]
    d_ppg = real_ppg - off_ppg
    car_share = (car["pts"][2] / car["pts"][0] * 100) if car["pts"][0] else 0.0
    seasons = sorted(player["seasons"].keys(), reverse=True)

    title = "%s Garbage-Time Stats | HoopsMatic" % name
    desc = ("%s's real vs official production once garbage time is stripped out: "
            "career %.2f%% of points come in garbage time (%.1f real PPG vs %.1f official, %s) "
            "over %d games." % (name, car_share, real_ppg, off_ppg, signed(d_ppg), gp))

    head = page_head(title, desc, "p/%s.html" % slug, og_image=headshot(player["id"]),
                     og_type="profile")

    parts = [head]
    parts.append(nav_tabs(None))

    parts.append('<div class="ehead">')
    parts.append('<img class="eimg" src="%s" alt="%s" '
                 'onerror="this.onerror=null;this.style.visibility=\'hidden\'">'
                 % (headshot(player["id"]), esc(name)))
    parts.append('<div><h1>%s</h1><div class="esub">Garbage-time splits · '
                 '%d season%s · %d career GP</div></div>'
                 % (esc(name), len(seasons), "" if len(seasons) == 1 else "s", gp))
    parts.append("</div>")

    parts.append('<div class="stat-cards">')
    parts.append('<div class="stat-card"><div class="lbl">Official PPG</div>'
                 '<div class="num flat">%.1f</div><div class="sub">as in the box score</div></div>' % off_ppg)
    parts.append('<div class="stat-card"><div class="lbl">Real PPG</div>'
                 '<div class="num flat">%.1f</div><div class="sub">garbage time removed</div></div>' % real_ppg)
    parts.append('<div class="stat-card gpct-card" style="background:%s">'
                 '<div class="lbl">Garbage %% of points</div>'
                 '<div class="num">%.2f%%</div>'
                 '<div class="sub">%s garbage pts · Δ %s PPG</div></div>'
                 % (garbage_pct_color(car_share), car_share, fmt_total(gar_pts), signed(d_ppg)))
    parts.append("</div>")

    parts.append('<div class="section">')
    parts.append('<div class="section-head"><h2>Scoring by season — per game</h2></div>')
    parts.append('<div class="table-wrap"><table class="lb"><thead><tr>'
                 '<th class="left">Season</th><th>GP</th><th>Official PPG</th>'
                 '<th>Real PPG</th><th>Garbage PPG</th><th class="dcol">Garbage %</th>'
                 '<th>Δ PPG</th></tr></thead><tbody>')

    def scoring_row(label, o, career=False):
        o_off = pg(o["pts"][0], o["gp"])
        o_real = pg(o["pts"][1], o["gp"])
        o_gar = pg(o["pts"][2], o["gp"])
        d = o_real - o_off
        share = (o["pts"][2] / o["pts"][0] * 100) if o["pts"][0] else 0.0
        cls = " career-row" if career else ""
        return ('<tr class="%s"><td class="left">%s</td><td>%d</td><td>%.1f</td>'
                '<td>%.1f</td><td>%.1f</td>'
                '<td class="gpct" style="background:%s">%.2f%%</td>'
                '<td class="delta deemph %s">%s</td></tr>'
                % (cls.strip(), esc(label), o["gp"], o_off, o_real, o_gar,
                   garbage_pct_color(share), share, delta_cls(d), signed(d)))

    for s in seasons:
        parts.append(scoring_row(s, player["seasons"][s]))
    parts.append(scoring_row("Career", car, career=True))
    parts.append("</tbody></table></div></div>")

    parts.append('<div class="section">')
    parts.append('<div class="section-head"><h2>Career splits — per game</h2></div>')
    parts.append('<div class="hint">Official = real + garbage. Garbage % is garbage as a share '
                 'of the official total; Δ is real minus official.</div>')
    parts.append('<div class="table-wrap"><table class="lb"><thead><tr>'
                 '<th class="left">Stat</th><th>Official</th><th>Real</th>'
                 '<th>Garbage</th><th class="dcol">Garbage %</th><th>Δ</th>'
                 '</tr></thead><tbody>')
    for key, label in COUNT_STATS:
        o_off = pg(car[key][0], gp)
        o_real = pg(car[key][1], gp)
        o_gar = pg(car[key][2], gp)
        d = o_real - o_off
        share = (car[key][2] / car[key][0] * 100) if car[key][0] else 0.0
        parts.append('<tr><td class="left">%s</td><td>%.1f</td><td>%.1f</td><td>%.1f</td>'
                     '<td class="gpct" style="background:%s">%.2f%%</td>'
                     '<td class="delta deemph %s">%s</td></tr>'
                     % (label, o_off, o_real, o_gar, garbage_pct_color(share), share,
                        delta_cls(d), signed(d)))
    for rkey, rlabel in (("efg", "eFG%"), ("fgpct", "FG%")):
        r_off = bucket(car, rkey, 0)
        r_real = bucket(car, rkey, 1)
        r_gar = bucket(car, rkey, 2)
        dr = (r_real - r_off) * 100
        parts.append('<tr><td class="left">%s</td><td>%s</td><td>%s</td><td>%s</td>'
                     '<td class="muted">—</td>'
                     '<td class="delta deemph %s">%s pp</td></tr>'
                     % (rlabel, fmt_pct(r_off), fmt_pct(r_real), fmt_pct(r_gar),
                        delta_cls(dr), signed(dr)))
    parts.append("</tbody></table></div></div>")

    if neighbors:
        parts.append('<div class="section">')
        parts.append('<div class="section-head"><h2>Similar garbage-time profiles</h2></div>')
        parts.append('<div class="hint">Players with a comparable career garbage % of points.</div>')
        parts.append('<div class="egrid">')
        for nb in neighbors:
            share = gpct_of[nb["id"]]
            parts.append('<a class="ecard" href="%s.html">'
                         '<img src="%s" alt="" onerror="this.onerror=null;this.style.visibility=\'hidden\'">'
                         '<span class="en">%s</span>'
                         '<span class="ec gpct" style="background:%s">%.2f%%</span></a>'
                         % (slug_of[nb["id"]], headshot(nb["id"]), esc(nb["name"]),
                            garbage_pct_color(share), share))
        parts.append("</div></div>")

    parts.append('<p style="margin:.2rem 0 1rem"><a class="chip" href="../index.html?player=%s">'
                 'Explore interactively →</a></p>' % esc(slug))

    parts.append(page_foot(updated))
    return "\n".join(parts)


def leaderboard_rows(players, season):
    rows = []
    for p in players:
        o = stat_obj(p, season)
        if not o or o["gp"] < MIN_GAMES:
            continue
        gp = o["gp"]
        rows.append({
            "p": p, "gp": gp,
            "off_ppg": pg(o["pts"][0], gp),
            "real_ppg": pg(o["pts"][1], gp),
            "gar_pts": o["pts"][2],
            "off_pts": o["pts"][0],
        })
    for r in rows:
        r["d_ppg"] = r["real_ppg"] - r["off_ppg"]
        r["gar_share"] = (r["gar_pts"] / r["off_pts"] * 100) if r["off_pts"] else 0.0
    return rows


def garbage_stat_rows(players, season, stat):
    rows = []
    for p in players:
        o = stat_obj(p, season)
        if not o or o["gp"] < MIN_GAMES:
            continue
        gp = o["gp"]
        off = bucket(o, stat, 0)
        gar = bucket(o, stat, 2)
        rows.append({
            "p": p, "gp": gp,
            "off_pg": pg(off, gp),
            "gar_pg": pg(gar, gp),
            "gar_tot": gar,
            "off_tot": off,
            "gar_pct": (gar / off * 100) if off else 0.0,
        })
    rows.sort(key=lambda r: r["gar_pg"], reverse=True)
    return rows[:TOP_N]


def _garbage_cols(label):
    return [
        ("GP", False, lambda r: "%d" % r["gp"], None, None),
        ("Official %s /g" % label, False, lambda r: "%.1f" % r["off_pg"], None, None),
        ("Garbage %s /g" % label, True, lambda r: "%.2f" % r["gar_pg"], "desc", None),
        ("Garbage %s" % label, False, lambda r: fmt_total(r["gar_tot"]), None, None),
        ("Garbage %% of %s" % label, False, lambda r: "%.2f%%" % r["gar_pct"], None,
         lambda r: garbage_pct_color(r["gar_pct"])),
    ]


def _droppers_cols():
    return [
        ("GP", False, lambda r: "%d" % r["gp"], None, None),
        ("Official PPG", False, lambda r: "%.1f" % r["off_ppg"], None, None),
        ("Real PPG", False, lambda r: "%.1f" % r["real_ppg"], None, None),
        ("Δ PPG", True, lambda r: ('<span class="delta %s">%s</span>'
                                   % (delta_cls(r["d_ppg"]), signed(r["d_ppg"]))), "asc", None),
        ("Garbage % of pts", False, lambda r: "%.2f%%" % r["gar_share"], None,
         lambda r: garbage_pct_color(r["gar_share"])),
    ]


def _stars_cols():
    return [
        ("GP", False, lambda r: "%d" % r["gp"], None, None),
        ("Official PPG", False, lambda r: "%.1f" % r["off_ppg"], None, None),
        ("Garbage PTS", True, lambda r: fmt_total(r["gar_pts"]), "desc", None),
        ("Garbage % of pts", False, lambda r: "%.2f%%" % r["gar_share"], None,
         lambda r: garbage_pct_color(r["gar_share"])),
    ]


def board_data(board_key, season, players):
    slabel = season_label(season)
    if board_key.startswith("garbage-"):
        stat = board_key.split("-", 1)[1]
        label, name, full = STAT_LABEL[stat], STAT_NAME[stat], STAT_FULL[stat]
        rows = garbage_stat_rows(players, season, stat)
        disp = "Garbage-Time %s" % name
        if rows:
            desc = ("NBA players ranked by garbage-time %s per game, %s. %s leads at %.2f garbage "
                    "%s per game (%s total). Min %d games."
                    % (full, slabel, rows[0]["p"]["name"], rows[0]["gar_pg"], full,
                       fmt_total(rows[0]["gar_tot"]), MIN_GAMES))
        else:
            desc = "NBA garbage-time %s leaderboard, %s. Min %d games." % (full, slabel, MIN_GAMES)
        blurb = ("Players ranked by their garbage-time %s — production accrued once the game "
                 "was already decided." % full)
        subtitle = "%s %s" % (esc(blurb), esc("Minimum %d games." % MIN_GAMES))
        title = "NBA %s — %s | HoopsMatic" % (disp, slabel)
        cols = _garbage_cols(label)
    else:
        rows = leaderboard_rows(players, season)
        if board_key == "biggest-droppers":
            rows.sort(key=lambda r: r["d_ppg"])
            rows = rows[:TOP_N]
            cols = _droppers_cols()
            disp = SCORING_TITLE[board_key]
            note = "Minimum %d games." % MIN_GAMES
            if rows:
                desc = ("NBA players whose scoring drops most once garbage time is removed, %s. "
                        "%s leads at %s real-minus-official PPG. Min %d games."
                        % (slabel, rows[0]["p"]["name"], signed(rows[0]["d_ppg"]), MIN_GAMES))
            else:
                desc = "NBA garbage-time biggest droppers leaderboard, %s. Min %d games." % (slabel, MIN_GAMES)
        else:
            rows = [r for r in rows if r["off_ppg"] >= STAR_THRESHOLD]
            rows.sort(key=lambda r: r["gar_pts"], reverse=True)
            rows = rows[:TOP_N]
            cols = _stars_cols()
            disp = SCORING_TITLE[board_key]
            note = "Minimum %d games · %d+ official PPG." % (MIN_GAMES, STAR_THRESHOLD)
            if rows:
                desc = ("NBA stars (%d+ official PPG) padding the most in garbage time, %s. "
                        "%s tops it with %s garbage points. Min %d games."
                        % (STAR_THRESHOLD, slabel, rows[0]["p"]["name"],
                           fmt_total(rows[0]["gar_pts"]), MIN_GAMES))
            else:
                desc = "NBA stars-in-garbage-time leaderboard, %s. Min %d games." % (slabel, MIN_GAMES)
        subtitle = "%s %s" % (esc(SCORING_BLURB[board_key]), esc(note))
        title = "NBA Garbage-Time %s — %s | HoopsMatic" % (disp, slabel)

    return {
        "stem": board_key, "nav_stem": board_key, "canonical_stem": board_key,
        "disp": disp, "title": title, "heading": "%s · %s" % (disp, slabel),
        "subtitle": subtitle, "desc": desc, "cols": cols, "rows": rows,
    }


def render_lb_table(cols, rows, slug_of, sortable, empty_label):
    table_cls = "lb sortable" if sortable else "lb"
    th = ['<th class="rank">#</th>',
          '<th class="left%s">Player</th>' % (" sortable-th" if sortable else "")]
    for header, is_d, _fn, dflt, _bg in cols:
        cls = ["dcol"] if is_d else []
        if sortable:
            cls.append("sortable-th")
        if dflt == "asc":
            cls.append("sort-asc")
        elif dflt == "desc":
            cls.append("sort-desc")
        th.append('<th class="%s">%s</th>' % (" ".join(cls), esc(header)))
    out = ['<div class="table-wrap"><table class="%s"><thead><tr>%s</tr></thead><tbody>'
           % (table_cls, "".join(th))]
    if not rows:
        out.append('<tr><td colspan="%d" class="empty">No players meet the filters '
                   'for %s.</td></tr>' % (len(cols) + 2, esc(empty_label)))
    else:
        for i, r in enumerate(rows, 1):
            p = r["p"]
            pslug = slug_of[p["id"]]
            namecell = ('<td class="left"><span class="pcell">'
                        '<img src="%s" alt="" onerror="this.onerror=null;this.style.visibility=\'hidden\'">'
                        '<a href="../p/%s.html">%s</a></span></td>'
                        % (headshot(p["id"]), pslug, esc(p["name"])))
            cells = []
            for _h, is_d, fn, _d, bg in cols:
                klass = "dcol" if is_d else ""
                style = ""
                if bg:
                    color = bg(r)
                    if color:
                        style = ' style="background:%s"' % color
                        klass = (klass + " gpct").strip()
                cells.append('<td class="%s"%s>%s</td>' % (klass, style, fn(r)))
            out.append('<tr><td class="rank">%d</td>%s%s</tr>' % (i, namecell, "".join(cells)))
    out.append("</tbody></table></div>")
    return "\n".join(out)


def _board_page(data, season, seasons, slug_of, updated):
    nav = data["nav_stem"]
    parts = [page_head(data["title"], data["desc"],
                       "leaderboards/%s-%s.html" % (data["canonical_stem"], season))]
    parts.append(nav_tabs("lb"))
    parts.append('<div class="hdr"><h1>%s</h1><span class="brand">HoopsMatic</span></div>'
                 % esc(data["heading"]))
    parts.append('<div class="subtitle">%s</div>' % data["subtitle"])
    parts.append(board_tabs(nav, season))
    parts.append(season_tabs(nav, seasons, season))
    parts.append(render_lb_table(data["cols"], data["rows"], slug_of, True, season_label(season)))
    parts.append(SORT_SCRIPT)
    parts.append(page_foot(updated))
    return "\n".join(parts)


def render_full_board(board_key, season, players, slug_of, seasons, updated, display=None):
    data = board_data(board_key, season, players)
    if display:
        slabel = season_label(season)
        data["title"] = "NBA %s — %s | HoopsMatic" % (display, slabel)
        data["heading"] = "%s · %s" % (display, slabel)
    return _board_page(data, season, seasons, slug_of, updated)


def render_players_index(players, slug_of, gpct_by_id, updated):
    title = "All NBA Players — Garbage-Time Stats | HoopsMatic"
    desc = ("Browse garbage-time real-vs-official stats for every NBA player, %d in all, "
            "seasons 2016-17 through 2025-26." % len(players))
    head = page_head(title, desc, "p/index.html")
    parts = [head]
    parts.append(nav_tabs("players"))
    parts.append('<div class="hdr"><h1>All Players</h1><span class="brand">HoopsMatic</span></div>')
    parts.append('<div class="subtitle">%d players · career totals, click any name for the full '
                 'garbage-time splits.</div>' % len(players))

    ordered = sorted(players, key=lambda p: p["name"].lower())
    groups = {}
    for p in ordered:
        letter = p["name"].strip()[:1].upper()
        if not letter.isalpha():
            letter = "#"
        groups.setdefault(letter, []).append(p)

    for letter in sorted(groups.keys()):
        parts.append('<div class="dir-letter">%s</div>' % esc(letter))
        parts.append('<div class="table-wrap"><table class="lb"><thead><tr>'
                     '<th class="left">Player</th><th>GP</th><th>Official PPG</th>'
                     '<th>Garbage PPG</th><th class="dcol">Garbage %</th>'
                     '</tr></thead><tbody>')
        for p in groups[letter]:
            car = p["career"]
            gpn = car["gp"]
            off = pg(car["pts"][0], gpn)
            gar_pg = pg(car["pts"][2], gpn)
            share = gpct_by_id[p["id"]]
            parts.append('<tr><td class="left"><span class="pcell">'
                         '<img src="%s" alt="" onerror="this.onerror=null;this.style.visibility=\'hidden\'">'
                         '<a href="%s.html">%s</a></span></td>'
                         '<td>%d</td><td>%.1f</td><td>%.1f</td>'
                         '<td class="gpct" style="background:%s">%.2f%%</td></tr>'
                         % (headshot(p["id"]), slug_of[p["id"]], esc(p["name"]),
                            gpn, off, gar_pg, garbage_pct_color(share), share))
        parts.append("</tbody></table></div>")
    parts.append(page_foot(updated))
    return "\n".join(parts)


def render_leaderboards_index(players, slug_of, seasons, updated):
    title = "NBA Garbage-Time Leaderboards | HoopsMatic"
    desc = ("Garbage-time leaderboards: points, rebounds, assists, steals and blocks leaders, "
            "plus biggest droppers and stars in garbage time — career and every season from "
            "2016-17 to 2025-26.")
    parts = [page_head(title, desc, "leaderboards/index.html")]
    parts.append(nav_tabs("lb"))
    parts.append('<div class="hdr"><h1>Leaderboards</h1><span class="brand">HoopsMatic</span></div>')
    parts.append('<div class="subtitle">Career top %d on every board — open a board for the full '
                 'top %d and season-by-season tables. Minimum %d games.</div>'
                 % (HUB_TOP_N, TOP_N, MIN_GAMES))

    for board_key, _label in NAV_BOARDS:
        data = board_data(board_key, "career", players)
        parts.append('<div class="section">')
        parts.append('<div class="section-head"><h2>%s</h2>'
                     '<a class="more" href="%s-career.html">View full leaderboard →</a></div>'
                     % (esc(data["disp"]), board_key))
        parts.append('<div class="hint">%s</div>' % data["subtitle"])
        parts.append(render_lb_table(data["cols"], data["rows"][:HUB_TOP_N], slug_of, False, "Career"))
        parts.append("</div>")
    parts.append(page_foot(updated))
    return "\n".join(parts)


def write_sitemap(urls, lastmod):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        lines.append("  <url><loc>%s</loc><lastmod>%s</lastmod></url>" % (esc(u), lastmod))
    lines.append("</urlset>\n")
    with open(os.path.join(HERE, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_robots():
    body = "User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % BASE_URL
    with open(os.path.join(HERE, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(body)


def write(path, content):
    full = os.path.join(HERE, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)

    players = [p for p in data["players"] if (p.get("name") or "").strip()]
    seasons = sorted(data.get("seasons", []), reverse=True)
    updated = data.get("updated", "")
    lastmod = updated if updated else date.today().isoformat()
    try:
        lastmod = datetime.fromisoformat(lastmod.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        lastmod = date.today().isoformat()

    slug_of = build_slug_map(players)
    neighbors_by_id, gpct_by_id = compute_neighbors(players)

    urls = [BASE_URL + "/", BASE_URL + "/p/index.html", BASE_URL + "/leaderboards/index.html"]

    for p in players:
        slug = slug_of[p["id"]]
        write("p/%s.html" % slug,
              render_player(p, slug, slug_of, neighbors_by_id[p["id"]], gpct_by_id, updated))
        urls.append("%s/p/%s.html" % (BASE_URL, slug))
    write("p/index.html", render_players_index(players, slug_of, gpct_by_id, updated))

    season_keys = ["career"] + seasons
    lb_pages = 0

    for board_key, _label in NAV_BOARDS:
        for season in season_keys:
            write("leaderboards/%s-%s.html" % (board_key, season),
                  render_full_board(board_key, season, players, slug_of, seasons, updated))
            urls.append("%s/leaderboards/%s-%s.html" % (BASE_URL, board_key, season))
            lb_pages += 1

    alias_pages = 0
    for season in season_keys:
        write("leaderboards/stat-padders-%s.html" % season,
              render_full_board("garbage-pts", season, players, slug_of, seasons, updated,
                                display="Garbage-Time Leaders"))
        alias_pages += 1

    write("leaderboards/index.html",
          render_leaderboards_index(players, slug_of, seasons, updated))

    write_sitemap(urls, lastmod)
    write_robots()

    print("Generated %d player pages, %d leaderboard pages (+%d stat-padders aliases), "
          "sitemap (%d urls), robots.txt"
          % (len(players), lb_pages, alias_pages, len(urls)))


if __name__ == "__main__":
    main()
