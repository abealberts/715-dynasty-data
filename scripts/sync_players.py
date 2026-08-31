from __future__ import annotations

import json

from common import DATA_DIR, fetch_json, load_config, write_json

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


def main() -> None:
    config = load_config()
    positions = set(config["positions"])
    sport = config["sport"]

    # Sleeper recommends fetching the full player map no more than once daily.
    payload = fetch_json(f"/players/{sport}")
    active = {}

    for player_id, player in payload.items():
        if player.get("active") is not True:
            continue
        fantasy_positions = set(player.get("fantasy_positions") or [])
        primary = player.get("position")
        if primary not in positions and not positions.intersection(fantasy_positions):
            continue

        slim = {field: player.get(field) for field in KEEP_FIELDS}
        slim["player_id"] = str(player_id)
        active[str(player_id)] = slim

    write_json("players_active.json", active)

    rosters_path = DATA_DIR / "rosters.json"
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
