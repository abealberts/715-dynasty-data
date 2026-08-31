from __future__ import annotations

from common import fetch_json, load_config, write_json, DATA_DIR
import json

KEEP_FIELDS = [
    "player_id", "first_name", "last_name", "full_name", "position",
    "fantasy_positions", "team", "age", "years_exp", "status",
    "injury_status", "injury_body_part", "injury_notes", "depth_chart_position",
    "depth_chart_order", "number",
]

def main() -> None:
    config = load_config()
    merged = {}

    for position in config["positions"]:
        payload = fetch_json(
            f"/players/{config['sport']}?position={position}&active=true"
        )
        for player_id, player in payload.items():
            slim = {field: player.get(field) for field in KEEP_FIELDS}
            slim["player_id"] = str(player_id)
            merged[str(player_id)] = slim

    write_json("players_active.json", merged)

    rosters_path = DATA_DIR / "rosters.json"
    if rosters_path.exists():
        rosters = json.loads(rosters_path.read_text())
        rostered = {
            str(player_id)
            for roster in rosters
            for player_id in (roster.get("players") or [])
        }
        free_agents = {
            pid: pdata
            for pid, pdata in merged.items()
            if pid not in rostered
        }
        write_json("free_agents.json", free_agents)

if __name__ == "__main__":
    main()
