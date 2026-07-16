#!/usr/bin/env python3
"""Generate blog pages from ~/org training data (intervals.icu pulls).

Reads:  ~/org/run-log.org, ~/org/wellness-log.org, ~/org/plan-30k-agenda.org
Writes: content/running/log.md     (run timeline, published)
        content/running/health.md  (wellness log, DRAFT)
        content/running/calendar.md + data/weeks.json
        content/posts/runs/*.md    (one small post per run, regenerated)

Run it after `python3 ~/org/sync_plan_intervals.py pull`, then commit + deploy.
ANNOTATIONS below is meant to be hand-edited: it carries the story that the
numbers can't (why a run mattered, what was decided).
"""

import calendar as callib
import datetime as dt
import json
import re
from pathlib import Path

ORG = Path.home() / "org"
BLOG = Path(__file__).resolve().parent.parent
PLAN_START = dt.date(2026, 6, 29)

# Wk -> (type, target volume km, long-run target)  — from course.org week table
WEEKS = {
    1: ("base", 35, "12 km / 1:12"),
    2: ("build", 37, "13.5 km / 1:21"),
    3: ("deload", 28, "10 km / 1:00"),
    4: ("build", 39, "15 km / 1:30"),
    5: ("build", 42, "17 km / 1:42"),
    6: ("deload/race", 30, "UTFS 10 km trail (Aug 9)"),
    7: ("build", 44, "19 km / 1:54"),
    8: ("build", 46, "21 km / 2:06"),
    9: ("deload", 36, "16 km / 1:36"),
    10: ("build", 49, "23 km / 2:18"),
    11: ("build", 51, "25 km / 2:30"),
    12: ("race", 46, "Beluga 18 km trail (Sep 19)"),
    13: ("build", 52, "26 km / 2:36"),
    14: ("taper/race", 44, "Half 21.1 km (Oct 4)"),
    15: ("build", 53, "28 km / 2:48"),
    16: ("deload", 43, "22 km / 2:12"),
    17: ("PEAK", 50, "30 km / 3:00 — the goal"),
    18: ("recovery", 34, "12–15 km recovery"),
}

# date -> {"keywords": [...], "note": "...", "analysis": "..."} — HAND-EDIT ME
# note: 1-2 sentences (timeline + post). analysis: the coach's read, a
# fuller paragraph shown only on the single-run post.
ANNOTATIONS = {
    "2026-06-29": {
        "note": "Day 1 of the plan.",
        "analysis": "Day one, and the baseline fault is already on tape: an "
                    "\"easy\" run with 39 % of its time above Zone 2. Average "
                    "HR 140 sits inside the band, but the drift to 158 says "
                    "the effort was managed by feel, not by the cap. This is "
                    "precisely the habit the whole plan is built to retrain.",
    },
    "2026-06-30": {
        "analysis": "The optional Tuesday got used, which is fine — but it "
                    "repeated Monday's pattern almost exactly: 39 % above "
                    "Zone 2, max HR touching 164. Two warm \"easy\" runs in "
                    "two days is how invisible fatigue accumulates; the "
                    "volume isn't the risk here, the intensity creep is.",
    },
    "2026-07-01": {
        "keywords": ["volume creep"],
        "note": "Week-1 medium-long — 10 km where ~8 was planned, part of a "
                "42 km week against a ~35 km target.",
        "analysis": "The week-1 medium-long pulled both levers at once: well "
                    "over its scheduled duration and 42 % of it above Zone 2. "
                    "Aerobically it looked comfortable, which is exactly why "
                    "it's seductive — \"one variable at a time\" exists "
                    "because tissue doesn't negotiate. Most of week 1's "
                    "volume overshoot (42 km against ~35) traces to sessions "
                    "like this one.",
    },
    "2026-07-02": {
        "analysis": "Marginally better discipline than the two runs before "
                    "it (34 % above Zone 2), but the same signature: honest "
                    "effort, cap ignored late. The engine keeps making these "
                    "runs feel cheap; the plantar fascia doesn't get a vote — "
                    "until it does.",
    },
    "2026-07-04": {
        "keywords": ["milestone"],
        "note": "First long run of the plan. Decoupling 0.7 % — the aerobic "
                "engine is fine; the work is discipline, not fitness.",
        "analysis": "The week's redemption: 72:04 on a 72-minute cap, 76 % "
                    "Zone 2, and aerobic decoupling of 0.7 % — essentially a "
                    "flat line. When pace is allowed to be an output instead "
                    "of a target, the data is immaculate. The aerobic base "
                    "was never the question; the discipline on the other "
                    "five days of the week is.",
    },
    "2026-07-06": {
        "note": "First genuinely easy easy-run of the plan (78 % Z2), in 31 °C. "
                "Strength A in the evening — strength habit starts.",
        "analysis": "First run after the volume reckoning, and the correction "
                    "landed: 78 % Zone 2 in 31 °C — heat that usually drags "
                    "HR upward makes the discipline more impressive, not "
                    "less. Strength A in the evening started the other half "
                    "of the plan. This is what week 1 should have looked "
                    "like.",
    },
    "2026-07-08": {
        "keywords": ["model run"],
        "note": "Controlled medium-long: pace dead-steady 5:58→5:55→5:55, "
                "85 % Z2. What the plan is supposed to look like.",
        "analysis": "A model session, arguably the cleanest of the plan: 85 % "
                    "Zone 2, pace dead-steady at 5:58→5:55→5:55, duration on "
                    "the cap. The foot ached at the start, went quiet by "
                    "minute eight, and the unwavering splits prove no "
                    "compensation crept into the gait. File under \"what the "
                    "plan looks like when followed.\"",
    },
    "2026-07-09": {
        "note": "Slightly hot toward the end — the easy-too-hard creep to "
                "watch. Strength B in the evening: first week with both "
                "strength sessions done.",
        "analysis": "Good, not great: 75 % Zone 2 with a warm patch mid-run "
                    "and drift toward the cap by the end — the easy-too-hot "
                    "creep announcing itself again, gently. The evening's "
                    "Strength B closed the first week with both strength "
                    "sessions done, which matters more for October than any "
                    "single run does.",
    },
    "2026-07-11": {
        "keywords": ["off-plan"],
        "note": "Social long run with friends — +28 % over the 12 km / 72 min "
                "cap, at the fast-flat profile that historically flares my "
                "legs. Aerobically fine (4.7 % decoupling), and the foot "
                "passed every checkpoint afterwards. Bent, didn't break — "
                "and doesn't get to become a habit.",
        "analysis": "Off-plan by every metric that matters: +28 % over the "
                    "duration cap, 74 % Zone 3, at the fast-flat profile "
                    "that has historically preceded every flare. The engine "
                    "shrugged — 4.7 % decoupling on the biggest run of the "
                    "block. The redeeming data came after: the foot passed "
                    "every checkpoint, including the best morning of the "
                    "episode two days later — evidence the current load "
                    "sits inside tissue capacity, with some margin. Noted, "
                    "absorbed, and explicitly not a precedent.",
    },
    "2026-07-13": {
        "keywords": ["best discipline"],
        "note": "91 % Z2 — best zone discipline of the plan, on day 1 of a "
                "deliberately strict deload week.",
        "analysis": "91 % Zone 2 — the best zone discipline of the plan, "
                    "delivered on day one of a deliberately strict deload. "
                    "After Saturday's excursion, this is the response that "
                    "matters: no compensating, no testing, just the "
                    "prescription. A deload only works if it's actually a "
                    "deload.",
    },
    "2026-07-14": {
        "note": "Recovery-pace shakeout at HR 119, 98 % Zone 1 — deload "
                "executed like it means it. Strength A in the evening, "
                "one day late after Monday's dry-needling session.",
        "analysis": "An optional day used correctly: 98 % Zone 1 at HR 119 — "
                    "a genuine recovery jog, not a stealth workout. Strength "
                    "A in the evening, one day late to give Monday's dry "
                    "needling room to settle. Small decisions, correctly "
                    "sequenced.",
    },
    "2026-07-16": {
        "keywords": ["moved up"],
        "note": "Saturday's long run, moved to Thursday (weekend conflict) "
                "and taken to the trails — where it became part run, part "
                "orienteering: lots of stops to find the track.",
        "analysis": "The deload long run, relocated to Thursday and taken "
                    "off-road — where it turned into an orienteering "
                    "session: repeated stops to relocate the track kept the "
                    "average HR at 114 with 93 % of the hour in Zone 1, "
                    "never even brushing the Z2 ceiling. For a deload, "
                    "that's not a bug: 55 minutes of time-on-feet on varied "
                    "terrain at near-zero intensity is exactly what an "
                    "absorption week wants — and honest UTFS prep besides, "
                    "since that race will also be about terrain management, "
                    "not pace. The 8:54/km means nothing; the 150 spm "
                    "cadence says plenty of walking, which the climbs and "
                    "the map-checking explain. Week 3 closes around 25 km "
                    "of a ~28 target. The morning told its own story "
                    "though: the first clean post-needling read came in at "
                    "3/10 — both feet, the highest of the block, after the "
                    "plan's densest stretch of consecutive running days — "
                    "and the right arch murmured at 0.5–1 through the run. "
                    "Friday's rest lands well; the weekend mornings decide "
                    "whether week 4 opens at full prescription.",
    },
    "2026-07-15": {
        "note": "Deload medium-long, right on the 36-minute cap. Morning "
                "markers agree the recovery is landing: resting HR 40, "
                "HRV back to 66.",
        "analysis": "Three for three on the deload: 37:30 against a "
                    "36-minute cap, 78 % Zone 2, and the morning markers "
                    "agreeing loudly — resting HR 40 and HRV back at 66 are "
                    "the best readings of the block. The recovery isn't just "
                    "scheduled; it's landing. If the foot's morning trend "
                    "holds, the week-4 progression gate is opening.",
    },
}

# One-off session moves within a week (life happens): date -> agenda-style
# dict replacing the scheduled session when analyzing that day's run.
SESSION_OVERRIDES = {
    "2026-07-16": {"title": "Long run 60' Z2", "tag": "long"},  # Sat -> Thu, trail
}


def planned_by_date(sessions):
    d = {s["date"]: s for s in sessions}
    for iso, sess in SESSION_OVERRIDES.items():
        d[dt.date.fromisoformat(iso)] = sess
    return d


RUN_HEAD = re.compile(
    r"^\* (\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}) — (.+?) \((\w+)\)\s+\(id (\S+)\)"
)
STATS = re.compile(
    r"([\d.]+) km \| ([\d:]+) \| ([\d:]+)/km \| HR (\d+)/(\d+) \|.*load (\d+)"
)
# Planned-session activity names look like "<City> - S<week> <label>" —
# the city prefix is whatever Garmin auto-names, so don't hardcode it.
SESSION = re.compile(r".+? - S(\d+) (.+?)(?: \(\+ strength \w\))?$")


def parse_runs():
    runs = []
    cur = None
    for line in (ORG / "run-log.org").read_text().splitlines():
        m = RUN_HEAD.match(line)
        if m:
            cur = {"date": dt.date.fromisoformat(m[1]), "name": m[3],
                   "sport": m[4], "zones": {}}
            runs.append(cur)
        elif cur and (m := STATS.search(line)):
            cur.update(km=float(m[1]), time=m[2], pace=m[3],
                       hr=int(m[4]), hrmax=int(m[5]), load=int(m[6]))
        elif cur and line.strip().startswith("HR zones:"):
            for z, pct in re.findall(r"(Z\d):(\d+)%", line):
                cur["zones"][z] = int(pct)
    return [r for r in runs if r["date"] >= PLAN_START and "km" in r]


def week_no(d):
    return (d - PLAN_START).days // 7 + 1


def session_label(run, sess=None):
    m = SESSION.match(run["name"])
    if m:
        label = m[2]
        return "Long run" if "longue" in label.lower() else label
    if sess:  # scheduled that day; the activity just wasn't renamed (early wks)
        return re.sub(r" \(\+ strength \w\)$", "", sess["title"])
    # No scheduled session that day. Tue/Sun are the plan's deliberately
    # unscheduled optional days — that's on-plan, not off-plan.
    if run["date"].weekday() in (1, 6):
        return "Optional recovery" if run["hr"] < 130 else "Optional easy"
    return "Long run (unscheduled)" if run["km"] > 10 else "Easy (unscheduled)"


def keywords(run, sess=None):
    kws = []
    label = session_label(run, sess).lower()
    for k, tag in (("medium", "medium-long"), ("long", "long-run"),
                   ("recovery", "recovery"), ("easy", "easy")):
        if k in label:
            kws.append(tag)
            break
    if label.startswith("optional"):
        kws.append("optional")
    if run.get("sport") == "TrailRun":
        kws.append("trail")
    wk = WEEKS.get(week_no(run["date"]))
    if wk and "deload" in wk[0]:
        kws.append("deload")
    z2 = run["zones"].get("Z2", 0)
    hot = sum(run["zones"].get(z, 0) for z in ("Z3", "Z4", "Z5"))
    if z2 >= 70:
        kws.append(f"{z2}% Z2 ✓")
    elif hot >= 30:
        kws.append(f"{hot}% above Z2 — hot")
    kws += ANNOTATIONS.get(str(run["date"]), {}).get("keywords", [])
    return kws


def run_minutes(t):
    m, s = t.split(":")
    return int(m) + int(s) / 60


def execution_line(run, sess):
    if sess and sess["tag"] == "race":
        plan = "race day — controlled effort, not raced"
    elif sess and (m := re.search(r"(\d+)' Z2", sess["title"])):
        pm = int(m[1])
        delta = (run_minutes(run["time"]) - pm) / pm * 100
        plan = f"plan {pm}′ Z2 → ran {run['time']} ({delta:+.0f} %)"
    else:
        plan = "optional day, nothing scheduled"
    return f"*Execution: {plan} · HR {run['hr']} avg (Z2 cap 145)*"


def zone_band(run):
    """Garmin-style time-in-zones band: stacked colored segments Z1→Z5."""
    z = run["zones"]
    parts, alt = [], []
    for k in ("Z1", "Z2", "Z3", "Z4", "Z5"):
        pct = z.get(k, 0)
        if not pct:
            continue
        alt.append(f"{k} {pct} %")
        label = f"{k} {pct}%" if pct >= 14 else (f"{pct}%" if pct >= 8 else "")
        parts.append(f'<span class="zb zb-{k.lower()}" style="width:{pct}%"'
                     f' title="{k}: {pct} %">{label}</span>')
    return (f'<div class="zoneband" role="img" aria-label="Time in zones: '
            f'{", ".join(alt)}">{"".join(parts)}</div>')


def post_slug(run, sess):
    base = re.sub(r"[^a-z0-9]+", "-", session_label(run, sess).lower()).strip("-")
    return f"{run['date']}-{base}"


def fmt_run(run, sess):
    day = run["date"].strftime("%a %b %-d")
    tags = " ".join(f"`{k}`" for k in keywords(run, sess))
    out = [f"**[{day} — {session_label(run, sess)}](/posts/runs/{post_slug(run, sess)}/)**  ",
           f"{run['km']:.2f} km · {run['time']} · {run['pace']}/km · "
           f"HR {run['hr']} avg / {run['hrmax']} max  ",
           tags + "  ",
           execution_line(run, sess),
           "", zone_band(run)]
    note = ANNOTATIONS.get(str(run["date"]), {}).get("note")
    if note:
        out.append(f"\n> {note}")
    return "\n".join(out)


def write_log(runs, sessions):
    today = dt.date.today()
    planned = planned_by_date(sessions)
    by_week = {}
    for r in runs:
        by_week.setdefault(week_no(r["date"]), []).append(r)
    parts = [f"""+++
title = "Training log"
date = {PLAN_START}
lastmod = {today}
tags = ["30k", "training-log"]
draft = false
+++

One entry per run, newest week first — goal and execution keywords on
each. The plan behind it: [as designed](/running/program-original/) ·
[current, with changelog](/running/program/). Generated from
[intervals.icu](https://intervals.icu) data; the notes are mine.
"""]
    for wk in sorted(by_week, reverse=True):
        wtype, vol, longrun = WEEKS[wk]
        start = PLAN_START + dt.timedelta(weeks=wk - 1)
        end = start + dt.timedelta(days=6)
        done = sum(r["km"] for r in by_week[wk])
        parts.append(
            f"## Week {wk} — {wtype} "
            f"({start.strftime('%b %-d')}–{end.strftime('%b %-d')})\n\n"
            f"Target ~{vol} km · long run: {longrun} · "
            f"ran {done:.1f} km{' so far' if end >= today else ''}\n")
        parts += [fmt_run(r, planned.get(r["date"])) + "\n"
                  for r in sorted(by_week[wk], key=lambda r: r["date"],
                                  reverse=True)]
    (BLOG / "content/running/log.md").write_text("\n".join(parts))


def write_health():
    today = dt.date.today()
    rows = [l for l in (ORG / "wellness-log.org").read_text().splitlines()
            if l.startswith("| 2")]
    header = ("| Date | RHR | RHR 7d | HRV | HRV 7d | Sleep h | Form |\n"
              "|------|-----|--------|-----|--------|---------|------|")
    md_rows = []
    for l in reversed(rows):
        c = [x.strip() for x in l.strip("|").split("|")]
        md_rows.append(f"| {c[0]} | {c[1]} | {c[2]} | {c[3]} | {c[4]} | "
                       f"{c[5] or '—'} | {c[10]} |")
    (BLOG / "content/running/health.md").write_text(f"""+++
title = "Health log"
date = {today}
lastmod = {today}
tags = ["30k", "health"]
draft = true
+++

Daily wellness markers (Garmin → intervals.icu), newest first. 7-day
rolling means are the signal; single days are noise. Form = CTL − ATL
(negative = carrying fatigue). Green-light criteria for progression:
HRV 7d recovering toward ~60, RHR 7d ≤ 42, foot morning score trending
≤ 1.

{header}
{chr(10).join(md_rows)}
""")


AGENDA_HEAD = re.compile(r"^\* (DONE )?S(\d+) (.+?)\s+:(\w+):$")


def parse_agenda():
    sessions = []
    cur = None
    for line in (ORG / "plan-30k-agenda.org").read_text().splitlines():
        if m := AGENDA_HEAD.match(line):
            cur = {"done": bool(m[1]), "wk": int(m[2]), "title": m[3],
                   "tag": m[4]}
        elif cur and (m := re.search(r"<(\d{4}-\d{2}-\d{2})", line)):
            cur["date"] = dt.date.fromisoformat(m[1])
            sessions.append(cur)
            cur = None
    return sessions


def chip_label(s):
    t = re.sub(r" \(race\)$", "", s["title"])
    t = re.sub(r" Z2( \(\+ strength \w\))?$", "", t)
    t = t.replace("Medium-long", "ML").replace("Long run", "Long")
    t = t.replace("'", "′")
    return ("✓ " if s["done"] else "") + t


def write_calendar(sessions):
    today = dt.date.today()
    by_date = {}
    for s in sessions:
        by_date.setdefault(s["date"], []).append(s)
    first, last = min(by_date), max(by_date)
    months = []
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        months.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    html = ['<div class="cal-legend">']
    for cls, label in (("easy", "Easy"), ("ml", "Medium-long"),
                       ("long", "Long run"), ("race", "Race"),
                       ("str", "Strength")):
        html.append(f'<span class="cal-chip cal-chip--{cls}">{label}</span>')
    html.append("</div>")
    for y, m in months:
        html.append(f'<div class="cal-scroll"><section class="cal-month">'
                    f"<h3>{callib.month_name[m]} {y}</h3>"
                    f'<div class="cal-grid">')
        html += [f'<div class="cal-dow">{d}</div>'
                 for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")]
        for week in callib.Calendar().monthdatescalendar(y, m):
            for day in week:
                if day.month != m:
                    html.append('<div class="cal-day cal-day--out"></div>')
                    continue
                cls = " cal-day--today" if day == today else ""
                cell = [f'<div class="cal-day{cls}">'
                        f'<span class="cal-date">{day.day}</span>']
                for s in by_date.get(day, []):
                    cell.append(f'<span class="cal-chip cal-chip--{s["tag"]}"'
                                f' title="{s["title"]}">{chip_label(s)}</span>')
                    if st := re.search(r"\(\+ strength (\w)\)", s["title"]):
                        cell.append(f'<span class="cal-chip cal-chip--str">'
                                    f"Str {st[1]}</span>")
                cell.append("</div>")
                html.append("".join(cell))
        html.append("</div></section></div>")

    (BLOG / "content/running/calendar.md").write_text(f"""+++
title = "Program calendar"
date = {PLAN_START}
lastmod = {today}
tags = ["30k", "plan"]
draft = false
+++

Every scheduled session of the 18-week program, ✓-marked as it
happens (today is outlined). Colors group session types; races in
green are run controlled, not raced. Details:
[the program](/running/program/) · [run-by-run log](/running/log/).

{chr(10).join(html)}
""")


def write_weeks_json(runs, sessions):
    today = dt.date.today()
    long_by_wk = {}
    for s in sessions:
        if s["tag"] == "race":
            label = re.sub(r" \(race\)$", "", s["title"])
            long_by_wk[s["wk"]] = f"{label} ({s['date'].strftime('%b %-d')})"
    km = {}
    for r in runs:
        wk = week_no(r["date"])
        km[wk] = km.get(wk, 0) + r["km"]
    ml = {1: 8, 2: 9, 3: 6, 4: 9, 5: 10, 6: 6, 7: 10, 8: 11, 9: 8, 10: 11,
          11: 12, 12: 8, 13: 12, 14: 7, 15: 12, 16: 9, 17: 8, 18: 6}
    out = []
    for wk, (wtype, vol, longrun) in WEEKS.items():
        start = PLAN_START + dt.timedelta(weeks=wk - 1)
        end = start + dt.timedelta(days=6)
        status = ("done" if end < today
                  else "current" if start <= today else "upcoming")
        out.append({
            "wk": wk, "starts": str(start), "ml": ml[wk],
            "long": long_by_wk.get(wk, longrun), "type": wtype,
            "target": vol,
            "actual": round(km[wk], 1) if wk in km else None,
            "status": status,
        })
    (BLOG / "data").mkdir(exist_ok=True)
    (BLOG / "data/weeks.json").write_text(json.dumps(out, indent=1))


def write_run_posts(runs, sessions):
    outdir = BLOG / "content/posts/runs"
    outdir.mkdir(parents=True, exist_ok=True)
    for old in outdir.glob("*.md"):
        old.unlink()
    planned = planned_by_date(sessions)
    for r in runs:
        sess = planned.get(r["date"])
        label = session_label(r, sess).replace("'", "′")
        tags = ["run"] + [k for k in keywords(r, sess) if "%" not in k]
        wk = week_no(r["date"])
        ann = ANNOTATIONS.get(str(r["date"]), {})
        note = ann.get("note", "")
        read = ann.get("analysis", "")
        coach = f"## The coach's read\n\n{read}\n" if read else ""
        (outdir / f"{post_slug(r, sess)}.md").write_text(f"""+++
title = "{label} — {r['km']:.1f} km"
date = {r['date']}
tags = {json.dumps(tags)}
summary = "Week {wk}: {r['km']:.2f} km · {r['time']} · {r['pace']}/km · HR {r['hr']}"
+++

{r['km']:.2f} km · {r['time']} · {r['pace']}/km · HR {r['hr']} avg / {r['hrmax']} max

{execution_line(r, planned.get(r['date']))}

{zone_band(r)}

{f'> {note}' if note else ''}

{coach}
Part of [week {wk}](/running/log/) of the [30 km build](/running/program/).
""")


def write_prompt_template():
    today = dt.date.today()
    src = (ORG / "running-plan-prompt-template.org").read_text()
    (BLOG / "content/running/prompt-template.md").write_text(f"""+++
title = "Build your own program: the prompt template"
date = 2026-07-15
lastmod = {today}
tags = ["ai", "plan", "tooling"]
summary = "The reusable intake prompt that encodes this plan's whole methodology — fill in your data, paste it into an AI conversation, get your own injury-first program."
+++

This is the intake prompt that encodes the whole methodology behind
[my 30 km program](/running/program-original/) — the injury-first
priorities, the heart-rate discipline, the guardrails, the output
format. Fill in the `YOUR INTAKE` section with your own history (real
export data beats self-estimates), paste the entire thing into a
conversation with an AI like Claude, and answer its follow-up
questions honestly. Background: [how this works](/posts/how-this-works/).
Template, scripts and Claude skills are bundled on GitHub:
[Pacane/running-plan-kit](https://github.com/Pacane/running-plan-kit).

It produces a self-coached training plan, not medical advice.

````org
{src}
````
""")


# Scripts published for download at /code/. FORBIDDEN is a fail-closed guard:
# if any personal marker ever shows up in a script, publishing aborts.
PUBLIC_SCRIPTS = [
    (ORG / "sync_plan_intervals.py",
     "intervals.icu bridge — pushes the plan as structured workouts; pulls "
     "completed runs, daily wellness (RHR/HRV/sleep/load) and the agenda "
     "back into org files; sets strength load from RPE so lifting counts "
     "in CTL/ACWR. Auth via env var or Emacs auth-source."),
    (ORG / "sync_strength_garmin.py",
     "Garmin Connect bridge — creates the strength sessions (A/B/ISO) as "
     "native watch workouts (animations, rep counting, rest timers) and "
     "schedules them on the calendar, skipping race weekends."),
    (BLOG / "scripts/generate_training_pages.py",
     "this blog's generator — turns the org data into the run log, "
     "calendar, live week table, health page and per-run posts. "
     "(Yes, it publishes itself.)"),
]
# Stored reversed so the guard doesn't trip on its own source when the
# generator publishes itself. (The GitHub handle is deliberately public —
# the kit repo is linked from the tools page — so it's not in this list.)
FORBIDDEN = [w[::-1] for w in
             ["524926i", "leoj", "revarb", "siocebeuqmai", "reittort",
              "liamg@", "yaneugas"]]


def publish_scripts():
    today = dt.date.today()
    outdir = BLOG / "static/code"
    outdir.mkdir(parents=True, exist_ok=True)
    rows = []
    for path, desc in PUBLIC_SCRIPTS:
        src = path.read_text()
        low = src.lower()
        hits = [w for w in FORBIDDEN if w in low]
        if hits:
            raise SystemExit(
                f"REFUSING to publish {path.name}: found {hits}")
        (outdir / path.name).write_text(src)
        n = len(src.splitlines())
        rows.append(f"## [{path.name}](/code/{path.name})\n\n"
                    f"{n} lines — {desc}\n")
    (BLOG / "content/running/tools.md").write_text(f"""+++
title = "The scripts"
date = 2026-07-15
lastmod = {today}
tags = ["tooling", "ai"]
summary = "The three Python scripts behind this whole setup — intervals.icu sync, Garmin strength workouts, and the blog generator — free to download and adapt."
+++

The plumbing described in [how this works](/posts/how-this-works/), as
plain downloadable Python — also on GitHub with the prompt template and
the Claude skills bundled:
[Pacane/running-plan-kit](https://github.com/Pacane/running-plan-kit). No packaging, no framework — read them top to
bottom, adapt to your own plan (the structure they expect comes from the
[prompt template](/running/prompt-template/)). They hold no credentials:
API keys come from the environment or Emacs auth-source, the Garmin OAuth
token lives in your home directory. Use at your own risk; they were built
for my setup, in conversation with an AI, and it shows in the best way.

{chr(10).join(rows)}
""")


if __name__ == "__main__":
    runs = parse_runs()
    sessions = parse_agenda()
    write_log(runs, sessions)
    write_health()
    write_calendar(sessions)
    write_weeks_json(runs, sessions)
    write_run_posts(runs, sessions)
    write_prompt_template()
    publish_scripts()
    print(f"log.md: {len(runs)} runs · health.md · "
          f"calendar.md: {len(sessions)} sessions · weeks.json · "
          f"posts/runs: {len(runs)} posts")
