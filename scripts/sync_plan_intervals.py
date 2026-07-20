#!/usr/bin/env python3
"""
Sync the 30 km plan (roam/20250327164425-course.org) to intervals.icu as planned
workouts (auto-push to your Garmin watch) AND/OR to an org file for the Emacs agenda.

SETUP (only needed for intervals.icu upload)
  1. intervals.icu -> Settings -> Developer Settings -> generate an API key.
  2. Make sure your running LTHR (173) is set in intervals.icu (Settings -> your run
     sport). HR targets use % of LTHR; if LTHR isn't set, replace "76-84% LTHR" with
     "Z2 HR" in this file.
  3. intervals.icu -> Connections -> Garmin -> enable "Upload planned workouts".

USAGE
  export INTERVALS_API_KEY=xxxxxxxxxxxx        # optional if key is in ~/.authinfo.gpg (auth-source)
  export INTERVALS_ATHLETE_ID=auto             # optional; "auto"/"0" -> resolved from the key
  export INTERVALS_SHIFT_WEEKS=0               # optional; shift TRAINING by N weeks
  export INTERVALS_SHIFT_FROM=2026-08-01       # optional; only shift workouts on/after this
                                               #   date (default: today -> past never moves)
  export INTERVALS_HR_MODE=range               # optional; range (%LTHR->bpm, default) | zone
  export INTERVALS_ORG_FILE=~/org/plan-30k-agenda.org   # optional; org output path
  export INTERVALS_STRENGTH_RPE=3              # optional; default RPE -> strength load (pull/fixstrength)
  python3 sync_plan_intervals.py dry           # print what WOULD be created (no changes)
  python3 sync_plan_intervals.py org           # write the org agenda file (local, no key)
  python3 sync_plan_intervals.py whoami        # verify the key + print YOUR athlete id
  python3 sync_plan_intervals.py latest        # summarize your most recent run (for review)
  python3 sync_plan_intervals.py pull          # append NEW runs -> ~/org/run-log.org (+ fix strength load)
  #   INTERVALS_PULL_SINCE=2026-06-30 ... pull  # backfill: re-scan from a date (deduped by id)
  python3 sync_plan_intervals.py fixstrength   # set strength load from RPE (also runs inside pull)
  python3 sync_plan_intervals.py wellness      # RHR/HRV/sleep -> ~/org/wellness-log.org (also inside pull)
  #   INTERVALS_WELLNESS_DAYS=28 INTERVALS_WELLNESS_FILE=~/org/wellness-log.org (defaults)
  python3 sync_plan_intervals.py create        # upload to intervals.icu + refresh org file
  python3 sync_plan_intervals.py delete        # remove all plan events from intervals.icu

NOTES
- Athlete id defaults to "auto": the script calls /athlete/0 (the authenticated athlete)
  to resolve your real id, so a wrong hard-coded id can't cause a 403.
- HTTP errors print the server's message (not a traceback). 401/403 = key or permissions.
- Idempotent: events carry external_id "plan30k-*"; create/delete clear those first.
- Schedules 4 core sessions/week (Mon easy, Wed medium-long, Thu easy, Sat long).
- INTERVALS_SHIFT_FROM: only workouts on/after that date shift; races keep real fixed dates.
- The org file is GENERATED (overwritten) -> don't hand-edit; add it to org-agenda-files.
- Stdlib only (no pip install).
"""
import os, sys, json, base64, re, datetime as dt
import urllib.request, urllib.parse, urllib.error

API = "https://intervals.icu/api/v1"


def _auth_source_key():
    """API key via Emacs auth-source (~/.authinfo.gpg, machine api.intervals.icu).
    The key never travels in cleartext: no shell arg, no file, no history."""
    import subprocess
    el = ('(let* ((m (car (or (auth-source-search :host "api.intervals.icu" :max 1)'
          '                   (auth-source-search :host "intervals.icu" :max 1))))'
          '       (s (and m (plist-get m :secret))))'
          '  (or (and (functionp s) (funcall s)) s))')
    try:
        out = subprocess.run(["emacsclient", "--eval", el], capture_output=True,
                             text=True, timeout=15).stdout.strip()
    except Exception:
        return None
    return out[1:-1] if len(out) > 1 and out[0] == out[-1] == '"' else None


KEY = (os.environ.get("INTERVALS_API_KEY") or "").strip() or _auth_source_key()
ATHLETE = os.environ.get("INTERVALS_ATHLETE_ID", "auto")   # "auto"/"0" -> resolve via /athlete/0
SHIFT = int(os.environ.get("INTERVALS_SHIFT_WEEKS", "0"))
_from = os.environ.get("INTERVALS_SHIFT_FROM")   # ISO date; only workouts on/after it shift
SHIFT_FROM = dt.date.fromisoformat(_from) if _from else dt.date.today()
ORG_FILE = os.path.expanduser(os.environ.get("INTERVALS_ORG_FILE", "~/org/plan-30k-agenda.org"))
HR_MODE = os.environ.get("INTERVALS_HR_MODE", "range").lower()   # range (%LTHR->bpm) | zone (ZoneN HR)
RUNLOG = os.path.expanduser(os.environ.get("INTERVALS_RUNLOG", "~/org/run-log.org"))
STATE_FILE = os.path.expanduser("~/org/.last-run-pull")
WELLNESS_LOG = os.path.expanduser(os.environ.get("INTERVALS_WELLNESS_FILE", "~/org/wellness-log.org"))
WELLNESS_DAYS = int(os.environ.get("INTERVALS_WELLNESS_DAYS", "28"))
PREFIX = "plan30k"
TIME = "T12:00:00"  # local start time on the day; cosmetic
DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# (Monday, medium-long minutes, Saturday long minutes)   None = race week (see build_events)
WEEKS = [
    ("2026-06-29", 48,  72),
    ("2026-07-06", 54,  81),
    ("2026-07-13", 36,  60),   # deload
    ("2026-07-20", 54,  90),
    ("2026-07-27", 60, 102),
    ("2026-08-03", 36,  78),   # deload (+ UTFS 10 km trail race Sun Aug 9)
    ("2026-08-10", 60, 114),
    ("2026-08-17", 66, 126),
    ("2026-08-24", 48,  96),   # deload
    ("2026-08-31", 66, 138),
    ("2026-09-07", 72, 150),
    ("2026-09-14", 48, None),  # S12: TRAIL 18k race, Sat Sep 19 (fixed)
    ("2026-09-21", 72, 156),
    ("2026-09-28", 42, None),  # S14: HALF race, Sun Oct 4 (fixed)
    ("2026-10-05", 72, 168),
    ("2026-10-12", 54, 132),   # deload
    ("2026-10-19", 48, 180),   # S17: 30 km PEAK, Sat Oct 24
    ("2026-10-26", 36,  90),   # recovery
]
def hr(band):
    """HR target token for a step, honoring INTERVALS_HR_MODE.
    range -> % of LTHR (Garmin renders an absolute bpm range); zone -> Garmin HR zone."""
    if HR_MODE == "zone":
        return {"easy": "Z2 HR", "long": "Z2 HR", "recov": "Z1 HR"}[band]
    return {"easy": "76-84% LTHR", "long": "76-83% LTHR", "recov": "70-80% LTHR"}[band]


EASY_MIN = int(os.environ.get("INTERVALS_EASY_MIN", "35"))  # base easy-run minutes
# Sensation-gated easy-run progression: weeks listed here override EASY_MIN.
# Keep past weeks' values intact (the blog reads history from the agenda).
# 2026-07-20: wk-4 gate passed (foot <=1 through deload, RHR/HRV green) -> 40'.
EASY_MIN_BY_WEEK = {w: 40 for w in range(4, 19)}


def easy_min(week):
    return EASY_MIN_BY_WEEK.get(week, EASY_MIN)


def dstr(monday, offset):
    """Training date = Monday + offset days; shifted by SHIFT weeks ONLY if the original
    date is on/after SHIFT_FROM (so past/kept sessions don't move). Races use fixed dates."""
    base = dt.date.fromisoformat(monday) + dt.timedelta(days=offset)
    if SHIFT and base >= SHIFT_FROM:
        base += dt.timedelta(days=SHIFT * 7)
    return base.isoformat()


def ev(date, name, desc, tag):
    return {
        "category": "WORKOUT",
        "start_date_local": date + TIME,
        "type": "Run",
        "name": name,
        "description": desc,
        "external_id": f"{PREFIX}-{tag}",
    }


def build_events():
    out = []
    for i, (mon, ml, lng) in enumerate(WEEKS, 1):
        em = easy_min(i)
        easy_desc = f"- {em}m {hr('easy')}"
        out.append(ev(dstr(mon, 0), f"S{i} Easy {em}' Z2 (+ strength A)", easy_desc, f"{i}-mon"))
        out.append(ev(dstr(mon, 2), f"S{i} Medium-long {ml}' Z2", f"- {ml}m {hr('easy')}", f"{i}-wed"))
        out.append(ev(dstr(mon, 3), f"S{i} Easy {em}' Z2 (+ strength B)", easy_desc, f"{i}-thu"))
        if i == 6:  # UTFS 10 km trail race: REAL fixed date (Sun), on a deload week
            out.append(ev(dstr(mon, 5), f"S{i} Easy shakeout 25' Z1 (optional/rest)",
                          f"- 25m {hr('recov')}", f"{i}-sat"))
            out.append(ev("2026-08-09", "S6 UTFS 10 km trail (race)",
                          "B race, run EASY like the June 6 trail 10k (avg HR ~134, all Z1-Z2). "
                          "HIKE the climbs (~670 m D+, Mont Sacre-Coeur wall); control the descents. "
                          "Not a race - the 30 km is the goal.", "6-race"))
        elif i == 12:  # trail race: REAL fixed date, never shifted
            out.append(ev("2026-09-19", "S12 TRAIL 18 km (race)",
                          "B race - by effort/terrain, Lone Peaks. No strict Z2 target.", "12-race"))
        elif i == 14:  # half race: REAL fixed date, never shifted
            out.append(ev("2026-10-04", "S14 Half 21.1 km (race)",
                          "B race - at ease / comfortable tempo, NOT all-out. The 30 km is still the goal.", "14-race"))
        elif lng:
            if i == 17:
                name = f"S{i} GOAL 30 km ({lng}')"
                desc = (f"- {lng}m {hr('long')}\n\nTreat like a RACE: taper before, "
                        f"recover fully after. Fuel 30-60g carbs/h from 75'. Cadence ~175-180.")
            elif i == 18:
                name = f"S{i} Recovery long run {lng}'"
                desc = f"- {lng}m {hr('recov')}"
            else:
                name = f"S{i} Long run {lng}' Z2"
                desc = f"- {lng}m {hr('long')}\n\nFuel 30-60g carbs/h from 75'. Cadence ~175-180."
            out.append(ev(dstr(mon, 5), name, desc, f"{i}-sat"))
    out.sort(key=lambda e: e["start_date_local"])
    return out


def wtype(name):
    n = name.lower()
    if "race" in n:
        return "race"
    if "medium-long" in n:
        return "ml"
    if "easy" in n:
        return "easy"
    return "long"


def _done_dates():
    """ISO dates with at least one run in RUNLOG (filled by the pull mode)."""
    if not os.path.exists(RUNLOG):
        return set()
    return set(re.findall(r"(?m)^\* (\d{4}-\d{2}-\d{2})T", open(RUNLOG).read()))


def write_org(evs):
    done = _done_dates()
    L = ["#+title: Plan 30 km - agenda",
         "#+category: 30km",
         "#+filetags: :run:",
         "",
         "# Generated by sync_plan_intervals.py (org mode) - do NOT hand-edit (overwritten on",
         "# every regeneration). DONE = a run exists that day in run-log.org -> run the pull",
         "# mode to refresh. Detailed tracking: the Tracking table / intervals.icu.",
         ""]
    for e in evs:
        d = dt.date.fromisoformat(e["start_date_local"][:10])
        mark = "DONE " if d.isoformat() in done else ""
        L.append(f"* {mark}{e['name']}  :{wtype(e['name'])}:")
        L.append(f"  <{d.isoformat()} {DOW[d.weekday()]}>")
        for line in e["description"].split("\n"):
            if line.strip():
                L.append("  " + line)
        L.append("")
    with open(ORG_FILE, "w") as f:
        f.write("\n".join(L) + "\n")
    note = f", shift={SHIFT}w from {SHIFT_FROM}" if SHIFT else ""
    print(f"Wrote {len(evs)} workouts to {ORG_FILE}{note}")


def req(method, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(API + path, data=body, method=method)
    r.add_header("Authorization", "Basic " + base64.b64encode(f"API_KEY:{KEY}".encode()).decode())
    # Cloudflare (error 1010) blocks the default "Python-urllib" User-Agent -> look like a browser.
    r.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                 "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36")
    r.add_header("Accept", "application/json")
    if body:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:400]
        hint = ""
        if e.code in (401, 403):
            hint = ("\n-> 401/403 = key or permissions. Check the API key (Settings -> Developer "
                    "Settings, copied in full). The athlete id is auto-resolved via /athlete/0; "
                    "run `whoami` to confirm.")
        sys.exit(f"HTTP {e.code} on {method} {path}\nServer response: {msg}{hint}")
    except urllib.error.URLError as e:
        sys.exit(f"Network error contacting intervals.icu: {e.reason}")


def resolve_athlete():
    """Turn 'auto'/'0'/'' into the real athlete id via /athlete/0 (authenticated athlete)."""
    global ATHLETE
    if ATHLETE not in ("auto", "0", "", None):
        return ATHLETE
    me = req("GET", "/athlete/0")
    ATHLETE = (me or {}).get("id") or ATHLETE
    if ATHLETE in ("auto", "0", "", None):
        sys.exit("Could not resolve the athlete id via /athlete/0. Set INTERVALS_ATHLETE_ID.")
    return ATHLETE


def list_plan_events():
    q = urllib.parse.urlencode({"oldest": "2026-06-01", "newest": "2027-06-01", "category": "WORKOUT"})
    evs = req("GET", f"/athlete/{ATHLETE}/events?{q}") or []
    return [e for e in evs if (e.get("external_id") or "").startswith(PREFIX)]


def delete_plan():
    existing = list_plan_events()
    for e in existing:
        req("DELETE", f"/athlete/{ATHLETE}/events/{e['id']}")
    print(f"Deleted {len(existing)} existing {PREFIX} events.")


def fmt_pace(dist_km, sec):
    if not dist_km or not sec:
        return "?"
    p = (sec / 60) / dist_km
    return f"{int(p)}:{int((p % 1) * 60):02d}/km"


def latest():
    """Print a review-ready summary of the most recent run from intervals.icu."""
    today = dt.date.today()
    q = urllib.parse.urlencode({"oldest": (today - dt.timedelta(days=4)).isoformat(),
                                "newest": today.isoformat()})
    acts = req("GET", f"/athlete/{ATHLETE}/activities?{q}") or []
    runs = [a for a in acts if a.get("type") in ("Run", "TrailRun", "VirtualRun")]
    if not runs:
        print("No run found in the last 4 days (not synced yet?).")
        return
    a = sorted(runs, key=lambda x: x.get("start_date_local", ""))[-1]
    d = req("GET", f"/activity/{a.get('id')}") or a          # full detail; fallback to summary
    dist = (d.get("distance") or 0) / 1000
    mv = int(d.get("moving_time") or 0)
    el = int(d.get("elapsed_time") or 0)
    print(f"=== {d.get('name', '(unnamed)')} | {d.get('start_date_local', '')[:16]} | {d.get('type')} ===")
    print(f"Distance       : {dist:.2f} km")
    print(f"Moving time    : {mv // 60}:{mv % 60:02d}  (elapsed {el // 60}:{el % 60:02d})")
    print(f"Avg pace       : {fmt_pace(dist, mv)}")
    print(f"Avg / max HR   : {d.get('average_heartrate', '?')} / {d.get('max_heartrate', '?')} bpm")
    print(f"Avg cadence    : {d.get('average_cadence', '?')} spm")
    print(f"Elevation gain : {d.get('total_elevation_gain', '?')} m")
    print(f"Load / Intens  : {d.get('icu_training_load', '?')} / {d.get('icu_intensity', '?')}")
    dec = d.get("decoupling")
    if dec is not None:
        print(f"Decoupling     : {dec:.1f}%  (HR vs pace drift; <5% = good aerobic shape)")
    zt = d.get("icu_hr_zone_times")
    if zt:
        tot = sum(zt) or 1
        print("Time per HR zone:")
        for i, s in enumerate(zt, 1):
            if s:
                print(f"  Z{i}: {s // 60}:{s % 60:02d} ({100 * s / tot:.0f}%)")
    print(f"\n(activity id {d.get('id')})")


def format_run_org(d):
    dist = (d.get("distance") or 0) / 1000
    mv = int(d.get("moving_time") or 0)
    date = (d.get("start_date_local") or "")[:16]
    out = [f"* {date} — {d.get('name', '(run)')} ({d.get('type')})  (id {d.get('id')})",
           f"  {dist:.2f} km | {mv // 60}:{mv % 60:02d} | {fmt_pace(dist, mv)} | "
           f"HR {d.get('average_heartrate', '?')}/{d.get('max_heartrate', '?')} | "
           f"cad {d.get('average_cadence', '?')} | D+ {d.get('total_elevation_gain', '?')}m | "
           f"load {d.get('icu_training_load', '?')}"]
    dec = d.get("decoupling")
    if dec is not None:
        out.append(f"  Decoupling {dec:.1f}%")
    zt = d.get("icu_hr_zone_times")
    if zt:
        tot = sum(zt) or 1
        zs = " ".join(f"Z{i}:{100 * s / tot:.0f}%" for i, s in enumerate(zt, 1) if s)
        out.append(f"  HR zones: {zs}")
    return "\n".join(out)


LOG_HEADER = "#+title: Run log (pull intervals.icu)\n#+category: run-log\n\n"


def parse_entries(txt):
    """Parse RUNLOG into [(date_sortkey, id, block_text)] from '* ...' subtrees."""
    out = []
    for b in re.findall(r"(?ms)^\* .*?(?=^\* |\Z)", txt):
        b = b.rstrip("\n")
        head = b.splitlines()[0]
        m = re.match(r"\* (\S+)", head)
        idm = re.search(r"\(id (\w+)\)", b)
        out.append((m.group(1) if m else "", idm.group(1) if idm else head, b))
    return out


def pull_runs():
    """Fetch runs since the last pull (or INTERVALS_PULL_SINCE for a backfill), merge into RUNLOG
    kept SORTED by date and deduped by id. Non-run activities in the window are listed."""
    state = open(STATE_FILE).read().strip() if os.path.exists(STATE_FILE) else None
    override = os.environ.get("INTERVALS_PULL_SINCE")   # YYYY-MM-DD -> re-scan this range (backfill)
    since = override or (state[:10] if state else (dt.date.today() - dt.timedelta(days=21)).isoformat())
    q = urllib.parse.urlencode({"oldest": since, "newest": dt.date.today().isoformat()})
    acts = req("GET", f"/athlete/{ATHLETE}/activities?{q}") or []
    is_run = lambda a: "run" in (a.get("type") or "").lower()   # Run, TrailRun, VirtualRun, Treadmill...
    runs = [a for a in acts if is_run(a)]
    skipped = [a for a in acts if not is_run(a)]
    if state and not override:
        runs = [a for a in runs if (a.get("start_date_local") or "") > state]
    existing = parse_entries(open(RUNLOG).read()) if os.path.exists(RUNLOG) else []
    have = {aid for _, aid, _ in existing}
    runs = [a for a in runs if str(a.get("id")) not in have]   # dedup vs file
    runs.sort(key=lambda x: x.get("start_date_local", ""))
    if skipped:
        print("Non-run activities in the window (ignored):")
        for a in sorted(skipped, key=lambda x: x.get("start_date_local", "")):
            print(f"  {(a.get('start_date_local') or '')[:10]}  {a.get('type')} — {a.get('name', '')}")
    if not runs:
        print(f"No NEW runs since {override or state or since}.")
        return
    new = []
    for a in runs:
        d = req("GET", f"/activity/{a.get('id')}") or a
        new.append(((d.get("start_date_local") or "")[:16], str(d.get("id")), format_run_org(d)))
    alle = sorted(existing + new, key=lambda x: x[0])
    with open(RUNLOG, "w") as f:
        f.write(LOG_HEADER + "\n".join(b for _, _, b in alle) + "\n")
    new_state = max([a.get("start_date_local", "") for a in runs] + ([state] if state else []))
    with open(STATE_FILE, "w") as f:
        f.write(new_state)
    print(f"Added {len(runs)} run(s); file sorted ({len(alle)} total). Marker: {new_state[:16]}.")


def pull_wellness():
    """Fetch the last WELLNESS_DAYS of Garmin wellness from intervals.icu (resting HR,
    HRV/rMSSD, sleep, steps + CTL/ATL) and (re)write WELLNESS_LOG as a generated org
    table, newest last. 7-day means for restingHR/HRV make the trend readable — the
    plan autoregulates off these (course.org, principle 5)."""
    newest = dt.date.today()
    oldest = newest - dt.timedelta(days=WELLNESS_DAYS - 1)
    rows = req("GET", f"/athlete/{ATHLETE}/wellness?oldest={oldest}&newest={newest}") or []
    rows.sort(key=lambda r: r.get("id") or "")
    if not rows:
        print("No wellness data returned.")
        return
    def num(r, k):
        v = r.get(k)
        return v if isinstance(v, (int, float)) else None
    def roll7(i, k):
        vals = [num(r, k) for r in rows[max(0, i - 6):i + 1]]
        vals = [v for v in vals if v is not None]
        return sum(vals) / len(vals) if vals else None
    out = ["#+title: Wellness log (pull intervals.icu)", "#+category: wellness", "",
           "# Generated by sync_plan_intervals.py (pull/wellness) - do NOT hand-edit.",
           "# rhr/hrv7d = 7-day rolling means. form = ctl - atl (negative = fatigued).",
           "",
           "| date | rhr | rhr7d | hrv | hrv7d | sleep_h | score | steps | ctl | atl | form |",
           "|------+-----+-------+-----+-------+---------+-------+-------+-----+-----+------|"]
    for i, r in enumerate(rows):
        sleep = num(r, "sleepSecs")
        ctl, atl = num(r, "ctl"), num(r, "atl")
        fmt = lambda v, p=0: ("" if v is None else f"{v:.{p}f}")
        out.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            r.get("id", ""), fmt(num(r, "restingHR")), fmt(roll7(i, "restingHR"), 1),
            fmt(num(r, "hrv")), fmt(roll7(i, "hrv"), 1),
            fmt(sleep / 3600 if sleep else None, 1), fmt(num(r, "sleepScore")),
            fmt(num(r, "steps")), fmt(ctl, 1), fmt(atl, 1),
            fmt(ctl - atl if ctl is not None and atl is not None else None, 1)))
    with open(WELLNESS_LOG, "w") as f:
        f.write("\n".join(out) + "\n")
    last = rows[-1]
    sl = num(last, "sleepSecs")
    print(f"Wellness: {len(rows)} day(s) -> {WELLNESS_LOG} | today: rhr {last.get('restingHR')} "
          f"hrv {last.get('hrv')} sleep {sl / 3600 if sl else 0:.1f}h")


def fix_strength_load():
    """intervals.icu loads strength by HR (HRSS) -> ~0 for low-HR lifting. Set a sensible
    load from RPE instead: load = (0.3 + 0.06*RPE)^2 * hours * 100 (RPE 3 ~7, RPE 7 ~16,
    matching the plan's ~15-25 for loaded HSR). RPE comes from the activity (logged on the
    watch / intervals) or INTERVALS_STRENGTH_RPE (default 3). WeightTraining only; idempotent;
    a manually-logged RPE wins over the default."""
    default_rpe = float(os.environ.get("INTERVALS_STRENGTH_RPE", "3"))
    since = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    q = urllib.parse.urlencode({"oldest": since, "newest": dt.date.today().isoformat()})
    fixed = 0
    for a in req("GET", f"/athlete/{ATHLETE}/activities?{q}") or []:
        if (a.get("type") or "") != "WeightTraining":
            continue
        rpe = a.get("icu_rpe") or default_rpe
        mins = (a.get("moving_time") or a.get("elapsed_time") or 0) / 60
        load = round((0.3 + 0.06 * rpe) ** 2 * (mins / 60) * 100)
        if load and a.get("icu_training_load") != load:
            body = {"icu_training_load": load}
            if not a.get("icu_rpe"):
                body["icu_rpe"] = default_rpe
            req("PUT", f"/activity/{a['id']}", body)
            print(f"strength load: {(a.get('start_date_local') or '')[:10]} "
                  f"RPE {rpe:g} -> load {load}")
            fixed += 1
    if fixed:
        print(f"{fixed} strength activity(ies) re-loaded from RPE.")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "dry"
    evs = build_events()
    if mode == "dry":
        for e in evs:
            print(e["start_date_local"][:10], "|", e["name"])
        note = f", shift={SHIFT}w from {SHIFT_FROM}" if SHIFT else ""
        print(f"\n{len(evs)} events (dry run). Athlete={ATHLETE}{note}")
        return
    if mode == "org":
        write_org(evs)
        return
    if not KEY:
        sys.exit("No API key: INTERVALS_API_KEY not set and Emacs auth-source empty "
                 "(~/.authinfo.gpg, machine api.intervals.icu).")
    if mode == "whoami":
        me = req("GET", "/athlete/0")
        print("Auth OK. athlete id =", (me or {}).get("id"), "| name =", (me or {}).get("name"))
        return
    resolve_athlete()
    print(f"Athlete resolved: {ATHLETE}")
    if mode == "latest":
        latest()
        return
    if mode == "pull":
        pull_runs()
        fix_strength_load()   # strength load from RPE (intervals' HR-load is ~0 for lifting)
        pull_wellness()       # refresh the wellness log (RHR/HRV/sleep -> autoregulation)
        write_org(evs)        # refresh the org agenda's DONE marks
        return
    if mode == "fixstrength":
        fix_strength_load()
        return
    if mode == "wellness":
        pull_wellness()
        return
    if mode in ("delete", "create"):
        delete_plan()
    if mode == "create":
        for e in evs:
            req("POST", f"/athlete/{ATHLETE}/events", e)
            print("created", e["start_date_local"][:10], e["name"])
        write_org(evs)  # keep the org agenda in sync with what was uploaded
        note = f", shift={SHIFT}w from {SHIFT_FROM}" if SHIFT else ""
        print(f"\nDone: {len(evs)} events created for {ATHLETE}{note}.")
    elif mode != "delete":
        sys.exit(f"Unknown mode '{mode}'. Use: dry | org | whoami | create | delete")


if __name__ == "__main__":
    main()
