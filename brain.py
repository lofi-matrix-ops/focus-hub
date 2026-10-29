import os, json, uuid, requests, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from google import genai
from supabase import create_client
from atproto import Client as BskyClient

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
ai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MatrixTelemetry/4.0"}

# 1. DETERMINE CURRENT LAWRENCE CST DAY & TIME WINDOW DYNAMICALLY
cst_now = datetime.now(timezone(timedelta(hours=-6)))
day_map = {0: "M", 1: "Tu", 2: "W", 3: "Th", 4: "F", 5: "Sa", 6: "Su"}
today_code = day_map[cst_now.weekday()]

# 2. QUERY SUPABASE ku_schedule_matrix FOR HIGHEST-PRESSURE COURSES MEETING TODAY
live_courses = {}
for pipe in ["p1_stem", "p2_bus", "p3_clas", "p4_fem_asmr", "p5_night"]:
    q = sb.table("ku_schedule_matrix").select("course_code,course_title,end_time,total_enrl,enroll_cap") \
          .eq("pipeline_track", pipe).ilike("meeting_days", f"%{today_code}%") \
          .order("pressure_score", desc=True).limit(5).execute()
    live_courses[pipe] = q.data if q.data else []

# 3. LIVE LAWRENCE WEATHER API (TRIGGERS BUS-WAIT / DORM ISOLATION HOOKS)
weather_desc = "Clear late night"
try:
    w = requests.get("https://api.open-meteo.com/v1/forecast?latitude=38.9717&longitude=-95.2353&current=temperature_2m,precipitation", timeout=8).json()
    temp_f = round(w["current"]["temperature_2m"] * 9/5 + 32)
    precip = w["current"]["precipitation"]
    weather_desc = f"{temp_f}F, {'Rain/Snow active' if precip > 0 else 'Dry'}"
except Exception:
    pass

# 4. LIVE KU + LAWRENCE SUBREDDITS & KANSAS GOOGLE TRENDS
campus_buzz, ks_trends = [], []
for sub in ["UniversityofKansas", "Lawrence"]:
    try:
        r = requests.get(f"https://www.reddit.com/r/{sub}/new.json?limit=6", headers=UA, timeout=8)
        campus_buzz += [p["data"].get("title","") for p in r.json().get("data",{}).get("children",[])]
    except Exception:
        pass

try:
    r = requests.get("https://trends.google.com/trending/rss?geo=US-KS", headers=UA, timeout=8)
    ks_trends = [i.text for i in ET.fromstring(r.text).findall(".//item/title")[:5]]
except Exception:
    pass

# 5. LIVE NSFW FETISH VELOCITY (REDDIT 18+ + GONEWILDAUDIO + REDGIFS + DANBOORU)
vis_nsfw, aud_nsfw, tag_velocity = [], [], []
try:
    r = requests.get("https://www.reddit.com/r/all/top.json?t=day&include_over_18=on&limit=25", headers=UA, timeout=8)
    vis_nsfw = [f"{p['data'].get('subreddit')}: {p['data'].get('title')}" for p in r.json().get("data",{}).get("children",[]) if p["data"].get("over_18")]
except Exception:
    pass

try:
    r = requests.get("https://www.reddit.com/r/GoneWildAudio/hot.json?limit=10", headers=UA, timeout=8)
    aud_nsfw = [p["data"].get("title","") for p in r.json().get("data",{}).get("children",[])]
except Exception:
    pass

try:
    r = requests.get("https://danbooru.donmai.us/tags.json?search[order]=count&limit=12", headers=UA, timeout=8)
    tag_velocity = [t.get("name","") for t in r.json() if isinstance(t, dict)]
except Exception:
    pass

# 6. GEMINI DYNAMIC SYNTHESIS ACROSS ALL 5 PIPELINES
prompt = f"""CST Timestamp: {cst_now.strftime('%A %I:%M %p')}. Local Weather: {weather_desc}.
Dynamic High-Pressure Courses Meeting Today by Pipeline: {json.dumps(live_courses)}
Live Campus/City Buzz: {campus_buzz[:8]}
Live Kansas Search Trends: {ks_trends}
Live Visual 18+ Velocity: {vis_nsfw[:8]}
Live Female Audio 18+ Velocity: {aud_nsfw[:6]}
Live Fetish Tag Taxonomy: {tag_velocity}

Generate 1 hyper-specific cortisol-to-dopamine hook and 1 trending 2-word 18+ search query for each of the 5 pipelines using today's live courses, weather, and fetish velocity above.
LEGAL RULE: NEVER output 'KU', 'Kansas', 'Lawrence', or 'Jayhawks'. Reference course numbers (e.g. CHEM 335, ME 212, BUS 150) or bus route numbers (Route 11, Route 30, Route 43) only.

Return ONLY valid JSON:
{{
  "p1_stem": {{"arch": "cosplay", "hook": "...", "query": "..."}},
  "p2_bus": {{"arch": "fit", "hook": "...", "query": "..."}},
  "p3_clas": {{"arch": "casual", "hook": "...", "query": "..."}},
  "p4_fem_asmr": {{"arch": "asmr", "hook": "...", "query": "..."}},
  "p5_night": {{"arch": "alt", "hook": "...", "query": "..."}}
}}"""

resp = ai.models.generate_content(model="gemini-2.5-flash", contents=prompt)
plan = json.loads(resp.text.strip().removeprefix("```json").removesuffix("```").strip())

for track_id, cfg in plan.items():
    res = sb.rpc("get_optimal_asset", {"req_track": track_id, "pref_arch": cfg["arch"]}).execute()
    if not res.data:
        res = sb.rpc("get_optimal_asset", {"req_track": None, "pref_arch": None}).execute()
    if not res.data:
        continue
    asset = res.data[0]
    q = cfg["query"].replace(" ", "+")
    payoff = f"https://www.reddit.com/r/GoneWildAudio/search/?q={q}&restrict_sr=1&include_over_18=on&sort=hot" if track_id == "p4_fem_asmr" else f"https://www.reddit.com/search/?q={q}+nsfw%3Ayes&include_over_18=on&sort=hot"

    sb.table("media_assets").update({
        "cortisol_hook": cfg["hook"],
        "fetish_tag": cfg["query"],
        "payoff_url": payoff,
        "last_posted_at": "now()"
    }).eq("id", asset["asset_id"]).execute()

    sb.table("deployment_logs").insert({
        "asset_id": asset["asset_id"],
        "pipeline_track": track_id,
        "archetype": asset["archetype"],
        "demographic": asset["demographic"],
        "intensity_tier": asset["intensity_tier"]
    }).execute()

print("Dynamic 5-Pipeline Sync Complete:", plan)
