from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    ROOT,
    build_roster_index,
    fetch_json,
    load_config,
    normalize_league,
    normalize_rosters,
    normalize_users,
)

HISTORY = ROOT / "data" / "history"
MAX_SEASONS = 10


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def fetch_matchups(league_id: str) -> dict[str, Any]:
    matchups = {}
    for week in range(1, 19):
        try:
            matchups[str(week)] = fetch_json(f"/league/{league_id}/matchups/{week}")
        except RuntimeError:
            matchups[str(week)] = []
    return matchups


def fetch_transactions(league_id: str) -> dict[str, Any]:
    transactions = {}
    for week in range(1, 19):
        try:
            transactions[str(week)] = fetch_json(f"/league/{league_id}/transactions/{week}")
        except RuntimeError:
            transactions[str(week)] = []
    return transactions


def main() -> None:
    config = load_config()
    current = fetch_json(f"/league/{config['league_id']}")
    previous_id = current.get("previous_league_id")

    seasons = []
    seen = set()

    while previous_id and str(previous_id) != "0" and len(seasons) < MAX_SEASONS:
        league_id = str(previous_id)
        if league_id in seen:
            break
        seen.add(league_id)

        raw_league = fetch_json(f"/league/{league_id}")
        raw_users = fetch_json(f"/league/{league_id}/users")
        raw_rosters = fetch_json(f"/league/{league_id}/rosters")

        league = normalize_league(raw_league)
        users = normalize_users(raw_users)
        rosters = normalize_rosters(raw_rosters)
        roster_index = build_roster_index(users, rosters)
        matchups = fetch_matchups(league_id)
        transactions = fetch_transactions(league_id)

        season = str(league.get("season") or "unknown")
        folder_name = f"{season}_{league_id}"
        folder = HISTORY / folder_name

        write_json(folder / "league.json", league)
        write_json(folder / "users.json", users)
        write_json(folder / "rosters.json", rosters)
        write_json(folder / "roster_index.json", roster_index)
        write_json(folder / "matchups.json", matchups)
        write_json(folder / "transactions.json", transactions)

        seasons.append({
            "season": season,
            "league_id": league_id,
            "name": league.get("name"),
            "folder": folder_name,
            "previous_league_id": league.get("previous_league_id"),
        })

        previous_id = league.get("previous_league_id")

    write_json(HISTORY / "manifest.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_league_id": str(config["league_id"]),
        "seasons": seasons,
    })

    print(f"Imported {len(seasons)} previous league season(s).")


if __name__ == "__main__":
    main()
