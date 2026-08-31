from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data" / "current"
DERIVED = ROOT / "data" / "derived"
POSITIONS = ("QB", "RB", "WR", "TE")
MY_ROSTER_ID = "3"


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


def numeric_depth(p: dict[str, Any]) -> int | None:
    for key in ("depth_chart_order", "depth_chart_position"):
        value = p.get(key)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def free_agent_sort_key(p: dict[str, Any]) -> tuple:
    team_penalty = 0 if p.get("team") else 1
    depth = numeric_depth(p) or 99
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


def pick_summary(picks: list[dict[str, Any]]) -> dict[str, Any]:
    by_round = {str(r): 0 for r in range(1, 6)}
    by_year: dict[str, int] = defaultdict(int)
    for pick in picks:
        rnd = str(pick.get("round"))
        if rnd in by_round:
            by_round[rnd] += 1
        by_year[str(pick.get("season"))] += 1
    return {
        "total": len(picks),
        "firsts": by_round["1"],
        "seconds": by_round["2"],
        "early_picks": by_round["1"] + by_round["2"],
        "by_round": by_round,
        "by_year": dict(sorted(by_year.items())),
    }


def build_team_needs(
    team_assets: dict[str, Any],
    league: dict[str, Any],
) -> dict[str, Any]:
    if not team_assets:
        return {"teams": {}, "league_position_averages": {}}

    averages = {}
    for pos in POSITIONS:
        counts = [int((team.get("position_counts") or {}).get(pos, 0)) for team in team_assets.values()]
        averages[pos] = round(sum(counts) / len(counts), 2)

    roster_positions = league.get("roster_positions") or []
    superflex = "SUPER_FLEX" in roster_positions

    # Practical depth targets for this league. These are roster-shape heuristics,
    # not claims about player quality.
    targets = {
        "QB": 3 if superflex else 2,
        "RB": 5,
        "WR": 7,
        "TE": 2,
    }

    profiles: dict[str, Any] = {}
    for rid, team in team_assets.items():
        counts = team.get("position_counts") or {}
        starter_counts = defaultdict(int)
        for p in team.get("players") or []:
            if p.get("starter") and p.get("position") in POSITIONS:
                starter_counts[p["position"]] += 1

        positions = {}
        needs = []
        surpluses = []

        for pos in POSITIONS:
            count = int(counts.get(pos, 0))
            avg = averages[pos]
            delta = round(count - avg, 2)
            target_gap = max(0, targets[pos] - count)
            comparative_need = max(0.0, -delta)
            comparative_surplus = max(0.0, delta)

            need_strength = round(max(float(target_gap), comparative_need), 2)
            surplus_strength = round(
                comparative_surplus if count >= targets[pos] else 0.0,
                2,
            )

            if count < targets[pos] or delta <= -1.0:
                label = "thin"
            elif delta <= -0.5:
                label = "below avg"
            elif delta >= 1.25 and count >= targets[pos]:
                label = "deep"
            elif delta >= 0.5 and count >= targets[pos]:
                label = "above avg"
            else:
                label = "balanced"

            positions[pos] = {
                "count": count,
                "starters": int(starter_counts.get(pos, 0)),
                "league_average": avg,
                "delta_vs_average": delta,
                "target": targets[pos],
                "label": label,
                "need_strength": need_strength,
                "surplus_strength": surplus_strength,
            }

            if need_strength >= 0.75:
                needs.append({
                    "position": pos,
                    "strength": need_strength,
                    "label": label,
                })
            if surplus_strength >= 0.75:
                surpluses.append({
                    "position": pos,
                    "strength": surplus_strength,
                    "label": label,
                })

        needs.sort(key=lambda x: x["strength"], reverse=True)
        surpluses.sort(key=lambda x: x["strength"], reverse=True)

        profiles[str(rid)] = {
            "roster_id": int(rid),
            "manager": team.get("manager"),
            "team_name": team.get("team_name"),
            "positions": positions,
            "needs": needs,
            "surpluses": surpluses,
            "pick_summary": pick_summary(team.get("picks") or []),
            "faab_remaining": (team.get("waivers") or {}).get("faab_remaining"),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "Roster-shape heuristic only. Needs/surpluses compare position counts with league averages and practical depth targets; player quality is not included.",
        "targets": targets,
        "league_position_averages": averages,
        "teams": profiles,
    }


def build_trade_partners(team_needs: dict[str, Any]) -> dict[str, Any]:
    profiles = team_needs.get("teams") or {}
    output: dict[str, list[dict[str, Any]]] = {}

    for source_id, source in profiles.items():
        source_needs = {x["position"]: x["strength"] for x in source.get("needs") or []}
        source_surpluses = {x["position"]: x["strength"] for x in source.get("surpluses") or []}
        source_picks = source.get("pick_summary") or {}
        partners = []

        for partner_id, partner in profiles.items():
            if partner_id == source_id:
                continue

            partner_needs = {x["position"]: x["strength"] for x in partner.get("needs") or []}
            partner_surpluses = {x["position"]: x["strength"] for x in partner.get("surpluses") or []}
            raw_score = 0.0
            reasons = []

            for pos in POSITIONS:
                if pos in source_needs and pos in partner_surpluses:
                    match = min(source_needs[pos], partner_surpluses[pos])
                    raw_score += 2.5 * match
                    reasons.append(f"They are deep at {pos}, where you are comparatively thin.")
                if pos in source_surpluses and pos in partner_needs:
                    match = min(source_surpluses[pos], partner_needs[pos])
                    raw_score += 2.0 * match
                    reasons.append(f"You have relative {pos} depth that matches one of their needs.")

            their_picks = partner.get("pick_summary") or {}
            early_diff = int(their_picks.get("early_picks", 0)) - int(source_picks.get("early_picks", 0))
            if early_diff >= 2:
                raw_score += 0.6
                reasons.append("They hold meaningfully more 1st/2nd-round draft capital.")
            if int(their_picks.get("firsts", 0)) >= 2:
                raw_score += 0.35
                reasons.append("They have multiple future first-round picks available as trade liquidity.")

            fit_score = round(min(10.0, raw_score), 1)
            if not reasons:
                reasons = ["No obvious roster-construction mismatch; a deal would be driven more by player preference than team need."]

            partners.append({
                "roster_id": int(partner_id),
                "manager": partner.get("manager"),
                "team_name": partner.get("team_name"),
                "fit_score": fit_score,
                "reasons": reasons[:5],
                "their_needs": partner.get("needs") or [],
                "their_surpluses": partner.get("surpluses") or [],
                "pick_summary": their_picks,
            })

        partners.sort(key=lambda x: (-x["fit_score"], x.get("manager") or ""))
        output[source_id] = partners

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "Fit score measures roster and draft-capital complementarity only. It is not a player-value or trade-fairness score.",
        "partners": output,
    }


def trend_map(items: list[dict[str, Any]]) -> dict[str, int]:
    result = {}
    for item in items or []:
        pid = item.get("player_id")
        if pid is not None:
            result[str(pid)] = int(item.get("count") or 0)
    return result


def scaled_trend(count: int, maximum: int, cap: float) -> float:
    if count <= 0 or maximum <= 0:
        return 0.0
    return cap * (math.log1p(count) / math.log1p(maximum))


def build_opportunities(
    free_agents: dict[str, Any],
    players: dict[str, Any],
    trending_adds: list[dict[str, Any]],
    trending_drops: list[dict[str, Any]],
    recent_transactions: list[dict[str, Any]],
    league: dict[str, Any],
) -> dict[str, Any]:
    add_map = trend_map(trending_adds)
    drop_map = trend_map(trending_drops)
    max_add = max(add_map.values(), default=0)
    max_drop = max(drop_map.values(), default=0)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    no_ir = int((league.get("settings") or {}).get("reserve_slots") or 0) == 0
    superflex = "SUPER_FLEX" in (league.get("roster_positions") or [])

    recent_drop: dict[str, dict[str, Any]] = {}
    for tx in recent_transactions:
        created = tx.get("created")
        if not isinstance(created, (int, float)):
            continue
        age_days = max(0.0, (now_ms - created) / 86_400_000)
        if age_days > 14:
            continue
        for drop in tx.get("drops") or []:
            pid = str((drop.get("player") or {}).get("player_id") or "")
            if pid and pid not in recent_drop:
                recent_drop[pid] = {
                    "age_days": round(age_days, 1),
                    "manager": drop.get("manager"),
                }

    opportunities = []
    for pid, raw in free_agents.items():
        p = player_view(str(pid), players)
        if p["name"].startswith("Sleeper ") and raw:
            p = player_view(str(pid), {str(pid): raw})

        pos = p.get("position")
        if pos not in POSITIONS:
            continue

        score = 5.0
        reasons = []
        depth = numeric_depth(p)
        add_count = add_map.get(str(pid), 0)
        drop_count = drop_map.get(str(pid), 0)

        if p.get("team"):
            score += 15
            reasons.append(f"Currently on an NFL roster ({p['team']}).")
        else:
            score -= 8
            reasons.append("Not currently attached to an NFL team.")

        if depth == 1:
            score += 26
            reasons.append("Listed first on the Sleeper depth chart.")
        elif depth == 2:
            score += 21
            reasons.append("Depth-chart No. 2: direct contingent path to usage.")
        elif depth == 3:
            score += 13
            reasons.append("Depth-chart No. 3: plausible contingent upside.")
        elif depth == 4:
            score += 5
            reasons.append("Depth-chart No. 4: deeper path to touches.")
        elif depth is None:
            reasons.append("No reliable depth-chart order is currently available.")

        age = p.get("age")
        if isinstance(age, (int, float)):
            if age <= 22:
                score += 10
                reasons.append("Very young for a dynasty stash.")
            elif age <= 24:
                score += 7
                reasons.append("Age supports long-term value growth.")
            elif age <= 26:
                score += 3

        if pos == "RB" and depth is not None and depth <= 3:
            score += 8
            reasons.append("RB contingent value can rise quickly with one depth-chart change.")
        elif pos == "QB" and superflex:
            score += 5
            reasons.append("Superflex format raises the value of any QB with a path to starts.")

        add_signal = scaled_trend(add_count, max_add, 25.0)
        drop_signal = scaled_trend(drop_count, max_drop, 14.0)
        score += add_signal
        score -= drop_signal
        if add_count:
            reasons.append(f"Sleeper market heat: {add_count:,} adds in the 24h trend window.")
        if drop_count:
            reasons.append(f"Market headwind: {drop_count:,} drops in the 24h trend window.")

        if str(pid) in recent_drop:
            info = recent_drop[str(pid)]
            score += 8
            manager = info.get("manager") or "a 715 manager"
            reasons.append(f"Recently dropped by {manager}; worth checking for a league-specific market reset.")

        injury = str(p.get("injury_status") or "").lower()
        if injury:
            if any(token in injury for token in ("out", "ir", "pup", "susp")):
                penalty = 15 if no_ir else 8
                score -= penalty
                reasons.append("Unavailable/injured status is costly because this league has no IR slots." if no_ir else "Unavailable/injured status lowers immediate utility.")
            elif "doubt" in injury:
                score -= 7
            elif "question" in injury:
                score -= 2

        score = round(max(0.0, min(100.0, score)), 1)
        if score >= 70:
            tier = "Priority"
        elif score >= 55:
            tier = "Strong stash"
        elif score >= 40:
            tier = "Watch"
        else:
            tier = "Deep"

        opportunities.append({
            **p,
            "depth": depth,
            "opportunity_score": score,
            "tier": tier,
            "trending_adds_24h": add_count,
            "trending_drops_24h": drop_count,
            "recent_715_drop": recent_drop.get(str(pid)),
            "reasons": reasons[:7],
        })

    opportunities.sort(key=lambda x: (-x["opportunity_score"], x.get("name") or ""))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "Signal score, not dynasty market value. Uses confirmed league availability, NFL roster status, depth chart, age, league format, Sleeper 24h add/drop trends, recent 715 drops, and injury/IR-slot context.",
        "sleeper_attribution": "Trending data provided by Sleeper.",
        "players": opportunities,
    }


def main() -> None:
    league = read_json(CURRENT / "league.json", {}) or {}
    rosters = read_json(CURRENT / "roster_index.json", {}) or {}
    picks = read_json(CURRENT / "pick_ownership.json", []) or []
    players = read_json(CURRENT / "players_active.json", {}) or {}
    free_agents = read_json(CURRENT / "free_agents.json", {}) or {}
    transactions = read_json(CURRENT / "transactions.json", {}) or {}
    trending_adds = read_json(CURRENT / "trending_adds.json", []) or []
    trending_drops = read_json(CURRENT / "trending_drops.json", []) or []

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
        if p["name"].startswith("Sleeper ") and raw:
            p = player_view(str(pid), {str(pid): raw})
        pos = p.get("position")
        if pos in free_by_pos:
            free_by_pos[pos].append(p)
    for pos in free_by_pos:
        free_by_pos[pos].sort(key=free_agent_sort_key)

    recent_transactions = flatten_transactions(transactions, players, rosters)

    current_snapshot = make_snapshot(rosters, picks)
    previous_snapshot = read_json(DERIVED / "snapshot_state.json", None)
    latest_changes = build_changes(previous_snapshot, current_snapshot, players, rosters)
    existing_log = read_json(DERIVED / "change_log.json", []) or []
    if latest_changes:
        existing_log.extend(latest_changes)
    change_log = existing_log[-500:]

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

    team_needs = build_team_needs(team_assets, league)
    trade_partners = build_trade_partners(team_needs)
    opportunities = build_opportunities(
        free_agents,
        players,
        trending_adds,
        trending_drops,
        recent_transactions,
        league,
    )

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

    # Phase 2
    write_json("team_needs.json", team_needs)
    write_json("trade_partners.json", trade_partners)
    write_json("opportunity_scanner.json", opportunities)


if __name__ == "__main__":
    main()
