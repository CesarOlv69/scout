"""
API-Football scraper — fetches Big 5 player stats via api-football.com
Free tier: 100 requests/day
Runs nightly via GitHub Actions
"""

import json, os, datetime, time, urllib.request, urllib.error

API_KEY = os.environ.get("API_FOOTBALL_KEY", "")
BASE = "https://v3.football.api-sports.io"

LEAGUES = {
    39:  "Premier League",
    140: "La Liga",
    78:  "Bundesliga",
    135: "Serie A",
    61:  "Ligue 1",
}

# Only scrape current season to stay within 100 req/day limit
# 5 leagues × 1 season = 5-20 requests (paginated)
CURRENT_SEASON = 2024  # 2024/25

def api_get(endpoint, params):
    url = f"{BASE}{endpoint}?" + "&".join(f"{k}={v}" for k,v in params.items())
    req = urllib.request.Request(url, headers={
        "x-apisports-key": API_KEY,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  [ERR] {url}: {e}")
        return None

def fetch_players(league_id, season):
    all_players = []
    page = 1
    while True:
        print(f"  Page {page}...")
        data = api_get("/players", {"league": league_id, "season": season, "page": page})
        if not data:
            break
        results = data.get("response", [])
        if not results:
            break
        all_players.extend(results)
        paging = data.get("paging", {})
        if page >= paging.get("total", 1):
            break
        page += 1
        time.sleep(1)
    return all_players

def process_player(raw, league_name, season):
    try:
        info = raw.get("player", {})
        stats = raw.get("statistics", [{}])[0]

        games = stats.get("games", {})
        mins = float(games.get("minutes") or 0)
        if mins < 90:
            return None

        p = mins / 90

        def v(d, *keys):
            val = d
            for k in keys:
                val = (val or {}).get(k)
            try:
                return round(float(val or 0) / p, 3)
            except:
                return 0.0

        goals_d   = stats.get("goals", {})
        passes_d  = stats.get("passes", {})
        dribbles_d= stats.get("dribbles", {})
        tackles_d = stats.get("tackles", {})
        shots_d   = stats.get("shots", {})

        return {
            "id":      str(info.get("id", "")),
            "name":    info.get("name", ""),
            "club":    stats.get("team", {}).get("name", ""),
            "league":  league_name,
            "season":  f"{season}/{str(season+1)[-2:]}",
            "pos":     (games.get("position") or "?")[:2].upper(),
            "games":   int(games.get("appearences") or 0),
            "minutes": int(mins),
            "stats": {
                "Goals":     v(goals_d,   "total") if goals_d else 0.0,
                "Assists":   round(float(goals_d.get("assists") or 0) / p, 3),
                "xG":        0.0,  # not on free tier
                "xA":        0.0,
                "Shots":     v(shots_d,    "total"),
                "KeyPasses": v(passes_d,   "key"),
                "Dribbles":  v(dribbles_d, "success"),
                "Tackles":   v(tackles_d,  "total"),
                "PassAcc":   float(passes_d.get("accuracy") or 0),
                "npxG":      0.0,
                "xGChain":   0.0,
            }
        }
    except Exception as e:
        print(f"  [ERR] process: {e}")
        return None

def main():
    if not API_KEY:
        print("ERROR: API_FOOTBALL_KEY not set")
        exit(1)

    os.makedirs("data", exist_ok=True)

    # Load existing data to preserve historical seasons
    all_seasons_data = {}
    for yr in [2019,2020,2021,2022,2023,2024,2025]:
        path = f"data/{yr}.json"
        if os.path.exists(path):
            with open(path) as f:
                all_seasons_data[yr] = json.load(f)

    # Scrape current season
    print(f"\n=== Season {CURRENT_SEASON}/{str(CURRENT_SEASON+1)[-2:]} ===")
    players, seen = [], set()

    for league_id, league_name in LEAGUES.items():
        print(f"  [{league_name}]")
        raw_list = fetch_players(league_id, CURRENT_SEASON)
        print(f"  -> {len(raw_list)} raw players")
        for raw in raw_list:
            pid = str(raw.get("player", {}).get("id", ""))
            p = process_player(raw, league_name, CURRENT_SEASON)
            if not p:
                continue
            if pid in seen:
                ex = next((x for x in players if x["id"] == pid), None)
                if ex and p["minutes"] > ex["minutes"]:
                    players.remove(ex); players.append(p)
            else:
                seen.add(pid); players.append(p)
        time.sleep(2)

    players.sort(key=lambda x: x["name"])
    
    # Save as both 2024 and 2025 (same season)
    for yr in [2024, 2025]:
        with open(f"data/{yr}.json", "w") as f:
            json.dump(players, f, ensure_ascii=False, separators=(",",":"))
    
    all_seasons_data[2024] = players
    all_seasons_data[2025] = players

    # Count all seasons
    counts = {str(yr): len(all_seasons_data.get(yr, [])) for yr in [2019,2020,2021,2022,2023,2024,2025]}

    manifest = {
        "seasons": [2024, 2025],  # only current season available via API free tier
        "leagues": list(LEAGUES.values()),
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "counts": counts,
        "source": "api-football.com",
    }
    with open("data/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone! {len(players)} players saved.")
    if len(players) == 0:
        exit(1)

if __name__ == "__main__":
    main()
