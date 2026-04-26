"""
API-Football scraper v2 — fetches ALL pages per league.
"""

import json, os, datetime, time, urllib.request

API_KEY = os.environ.get("API_FOOTBALL_KEY", "")
BASE = "https://v3.football.api-sports.io"

LEAGUES = {
    39:  "Premier League",
    140: "La Liga",
    78:  "Bundesliga",
    135: "Serie A",
    61:  "Ligue 1",
}

CURRENT_SEASON = 2024

def api_get(endpoint, params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}{endpoint}?{qs}"
    req = urllib.request.Request(url, headers={
        "x-apisports-key": API_KEY,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
            # Print remaining requests for debug
            remaining = r.headers.get("x-ratelimit-requests-remaining", "?")
            print(f"    API requests remaining: {remaining}")
            return data
    except Exception as e:
        print(f"    [ERR] {e}")
        return None

def fetch_all_players(league_id, season):
    all_players = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        print(f"    Page {page}/{total_pages}...")
        data = api_get("/players", {
            "league": league_id,
            "season": season,
            "page": page
        })
        if not data:
            break

        paging = data.get("paging", {})
        total_pages = int(paging.get("total", 1))
        results = data.get("response", [])
        
        if not results:
            break
            
        all_players.extend(results)
        print(f"    Got {len(results)} players (total so far: {len(all_players)})")
        
        page += 1
        if page <= total_pages:
            time.sleep(1.5)  # respect rate limit

    return all_players

def process(raw, league_name, season):
    try:
        info  = raw.get("player", {})
        stats = raw.get("statistics", [{}])[0]
        games_d    = stats.get("games", {})
        goals_d    = stats.get("goals", {})
        passes_d   = stats.get("passes", {})
        shots_d    = stats.get("shots", {})
        dribbles_d = stats.get("dribbles", {})
        tackles_d  = stats.get("tackles", {})

        mins = float(games_d.get("minutes") or 0)
        if mins < 90:
            return None

        p = mins / 90

        def v(d, key):
            try: return round(float(d.get(key) or 0) / p, 3)
            except: return 0.0

        return {
            "id":      str(info.get("id", "")),
            "name":    info.get("name", ""),
            "club":    stats.get("team", {}).get("name", ""),
            "league":  league_name,
            "season":  f"{season}/{str(season+1)[-2:]}",
            "pos":     (games_d.get("position") or "?")[:2].upper(),
            "games":   int(games_d.get("appearences") or 0),
            "minutes": int(mins),
            "stats": {
                "Goals":     v(goals_d,    "total"),
                "Assists":   round(float(goals_d.get("assists") or 0) / p, 3),
                "xG":        0.0,
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
        print(f"    [ERR] process: {e}")
        return None

def main():
    if not API_KEY:
        print("ERROR: API_FOOTBALL_KEY not set")
        exit(1)

    os.makedirs("data", exist_ok=True)
    players, seen = [], set()

    print(f"\n=== Season {CURRENT_SEASON}/{str(CURRENT_SEASON+1)[-2:]} ===")

    for league_id, league_name in LEAGUES.items():
        print(f"\n  [{league_name}]")
        raw_list = fetch_all_players(league_id, CURRENT_SEASON)
        print(f"  Total raw: {len(raw_list)}")

        for raw in raw_list:
            pid = str(raw.get("player", {}).get("id", ""))
            p = process(raw, league_name, CURRENT_SEASON)
            if not p:
                continue
            if pid in seen:
                ex = next((x for x in players if x["id"] == pid), None)
                if ex and p["minutes"] > ex["minutes"]:
                    players.remove(ex)
                    players.append(p)
            else:
                seen.add(pid)
                players.append(p)

        time.sleep(2)

    players.sort(key=lambda x: x["name"])
    print(f"\nTotal players: {len(players)}")

    for yr in [2024, 2025]:
        with open(f"data/{yr}.json", "w") as f:
            json.dump(players, f, ensure_ascii=False, separators=(",", ":"))

    manifest = {
        "seasons": [2024, 2025],
        "leagues": list(LEAGUES.values()),
        "updated": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "counts": {"2024": len(players), "2025": len(players)},
        "source": "api-football.com",
    }
    with open("data/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print("Done!")
    if len(players) == 0:
        exit(1)

if __name__ == "__main__":
    main()
