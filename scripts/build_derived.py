from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data" / "current"
DERIVED = ROOT / "data" / "derived"
POSITIONS = ("QB", "RB", "WR", "TE")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(name: str, value: Any) -> None:
    DERIVED.mkdir(parents=True, exist_ok=True)
    path = DERIVED / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def player_view(player_id: str, players: dict[str, Any]) -> dict[str, Any]:
    p = players.get(str(player_id), {}) or {}
    name = p.get("full_name") or " ".join(
        x for x in [p.get("first_name"), p.get("last_name")] if x
    ) or f"Sleeper {player_id}"
    return {
        "player_id": str(player_id),
        "name": name,
        "position": p.get("position"),
        "fantasy_positions": p.get("fantasy_positions") or [],
        "team": p.get("team"),
        "age": p.get("age"),
        "years_exp": p.get("years_exp"),
        "status": p.get("status"),
        "injury_status": p.get("injury_status"),
        "injury_body_part": p.get("injury_body_part"),
        "injury_notes": p.get("injury_notes"),
        "depth_chart_position": p.get("depth_chart_position"),
        "depth_chart_order": p.get("depth_chart_order"),
    }


def free_agent_sort_key(p: dict[str, Any]) -> tuple:
    # This is a browse order, not a dynasty ranking.
    team_penalty = 0 if p.get("team") else 1
    depth = p.get("depth_chart_order")
    depth = depth if isinstance(depth, (int, float)) else 99
    age = p.get("age")
    age = age if isinstance(age, (int, float)) else 99
    return (team_penalty, depth, age, p.get("name") or "")


def flatten_transactions(
    transactions: dict[str, Any],
    players: dict[str, Any],
    rosters: dict[str, Any],
) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for week, items in (transactions or {}).items():
        for tx in items or []:
            adds = []
            for pid, rid in (tx.get("adds") or {}).items():
                adds.append({
                    "player": player_view(str(pid), players),
                    "roster_id": rid,
                    "manager": (rosters.get(str(rid)) or {}).get("display_name"),
                })
            drops = []
            for pid, rid in (tx.get("drops") or {}).items():
                drops.append({
                    "player": player_view(str(pid), players),
                    "roster_id": rid,
                    "manager": (rosters.get(str(rid)) or {}).get("display_name"),
                })
            flattened.append({
                "transaction_id": tx.get("transaction_id"),
                "type": tx.get("type"),
                "status": tx.get("status"),
                "created": tx.get("created"),
                "week": int(week) if str(week).isdigit() else week,
                "roster_ids": tx.get("roster_ids") or [],
                "adds": adds,
                "drops": drops,
                "draft_picks": tx.get("draft_picks") or [],
                "waiver_budget": (tx.get("settings") or {}).get("waiver_bid"),
            })
    return sorted(flattened, key=lambda x: x.get("created") or 0, reverse=True)


def make_snapshot(
    rosters: dict[str, Any],
    picks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "rosters": {
            str(rid): {
                "players": sorted(str(x) for x in (r.get("players") or [])),
                "starters": [str(x) for x in (r.get("starters") or [])],
            }
            for rid, r in rosters.items()
        },
        "picks": {
            f"{p['season']}-{p['round']}-{p['original_roster_id']}": p["owner_roster_id"]
            for p in picks
        },
    }


def build_changes(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
    players: dict[str, Any],
    rosters: dict[str, Any],
) -> list[dict[str, Any]]:
    if not previous:
        return []

    now = datetime.now(timezone.utc).isoformat()
    changes: list[dict[str, Any]] = []
    prev_rosters = previous.get("rosters") or {}
    cur_rosters = current.get("rosters") or {}

    for rid in sorted(set(prev_rosters) | set(cur_rosters), key=lambda x: int(x)):
        manager = (rosters.get(str(rid)) or {}).get("display_name")
        old_players = set((prev_rosters.get(rid) or {}).get("players") or [])
        new_players = set((cur_rosters.get(rid) or {}).get("players") or [])
        for pid in sorted(new_players - old_players):
            changes.append({
                "detected_at": now,
                "type": "roster_add",
                "roster_id": int(rid),
                "manager": manager,
                "player": player_view(pid, players),
            })
        for pid in sorted(old_players - new_players):
            changes.append({
                "detected_at": now,
                "type": "roster_drop",
                "roster_id": int(rid),
                "manager": manager,
                "player": player_view(pid, players),
            })

        old_starters = (prev_rosters.get(rid) or {}).get("starters") or []
        new_starters = (cur_rosters.get(rid) or {}).get("starters") or []
        if old_starters != new_starters:
            changes.append({
                "detected_at": now,
                "type": "starter_change",
                "roster_id": int(rid),
                "manager": manager,
                "old_starters": old_starters,
                "new_starters": new_starters,
            })

    prev_picks = previous.get("picks") or {}
    cur_picks = current.get("picks") or {}
    for key in sorted(set(prev_picks) | set(cur_picks)):
        old_owner = prev_picks.get(key)
        new_owner = cur_picks.get(key)
        if old_owner == new_owner:
            continue
        season, rnd, original = key.split("-")
        changes.append({
            "detected_at": now,
            "type": "pick_owner_change",
            "season": season,
            "round": int(rnd),
            "original_roster_id": int(original),
            "old_owner_roster_id": old_owner,
            "new_owner_roster_id": new_owner,
            "old_owner_manager": (rosters.get(str(old_owner)) or {}).get("display_name") if old_owner else None,
            "new_owner_manager": (rosters.get(str(new_owner)) or {}).get("display_name") if new_owner else None,
        })
    return changes


def main() -> None:
    league = read_json(CURRENT / "league.json", {}) or {}
    rosters = read_json(CURRENT / "roster_index.json", {}) or {}
    picks = read_json(CURRENT / "pick_ownership.json", []) or []
    players = read_json(CURRENT / "players_active.json", {}) or {}
    free_agents = read_json(CURRENT / "free_agents.json", {}) or {}
    transactions = read_json(CURRENT / "transactions.json", {}) or {}

    if not league or not rosters:
        raise RuntimeError("league.json and roster_index.json are required before building derived data")

    waiver_budget = int((league.get("settings") or {}).get("waiver_budget", 100))
    roster_names = {
        str(rid): (r.get("display_name") or r.get("team_name") or f"Roster {rid}")
        for rid, r in rosters.items()
    }

    ownership: dict[str, Any] = {}
    team_assets: dict[str, Any] = {}

    picks_by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pick in picks:
        owner = str(pick.get("owner_roster_id"))
        original = str(pick.get("original_roster_id"))
        picks_by_owner[owner].append({
            **pick,
            "original_manager": roster_names.get(original),
        })

    for rid, roster in rosters.items():
        rid = str(rid)
        player_ids = [str(x) for x in (roster.get("players") or [])]
        starter_ids = [str(x) for x in (roster.get("starters") or []) if str(x) != "0"]
        starter_set = set(starter_ids)

        player_rows = []
        position_counts = defaultdict(int)
        for pid in player_ids:
            p = player_view(pid, players)
            p["starter"] = pid in starter_set
            player_rows.append(p)
            if p.get("position"):
                position_counts[p["position"]] += 1
            ownership[pid] = {
                "roster_id": int(rid),
                "manager": roster.get("display_name"),
                "team_name": roster.get("team_name"),
                "player": p,
            }

        player_rows.sort(key=lambda p: (
            POSITIONS.index(p["position"]) if p.get("position") in POSITIONS else 99,
            0 if p.get("starter") else 1,
            p.get("name") or "",
        ))

        settings = roster.get("settings") or {}
        budget_used = settings.get("waiver_budget_used") or 0
        team_picks = sorted(
            picks_by_owner.get(rid, []),
            key=lambda p: (int(p["season"]), int(p["round"]), int(p["original_roster_id"])),
        )

        team_assets[rid] = {
            "roster_id": int(rid),
            "manager": roster.get("display_name"),
            "team_name": roster.get("team_name"),
            "record": {
                "wins": settings.get("wins", 0),
                "losses": settings.get("losses", 0),
                "ties": settings.get("ties", 0),
                "fpts": settings.get("fpts", 0),
                "fpts_decimal": settings.get("fpts_decimal", 0),
            },
            "waivers": {
                "faab_budget": waiver_budget,
                "faab_used": budget_used,
                "faab_remaining": waiver_budget - budget_used,
                "waiver_position": settings.get("waiver_position"),
            },
            "position_counts": dict(position_counts),
            "players": player_rows,
            "starters": [player_view(pid, players) for pid in starter_ids],
            "bench": [p for p in player_rows if not p.get("starter")],
            "picks": team_picks,
        }

    free_by_pos: dict[str, list[dict[str, Any]]] = {p: [] for p in POSITIONS}
    for pid, raw in free_agents.items():
        p = player_view(str(pid), players)
        # Fallback to metadata already present in free_agents if players_active is absent/stale.
        if p["name"].startswith("Sleeper ") and raw:
            p = player_view(str(pid), {str(pid): raw})
        pos = p.get("position")
        if pos in free_by_pos:
            free_by_pos[pos].append(p)
    for pos in free_by_pos:
        free_by_pos[pos].sort(key=free_agent_sort_key)

    recent_transactions = flatten_transactions(transactions, players, rosters)

    roster_positions = league.get("roster_positions") or []
    starter_slots = [x for x in roster_positions if x != "BN"]
    league_summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "league_id": league.get("league_id"),
        "name": league.get("name"),
        "season": league.get("season"),
        "status": league.get("status"),
        "teams": league.get("total_rosters"),
        "starter_slots": starter_slots,
        "bench_slots": sum(1 for x in roster_positions if x == "BN"),
        "superflex": "SUPER_FLEX" in starter_slots,
        "full_ppr": (league.get("scoring_settings") or {}).get("rec") == 1.0,
        "league_median_match": bool((league.get("settings") or {}).get("league_average_match")),
        "draft_rounds": (league.get("settings") or {}).get("draft_rounds"),
        "faab_budget": waiver_budget,
        "team_summaries": [
            {
                "roster_id": t["roster_id"],
                "manager": t["manager"],
                "team_name": t["team_name"],
                "record": t["record"],
                "faab_remaining": t["waivers"]["faab_remaining"],
                "position_counts": t["position_counts"],
                "pick_count": len(t["picks"]),
            }
            for t in team_assets.values()
        ],
    }

    current_snapshot = make_snapshot(rosters, picks)
    previous_snapshot = read_json(DERIVED / "snapshot_state.json", None)
    latest_changes = build_changes(previous_snapshot, current_snapshot, players, rosters)
    existing_log = read_json(DERIVED / "change_log.json", []) or []
    if latest_changes:
        existing_log.extend(latest_changes)
    change_log = existing_log[-500:]

    write_json("league_summary.json", league_summary)
    write_json("team_assets.json", team_assets)
    write_json("player_ownership.json", ownership)
    write_json("free_agents_by_position.json", free_by_pos)
    write_json("recent_transactions.json", recent_transactions[:200])
    write_json("league_changes.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "first_run": previous_snapshot is None,
        "changes": latest_changes,
    })
    write_json("change_log.json", change_log)
    write_json("snapshot_state.json", current_snapshot)


if __name__ == "__main__":
    main()
