"""
Understat scraper — fetches player stats for all Big 5 leagues, multiple seasons.
Outputs one JSON file per season: data/YEAR.json
Each file contains all players across all 5 leagues with per-90 stats computed.
"""

import json
import re
import time
import urllib.request
import urllib.parse
import os
from html import unescape

LEAGUES = {
    "EPL":        "Premier League",
    "La_liga":    "La Liga",
    "Bundesliga": "Bundesliga",
    "Serie_A":    "Serie A",
    "Ligue_1":    "Ligue 1",
}

# Seasons: start year of each season (e.g. 2025 = 2025/26)
SEASONS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def fetch_league_players(league_key: str, season: int) -> list[dict]:
    """Scrape player data table from understat.com league page."""
    url = f"https://understat.com/league/{league_key}/{season}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8")
    except Exception as e:
        print(f"  [ERR] {league_key} {season}: {e}")
        return []

    # Understat embeds data as JSON inside <script> tags
    # Pattern: var playersData = JSON.parse('...')
    match = re.search(r"var\s+playersData\s*=\s*JSON\.parse\('(.+?)'\)", html)
    if not match:
        print(f"  [WARN] No playersData found for {league_key} {season}")
        return []

    raw = match.group(1)
    # Unescape JS unicode escapes then parse JSON
    raw = raw.encode("utf-8").decode("unicode_escape")
    raw = unescape(raw)
    try:
        players = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [ERR] JSON decode {league_key} {season}: {e}")
        return []

    return players


def compute_per90(player: dict, league_name: str, season: int) -> dict | None:
    """Convert raw cumulative stats to per-90 values."""
    try:
        minutes = float(player.get("time", 0))
        if minutes < 90:  # Skip players with less than 1 full game
            return None

        per90 = minutes / 90.0

        def p90(val):
            try:
                return round(float(val) / per90, 3)
            except (TypeError, ValueError, ZeroDivisionError):
                return 0.0

        goals = p90(player.get("goals", 0))
        assists = p90(player.get("assists", 0))
        xg = p90(player.get("xG", 0))
        xa = p90(player.get("xA", 0))
        shots = p90(player.get("shots", 0))
        key_passes = p90(player.get("key_passes", 0))
        npg = p90(player.get("npg", 0))
        npxg = p90(player.get("npxG", 0))
        xg_chain = p90(player.get("xGChain", 0))
        xg_buildup = p90(player.get("xGBuildup", 0))

        # Games played (for display context)
        games = int(player.get("games", 0))
        minutes_total = int(minutes)

        return {
            "id":          player.get("id", ""),
            "name":        player.get("player_name", "Unknown"),
            "club":        player.get("team_title", ""),
            "league":      league_name,
            "season":      f"{season}/{str(season+1)[-2:]}",
            "pos":         player.get("position", "").upper() or "?",
            "games":       games,
            "minutes":     minutes_total,
            "stats": {
                "Goals":       goals,
                "Assists":     assists,
                "xG":          xg,
                "xA":          xa,
                "Shots":       shots,
                "KeyPasses":   key_passes,
                "npG":         npg,
                "npxG":        npxg,
                "xGChain":     xg_chain,
                "xGBuildup":   xg_buildup,
            }
        }
    except Exception as e:
        print(f"  [ERR] compute_per90 for {player.get('player_name')}: {e}")
        return None


def scrape_season(season: int) -> list[dict]:
    """Scrape all 5 leagues for a given season year."""
    all_players = []
    seen_ids = set()  # A player can appear in multiple leagues (transfers)

    for league_key, league_name in LEAGUES.items():
        print(f"  Fetching {league_name} {season}/{str(season+1)[-2:]}...")
        raw_players = fetch_league_players(league_key, season)
        print(f"    → {len(raw_players)} raw players found")

        for rp in raw_players:
            pid = rp.get("id", "")
            # If a player appears twice (transfer mid-season), keep the one
            # with more minutes — Understat already aggregates per league page
            processed = compute_per90(rp, league_name, season)
            if processed is None:
                continue
            if pid in seen_ids:
                # Keep the one with more minutes
                existing = next((p for p in all_players if p["id"] == pid), None)
                if existing and processed["minutes"] > existing["minutes"]:
                    all_players.remove(existing)
                    all_players.append(processed)
            else:
                seen_ids.add(pid)
                all_players.append(processed)

        # Be polite — don't hammer Understat
        time.sleep(2)

    # Sort by name
    all_players.sort(key=lambda p: p["name"])
    return all_players


def main():
    os.makedirs("data", exist_ok=True)
    summary = {}

    for season in SEASONS:
        print(f"\n=== Season {season}/{str(season+1)[-2:]} ===")
        players = scrape_season(season)
        print(f"  Total: {len(players)} players")

        out_path = f"data/{season}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(players, f, ensure_ascii=False, separators=(",", ":"))
        print(f"  Written → {out_path}")

        summary[str(season)] = len(players)

    # Write a manifest file so the app knows which seasons exist
    manifest = {
        "seasons": SEASONS,
        "leagues": list(LEAGUES.values()),
        "updated": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "counts": summary,
    }
    with open("data/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print("\n✓ manifest.json written")
    print("\nDone!")


if __name__ == "__main__":
    main()
