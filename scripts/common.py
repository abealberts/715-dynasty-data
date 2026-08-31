from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://api.sleeper.app/v1"
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "current"

def load_config() -> dict[str, Any]:
    return json.loads((ROOT / "config.json").read_text())

def fetch_json(path_or_url: str, attempts: int = 3) -> Any:
    url = path_or_url if path_or_url.startswith("http") else f"{BASE}{path_or_url}"
    last_error = None
    for attempt in range(attempts):
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": "715-dynasty-sleeper-sync/1.0",
                    "Accept": "application/json",
                },
            )
            with urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")

def write_json(relative_path: str, value: Any) -> None:
    path = DATA_DIR / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)

def normalize_league(league: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "league_id", "name", "status", "season", "season_type", "sport",
        "draft_id", "previous_league_id", "total_rosters", "roster_positions",
        "settings", "scoring_settings", "metadata",
    ]
    return {k: league.get(k) for k in keys}

def normalize_users(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for user in users:
        metadata = user.get("metadata") or {}
        result.append({
            "user_id": user.get("user_id"),
            "display_name": user.get("display_name"),
            "team_name": metadata.get("team_name"),
            "avatar": user.get("avatar"),
            "is_owner": user.get("is_owner"),
        })
    return sorted(result, key=lambda x: str(x.get("display_name") or "").lower())

def normalize_rosters(rosters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for roster in rosters:
        result.append({
            "roster_id": roster.get("roster_id"),
            "owner_id": roster.get("owner_id"),
            "co_owners": roster.get("co_owners"),
            "players": roster.get("players") or [],
            "starters": roster.get("starters") or [],
            "reserve": roster.get("reserve") or [],
            "taxi": roster.get("taxi") or [],
            "settings": roster.get("settings") or {},
        })
    return sorted(result, key=lambda x: int(x["roster_id"]))

def build_roster_index(
    users: list[dict[str, Any]],
    rosters: list[dict[str, Any]],
) -> dict[str, Any]:
    users_by_id = {u["user_id"]: u for u in users}
    index = {}
    for roster in rosters:
        user = users_by_id.get(roster.get("owner_id"), {})
        rid = str(roster["roster_id"])
        index[rid] = {
            "roster_id": roster["roster_id"],
            "owner_id": roster.get("owner_id"),
            "display_name": user.get("display_name"),
            "team_name": user.get("team_name"),
            "players": roster.get("players") or [],
            "starters": roster.get("starters") or [],
            "settings": roster.get("settings") or {},
        }
    return index

def build_pick_ownership(
    league: dict[str, Any],
    traded_picks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    season = int(league["season"])
    rounds = int((league.get("settings") or {}).get("draft_rounds", 5))
    roster_count = int(league.get("total_rosters") or 0)

    traded_lookup = {}
    max_traded_season = season + 3
    for pick in traded_picks:
        pick_season = int(pick["season"])
        max_traded_season = max(max_traded_season, pick_season)
        traded_lookup[(pick_season, int(pick["round"]), int(pick["roster_id"]))] = int(pick["owner_id"])

    result = []
    for yr in range(season, max_traded_season + 1):
        for original_roster_id in range(1, roster_count + 1):
            for rnd in range(1, rounds + 1):
                owner = traded_lookup.get((yr, rnd, original_roster_id), original_roster_id)
                result.append({
                    "season": str(yr),
                    "round": rnd,
                    "original_roster_id": original_roster_id,
                    "owner_roster_id": owner,
                    "traded": owner != original_roster_id,
                })
    return result

def recompute_free_agents(rosters: list[dict[str, Any]]) -> None:
    players_path = DATA_DIR / "players_active.json"
    if not players_path.exists():
        return

    active_players = json.loads(players_path.read_text())
    rostered = {
        str(player_id)
        for roster in rosters
        for player_id in (roster.get("players") or [])
    }
    free_agents = {
        pid: pdata
        for pid, pdata in active_players.items()
        if str(pid) not in rostered
    }
    write_json("free_agents.json", free_agents)
