from __future__ import annotations

from common import (
    fetch_json,
    load_config,
    normalize_league,
    normalize_rosters,
    normalize_users,
    build_roster_index,
    build_pick_ownership,
    recompute_free_agents,
    write_json,
)


def refresh_trending(sport: str) -> None:
    # Lightweight endpoint: refresh market heat every league-sync cycle.
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
    league_id = config["league_id"]
    sport = config["sport"]

    league_raw = fetch_json(f"/league/{league_id}")
    users_raw = fetch_json(f"/league/{league_id}/users")
    rosters_raw = fetch_json(f"/league/{league_id}/rosters")
    traded_picks = fetch_json(f"/league/{league_id}/traded_picks")
    nfl_state = fetch_json("/state/nfl")
    drafts_raw = fetch_json(f"/league/{league_id}/drafts")

    league = normalize_league(league_raw)
    users = normalize_users(users_raw)
    rosters = normalize_rosters(rosters_raw)

    write_json("league.json", league)
    write_json("users.json", users)
    write_json("rosters.json", rosters)
    write_json("traded_picks.json", traded_picks)
    write_json("nfl_state.json", nfl_state)
    write_json("roster_index.json", build_roster_index(users, rosters))
    write_json("pick_ownership.json", build_pick_ownership(league, traded_picks))

    drafts = []
    for draft in drafts_raw:
        draft_id = draft["draft_id"]
        normalized = {
            key: draft.get(key)
            for key in [
                "draft_id", "league_id", "season", "season_type", "sport",
                "status", "type", "start_time", "settings", "metadata",
                "draft_order", "slot_to_roster_id",
            ]
        }
        drafts.append(normalized)
        write_json(f"drafts/{draft_id}.json", normalized)
        write_json(f"drafts/{draft_id}_picks.json", fetch_json(f"/draft/{draft_id}/picks"))
        write_json(
            f"drafts/{draft_id}_traded_picks.json",
            fetch_json(f"/draft/{draft_id}/traded_picks"),
        )
    write_json("drafts.json", drafts)

    transactions = {}
    for week in config["transaction_weeks"]:
        try:
            payload = fetch_json(f"/league/{league_id}/transactions/{week}")
        except RuntimeError:
            payload = []
        transactions[str(week)] = payload
    write_json("transactions.json", transactions)

    matchups = {}
    for week in config["matchup_weeks"]:
        try:
            payload = fetch_json(f"/league/{league_id}/matchups/{week}")
        except RuntimeError:
            payload = []
        matchups[str(week)] = payload
    write_json("matchups.json", matchups)

    recompute_free_agents(rosters)
    refresh_trending(sport)


if __name__ == "__main__":
    main()
