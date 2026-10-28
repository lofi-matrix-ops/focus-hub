import os, json, uuid, requests, xml.etree.ElementTree as ET
from google import genai
from supabase import create_client
from atproto import Client as BskyClient, models

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
ai = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TrendBot/1.0"}

# 1. SCRAPE LIVE KU STUDENT STRESSORS (READ-ONLY PUBLIC JSON, NO API KEY NEEDED)
ku_posts = []
try:
    r = requests.get("https://www.reddit.com/r/UniversityofKansas/new.json?limit=8", headers=HEADERS, timeout=10)
    for post in r.json().get("data", {}).get("children", []):
        ku_posts.append(post["data"].get("title", ""))
except Exception:
    ku_posts = ["Midterm exam burnout and late night lab deadlines"]

# 2. SCRAPE LIVE KANSAS GOOGLE SEARCH TRENDS (RSS)
ks_trends = []
try:
    r = requests.get("https://trends.google.com/trending/rss?geo=US-KS", headers=HEADERS, timeout=10)
    root = ET.fromstring(r.text)
    for item in root.findall(".//item/title")[:5]:
        ks_trends.append(item.text)
except Exception:
    ks_trends = ["late night study"]

# 3. SCRAPE RISING NSFW & AESTHETIC TRENDS TO ADAPT ARCHETYPE SELECTION
nsfw_titles = []
try:
    r = requests.get("https://www.reddit.com/r/all/top.json?t=day&include_over_18=on&limit=25", headers=HEADERS, timeout=10)
    for post in r.json().get("data", {}).get("children", []):
        if post["data"].get("over_18"):
            nsfw_titles.append(post["data"].get("title", ""))
except Exception:
    pass

# 4. GEMINI AUTONOMOUS SYNTHESIS (CORTISOL PRIME + OPTIMAL ARCHETYPE)
prompt = f"""You are an autonomous behavioral conversion engine.
Live campus stress topics: {ku_posts}
Live Kansas search trends: {ks_trends}
Live 18+ rising trend titles: {nsfw_titles[:8]}

Tasks:
1. Pick which archetype ["fit", "alt", "casual", "goth", "tech"] best aligns with current rising trends.
2. Write a 1-sentence 'cortisol_hook' that mirrors the current campus stress/mood above to trigger acute relatability, then pivots to taking a 6-second sensory reset.
CRITICAL LEGAL RULE: NEVER mention KU, Kansas, Lawrence, Jayhawks, or any specific university name.
3. Provide a 2-word 'nsfw_search_query' matching the hottest current 18+ trend.

Return ONLY valid JSON:
{{"preferred_archetype": "...", "cortisol_hook": "...", "nsfw_search_query": "..."}}"""

resp = ai.models.generate_content(model="gemini-2.5-flash", contents=prompt)
synth = json.loads(resp.text.strip().removeprefix("```json").removesuffix("```").strip())

# 5. PULL OPTIMAL COOLIDGE-ROTATED ASSET FROM SUPABASE
res = sb.rpc("get_optimal_asset", {"preferred_arch": synth["preferred_archetype"]}).execute()
if not res.data:
    res = sb.rpc("get_optimal_asset", {"preferred_arch": None}).execute()
asset = res.data[0]

dynamic_payoff = f"https://www.reddit.com/search/?q={synth['nsfw_search_query'].replace(' ', '+')}+nsfw%3Ayes&include_over_18=on&sort=hot"

# 6. UPDATE PWA LIVE FEED & asset hook
sb.table("media_assets").update({
    "cortisol_hook": synth["cortisol_hook"],
    "payoff_url": dynamic_payoff,
    "last_posted_at": "now()"
}).eq("id", asset["asset_id"]).execute()

sb.table("live_feed").update({
    "asset_id": asset["asset_id"],
    "video_url": asset["video_url"],
    "archetype": asset["archetype"],
    "intensity_tier": asset["intensity_tier"],
    "cortisol_hook": synth["cortisol_hook"],
    "trending_nsfw_tag": synth["nsfw_search_query"],
    "payoff_url": dynamic_payoff,
    "updated_at": "now()"
}).eq("id", 1).execute()

sb.table("deployment_logs").insert({
    "asset_id": asset["asset_id"],
    "archetype": asset["archetype"],
    "demographic": asset["demographic"],
    "intensity_tier": asset["intensity_tier"]
}).execute()

# 7. AUTONOMOUS DISPATCH TO MATRIX ROOM
try:
    room_id = os.environ["MATRIX_ROOM_ID"]
    token = os.environ["MATRIX_ACCESS_TOKEN"]
    txn = str(uuid.uuid4())
    matrix_url = f"https://matrix-client.matrix.org/_matrix/client/v3/rooms/{room_id}/send/m.room.message/{txn}"
    msg_body = f"⚠️ {synth['cortisol_hook']}\n🎧 6s Loop: {asset['video_url']}\n🔥 18+ Vault: https://focus-vibe-check.vercel.app"
    requests.put(matrix_url, headers={"Authorization": f"Bearer {token}"}, json={"msgtype": "m.text", "body": msg_body}, timeout=10)
except Exception as e:
    print("Matrix skip:", e)

# 8. AUTONOMOUS DISPATCH TO BLUESKY (ATPROTO)
try:
    bsky = BskyClient()
    bsky.login(os.environ["BSKY_HANDLE"], os.environ["BSKY_APP_PASSWORD"])
    post_text = f"{synth['cortisol_hook']}\n\n6-sec binaural focus reset + 18+ archive 👇\nhttps://focus-vibe-check.vercel.app"
    bsky.send_post(text=post_text)
except Exception as e:
    print("Bluesky skip:", e)

print("Cycle complete:", synth)
