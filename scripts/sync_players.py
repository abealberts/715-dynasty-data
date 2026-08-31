from __future__ import annotations

import json
from pathlib import Path

from common import DATA_DIR, ROOT, fetch_json, load_config, write_json

KEEP_FIELDS = [
    "player_id", "first_name", "last_name", "full_name", "position",
    "fantasy_positions", "team", "age", "years_exp", "status",
    "injury_status", "injury_body_part", "injury_notes", "depth_chart_position",
    "depth_chart_order", "number",
]


def refresh_trending(sport: str) -> None:
    write_json(
        "trending_adds.json",
        fetch_json(f"/players/{sport}/trending/add?lookback_hours=24&limit=100"),
    )
    write_json(
        "trending_drops.json",
        fetch_json(f"/players/{sport}/trending/drop?lookback_hours=24&limit=100"),
    )


def historical_player_ids() -> set[str]:
    ids: set[str] = set()
    history = ROOT / "data" / "history"
    if not history.exists():
        return ids

    for path in history.glob("*/matchups.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for rows in payload.values():
            for row in rows or []:
                ids.update(str(x) for x in (row.get("players") or []) if str(x) != "0")
                ids.update(str(x) for x in (row.get("players_points") or {}).keys() if str(x) != "0")

    for path in history.glob("*/roster_index.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for roster in payload.values():
            ids.update(str(x) for x in (roster.get("players") or []) if str(x) != "0")

    return ids


def slim_player(player_id: str, player: dict) -> dict:
    slim = {field: player.get(field) for field in KEEP_FIELDS}
    slim["player_id"] = str(player_id)
    return slim


def main() -> None:
    config = load_config()
    positions = set(config["positions"])
    sport = config["sport"]

    # Sleeper recommends fetching the full player map no more than once daily.
    # We use that one fetch for both the active-player index and lightweight
    # metadata needed to reconstruct historical lineup legality.
    payload = fetch_json(f"/players/{sport}")
    active = {}
    history_ids = historical_player_ids()
    known_ids = set(history_ids)

    rosters_path = DATA_DIR / "rosters.json"
    if rosters_path.exists():
        rosters = json.loads(rosters_path.read_text(encoding="utf-8"))
        for roster in rosters:
            known_ids.update(str(x) for x in (roster.get("players") or []) if str(x) != "0")

    for player_id, player in payload.items():
        fantasy_positions = set(player.get("fantasy_positions") or [])
        primary = player.get("position")
        fantasy_relevant = primary in positions or bool(positions.intersection(fantasy_positions))

        if player.get("active") is True and fantasy_relevant:
            active[str(player_id)] = slim_player(str(player_id), player)
            known_ids.add(str(player_id))

    known = {}
    for player_id in known_ids:
        player = payload.get(str(player_id))
        if player is not None:
            known[str(player_id)] = slim_player(str(player_id), player)

    write_json("players_active.json", active)
    write_json("players_known.json", known)

    if rosters_path.exists():
        rosters = json.loads(rosters_path.read_text(encoding="utf-8"))
        rostered = {
            str(player_id)
            for roster in rosters
            for player_id in (roster.get("players") or [])
        }
        free_agents = {
            pid: pdata
            for pid, pdata in active.items()
            if pid not in rostered
        }
        write_json("free_agents.json", free_agents)

    refresh_trending(sport)


if __name__ == "__main__":
    main()
