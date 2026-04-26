"""
Understat scraper — version 2
Fetches player stats for all Big 5 leagues, multiple seasons.
Uses session cookies + better headers to bypass bot detection.
"""

import json
import re
import time
import urllib.request
import urllib.parse
import os
from html import unescape
import datetime

LEAGUES = {
    "EPL":        "Premier League",
    "La_liga":    "La Liga",
    "Bundesliga": "Bundesliga",
    "Serie_A":    "Serie A",
    "Ligue_1":    "Ligue 1",
}

SEASONS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]

def make_opener():
    opener = urllib.request.build_opener()
    opener.addheaders = [
        ('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'),
        ('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'),
        ('Accept-Language', 'en-US,en;q=0.9'),
        ('Connection', 'keep-alive'),
        ('Upgrade-Insecure-Requests', '1'),
    ]
    return opener

def fetch_html(url, opener):
    try:
        req = urllib.request.Request(url)
        with opener.open(req, timeout=30) as resp:
            raw = resp.read()
            encoding = resp.info().get('Content-Encoding', '')
            if encoding == 'gzip':
                import gzip
                raw = gzip.decompress(raw)
            return raw.decode('utf-8', errors='replace')
    except Exception as e:
        print(f"    [ERR] fetch {url}: {e}")
        return ""

def extract_json_var(html, var_name):
    pattern = rf"var\s+{var_name}\s*=\s*JSON\.parse\('(.+?)'\)"
    match = re.search(pattern, html, re.DOTALL)
    if match:
        raw = match.group(1)
        try:
            raw = raw.encode('utf-8').decode('unicode_escape')
        except Exception:
            pass
        raw = unescape(raw)
        try:
            return json.loads(raw)
        except Exception as e:
            print(f"    [ERR] JSON parse: {e}")
            return None
    return None

def fetch_league_players(league_key, season, opener):
    url = f"https://understat.com/league/{league_key}/{season}"
    print(f"    GET {url}")
    html = fetch_html(url, opener)

    if not html or len(html) < 1000:
        print(f"    [WARN] Empty response ({len(html)} chars)")
        return []

    data = extract_json_var(html, 'playersData')
    if data is None:
        print(f"    [WARN] playersData not found. HTML length: {len(html)}")
        return []

    print(f"    -> {len(data)} players")
    return data

def compute_per90(player, league_name, season):
    try:
        minutes = float(player.get('time', 0))
        if minutes < 90:
            return None
        per90 = minutes / 90.0
        def p90(val):
            try:
                return round(float(val) / per90, 3)
            except:
                return 0.0
        return {
            'id':      player.get('id', ''),
            'name':    player.get('player_name', 'Unknown'),
            'club':    player.get('team_title', ''),
            'league':  league_name,
            'season':  f"{season}/{str(season+1)[-2:]}",
            'pos':     player.get('position', '').upper() or '?',
            'games':   int(player.get('games', 0)),
            'minutes': int(minutes),
            'stats': {
                'Goals':     p90(player.get('goals', 0)),
                'Assists':   p90(player.get('assists', 0)),
                'xG':        p90(player.get('xG', 0)),
                'xA':        p90(player.get('xA', 0)),
                'Shots':     p90(player.get('shots', 0)),
                'KeyPasses': p90(player.get('key_passes', 0)),
                'npG':       p90(player.get('npg', 0)),
                'npxG':      p90(player.get('npxG', 0)),
                'xGChain':   p90(player.get('xGChain', 0)),
                'xGBuildup': p90(player.get('xGBuildup', 0)),
            }
        }
    except Exception as e:
        print(f"    [ERR] compute_per90: {e}")
        return None

def scrape_season(season, opener):
    all_players = []
    seen_ids = set()
    for league_key, league_name in LEAGUES.items():
        print(f"  [{league_name}] {season}/{str(season+1)[-2:]}")
        raw_players = fetch_league_players(league_key, season, opener)
        for rp in raw_players:
            pid = rp.get('id', '')
            p = compute_per90(rp, league_name, season)
            if p is None:
                continue
            if pid in seen_ids:
                existing = next((x for x in all_players if x['id'] == pid), None)
                if existing and p['minutes'] > existing['minutes']:
                    all_players.remove(existing)
                    all_players.append(p)
            else:
                seen_ids.add(pid)
                all_players.append(p)
        time.sleep(3)
    all_players.sort(key=lambda p: p['name'])
    return all_players

def main():
    os.makedirs('data', exist_ok=True)
    opener = make_opener()

    # Warm up session
    print("Warming up session...")
    fetch_html("https://understat.com/", opener)
    time.sleep(2)

    summary = {}
    for season in SEASONS:
        print(f"\n=== Season {season}/{str(season+1)[-2:]} ===")
        players = scrape_season(season, opener)
        print(f"  Total: {len(players)} players")
        with open(f"data/{season}.json", 'w', encoding='utf-8') as f:
            json.dump(players, f, ensure_ascii=False, separators=(',', ':'))
        summary[str(season)] = len(players)
        time.sleep(2)

    manifest = {
        'seasons': SEASONS,
        'leagues': list(LEAGUES.values()),
        'updated': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'counts': summary,
    }
    with open('data/manifest.json', 'w') as f:
        json.dump(manifest, f, indent=2)

    print("\nDone!")
    print("Counts:", summary)

if __name__ == '__main__':
    main()
