from __future__ import annotations

import itertools
import json
import math
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase4 import build_phase4_outputs
from external_intel import (
    attach_player_intel,
    build_market_summary,
    build_player_intel,
    enrich_current_power,
    enrich_opportunities,
    enrich_team_needs,
    enrich_trade_partners,
)

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data" / "current"
DERIVED = ROOT / "data" / "derived"
HISTORY = ROOT / "data" / "history"
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
        "QB": 4 if superflex else 2,
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

    total_candidates = len(opportunities)
    # The dashboard never needs thousands of deep free agents. Keeping the
    # strongest 300 makes this file small enough for GitHub/ChatGPT reads while
    # preserving substantially more candidates than the UI displays at once.
    opportunities = opportunities[:300]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "Signal score, not dynasty market value. Uses confirmed league availability, NFL roster status, depth chart, age, league format, Sleeper 24h add/drop trends, recent 715 drops, and injury/IR-slot context.",
        "sleeper_attribution": "Trending data provided by Sleeper.",
        "total_candidates": total_candidates,
        "players": opportunities,
    }



def pct(wins: float, ties: float, games: float) -> float:
    if games <= 0:
        return 0.0
    return (wins + (0.5 * ties)) / games


def completed_current_weeks(
    matchups: dict[str, Any],
    nfl_state: dict[str, Any],
) -> list[int]:
    current_week = int(nfl_state.get("week") or nfl_state.get("display_week") or 1)
    completed = []
    for week_text, rows in (matchups or {}).items():
        if not str(week_text).isdigit():
            continue
        week = int(week_text)
        if week >= current_week:
            continue
        if any(float((row or {}).get("points") or 0) != 0 for row in (rows or [])):
            completed.append(week)
    return sorted(completed)


def optimal_lineup(
    row: dict[str, Any],
    players: dict[str, Any],
    league: dict[str, Any],
) -> dict[str, Any]:
    roster_positions = league.get("roster_positions") or []
    starter_slots = [slot for slot in roster_positions if slot != "BN"]
    fixed_counts: dict[str, int] = defaultdict(int)
    variable_slots: list[list[str]] = []

    for slot in starter_slots:
        if slot in POSITIONS:
            fixed_counts[slot] += 1
        elif slot == "FLEX":
            variable_slots.append(["RB", "WR", "TE"])
        elif slot == "SUPER_FLEX":
            variable_slots.append(["QB", "RB", "WR", "TE"])

    points_by_pos: dict[str, list[tuple[float, str]]] = {pos: [] for pos in POSITIONS}
    total_player_rows = len(row.get("players_points") or {})
    recognized_player_rows = 0
    for pid, raw_points in (row.get("players_points") or {}).items():
        p = players.get(str(pid), {}) or {}
        pos = p.get("position")
        if pos not in POSITIONS:
            fantasy = p.get("fantasy_positions") or []
            pos = next((x for x in fantasy if x in POSITIONS), None)
        if pos not in POSITIONS:
            continue
        recognized_player_rows += 1
        try:
            points = float(raw_points or 0)
        except (TypeError, ValueError):
            points = 0.0
        points_by_pos[pos].append((points, str(pid)))

    for pos in POSITIONS:
        points_by_pos[pos].sort(key=lambda x: (x[0], x[1]), reverse=True)

    assignments = itertools.product(*variable_slots) if variable_slots else [()]
    best_points = None
    best_ids: list[str] = []

    for assigned in assignments:
        counts = dict(fixed_counts)
        for pos in assigned:
            counts[pos] = counts.get(pos, 0) + 1

        selected: list[tuple[float, str]] = []
        valid = True
        for pos, need in counts.items():
            available = points_by_pos.get(pos) or []
            if len(available) < need:
                valid = False
                break
            selected.extend(available[:need])
        if not valid:
            continue

        total = sum(x[0] for x in selected)
        if best_points is None or total > best_points:
            best_points = total
            best_ids = [x[1] for x in selected]

    actual = float(row.get("points") or 0)
    lineup_valid = best_points is not None
    if best_points is None:
        best_ids = []

    starter_set = {str(x) for x in (row.get("starters") or []) if str(x) != "0"}
    bench = []
    for pid, raw_points in (row.get("players_points") or {}).items():
        pid = str(pid)
        if pid in starter_set:
            continue
        try:
            points = float(raw_points or 0)
        except (TypeError, ValueError):
            points = 0.0
        bench.append((points, pid))
    bench.sort(reverse=True)

    bench_star = None
    if bench:
        points, pid = bench[0]
        bench_star = {
            **player_view(pid, players),
            "points": round(points, 2),
        }

    coverage = 100.0 if total_player_rows <= 0 else (recognized_player_rows / total_player_rows) * 100
    if lineup_valid and best_points is not None:
        efficiency = 100.0 if best_points <= 0 else max(0.0, min(100.0, (actual / best_points) * 100))
        optimal_points = round(best_points, 2)
        points_left = round(max(0.0, best_points - actual), 2)
        efficiency_value = round(efficiency, 1)
    else:
        optimal_points = None
        points_left = None
        efficiency_value = None

    return {
        "actual_points": round(actual, 2),
        "optimal_points": optimal_points,
        "points_left": points_left,
        "efficiency": efficiency_value,
        "valid": lineup_valid,
        "metadata_coverage": round(coverage, 1),
        "optimal_player_ids": best_ids,
        "bench_star": bench_star,
    }


def build_week_metrics(
    week: int,
    rows: list[dict[str, Any]],
    rosters: dict[str, Any],
    players: dict[str, Any],
    league: dict[str, Any],
    season: str | None = None,
) -> dict[str, Any]:
    score_rows = [row for row in (rows or []) if row.get("roster_id") is not None]
    scores = [float(row.get("points") or 0) for row in score_rows]
    average = statistics.mean(scores) if scores else 0.0
    median = statistics.median(scores) if scores else 0.0

    h2h: dict[str, dict[str, Any]] = {}
    by_matchup: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in score_rows:
        mid = row.get("matchup_id")
        if mid is not None:
            by_matchup[str(mid)].append(row)

    for pair in by_matchup.values():
        if len(pair) != 2:
            continue
        a, b = pair
        a_id, b_id = str(a["roster_id"]), str(b["roster_id"])
        a_score, b_score = float(a.get("points") or 0), float(b.get("points") or 0)
        if a_score > b_score:
            a_result, b_result = "W", "L"
        elif a_score < b_score:
            a_result, b_result = "L", "W"
        else:
            a_result = b_result = "T"
        h2h[a_id] = {"result": a_result, "opponent_roster_id": int(b_id), "opponent_points": round(b_score, 2)}
        h2h[b_id] = {"result": b_result, "opponent_roster_id": int(a_id), "opponent_points": round(a_score, 2)}

    teams = []
    for row in score_rows:
        rid = str(row["roster_id"])
        score = float(row.get("points") or 0)
        all_w = sum(1 for other in scores if score > other)
        all_l = sum(1 for other in scores if score < other)
        all_t = max(0, len(scores) - 1 - all_w - all_l)

        if score > median:
            median_result = "W"
        elif score < median:
            median_result = "L"
        else:
            median_result = "T"

        lineup = optimal_lineup(row, players, league)
        roster = rosters.get(rid) or {}
        teams.append({
            "roster_id": int(rid),
            "owner_id": str(roster.get("owner_id") or f"{season or league.get('season')}:{rid}"),
            "manager": roster.get("display_name"),
            "team_name": roster.get("team_name"),
            "score": round(score, 2),
            "score_vs_average": round(score - average, 2),
            "score_vs_median": round(score - median, 2),
            "h2h": h2h.get(rid) or {"result": None, "opponent_roster_id": None, "opponent_points": None},
            "all_play": {"wins": all_w, "losses": all_l, "ties": all_t},
            "median_result": median_result,
            "lineup": lineup,
        })

    teams.sort(key=lambda x: x["score"], reverse=True)
    return {
        "season": str(season or league.get("season") or ""),
        "week": week,
        "league_average": round(average, 2),
        "league_median": round(median, 2),
        "teams": teams,
    }


def aggregate_metrics(
    week_metrics: list[dict[str, Any]],
    identity: str = "roster",
    current_owner_to_roster: dict[str, int] | None = None,
) -> dict[str, Any]:
    accum: dict[str, dict[str, Any]] = {}
    current_owner_to_roster = current_owner_to_roster or {}

    for week in week_metrics:
        season = str(week.get("season") or "")
        for team in week.get("teams") or []:
            owner_id = str(team.get("owner_id") or "")
            key = owner_id if identity == "owner" else str(team["roster_id"])
            if key not in accum:
                accum[key] = {
                    "identity_id": key,
                    "owner_id": owner_id,
                    "roster_id": current_owner_to_roster.get(owner_id, team["roster_id"]),
                    "manager": team.get("manager"),
                    "team_name": team.get("team_name"),
                    "scores": [],
                    "h2h_wins": 0,
                    "h2h_losses": 0,
                    "h2h_ties": 0,
                    "all_play_wins": 0,
                    "all_play_losses": 0,
                    "all_play_ties": 0,
                    "median_wins": 0,
                    "median_losses": 0,
                    "median_ties": 0,
                    "actual_points": 0.0,
                    "optimal_points": 0.0,
                    "valid_lineup_weeks": 0,
                    "seasons": set(),
                }
            a = accum[key]
            a["owner_id"] = owner_id or a.get("owner_id")
            a["roster_id"] = current_owner_to_roster.get(owner_id, a["roster_id"])
            a["manager"] = team.get("manager") or a.get("manager")
            a["team_name"] = team.get("team_name") or a.get("team_name")
            a["scores"].append(float(team["score"]))
            if season:
                a["seasons"].add(season)

            result = (team.get("h2h") or {}).get("result")
            if result == "W":
                a["h2h_wins"] += 1
            elif result == "L":
                a["h2h_losses"] += 1
            elif result == "T":
                a["h2h_ties"] += 1

            ap = team.get("all_play") or {}
            a["all_play_wins"] += int(ap.get("wins") or 0)
            a["all_play_losses"] += int(ap.get("losses") or 0)
            a["all_play_ties"] += int(ap.get("ties") or 0)

            mr = team.get("median_result")
            if mr == "W":
                a["median_wins"] += 1
            elif mr == "L":
                a["median_losses"] += 1
            elif mr == "T":
                a["median_ties"] += 1

            lineup = team.get("lineup") or {}
            if lineup.get("valid") and lineup.get("optimal_points") is not None:
                a["actual_points"] += float(lineup.get("actual_points") or 0)
                a["optimal_points"] += float(lineup.get("optimal_points") or 0)
                a["valid_lineup_weeks"] += 1

    result = {}
    for key, a in accum.items():
        h2h_games = a["h2h_wins"] + a["h2h_losses"] + a["h2h_ties"]
        ap_games = a["all_play_wins"] + a["all_play_losses"] + a["all_play_ties"]
        median_games = a["median_wins"] + a["median_losses"] + a["median_ties"]
        h2h_pct = pct(a["h2h_wins"], a["h2h_ties"], h2h_games)
        ap_pct = pct(a["all_play_wins"], a["all_play_ties"], ap_games)
        median_pct = pct(a["median_wins"], a["median_ties"], median_games)

        if a["valid_lineup_weeks"] and a["optimal_points"] > 0:
            efficiency = (a["actual_points"] / a["optimal_points"]) * 100
            points_left = max(0.0, a["optimal_points"] - a["actual_points"])
        else:
            efficiency = None
            points_left = None

        result[key] = {
            "identity_id": key,
            "owner_id": a["owner_id"],
            "roster_id": a["roster_id"],
            "manager": a.get("manager"),
            "team_name": a.get("team_name"),
            "weeks": len(a["scores"]),
            "seasons": sorted(a["seasons"]),
            "points_for": round(sum(a["scores"]), 2),
            "average_score": round(statistics.mean(a["scores"]), 2) if a["scores"] else 0.0,
            "recent_3_average": round(statistics.mean(a["scores"][-3:]), 2) if a["scores"] else 0.0,
            "h2h": {
                "wins": a["h2h_wins"], "losses": a["h2h_losses"], "ties": a["h2h_ties"],
                "pct": round(h2h_pct, 4),
            },
            "all_play": {
                "wins": a["all_play_wins"], "losses": a["all_play_losses"], "ties": a["all_play_ties"],
                "pct": round(ap_pct, 4),
            },
            "median": {
                "wins": a["median_wins"], "losses": a["median_losses"], "ties": a["median_ties"],
                "pct": round(median_pct, 4),
            },
            "lineup_efficiency": round(efficiency, 1) if efficiency is not None else None,
            "lineup_weeks": a["valid_lineup_weeks"],
            "points_left_on_bench": round(points_left, 2) if points_left is not None else None,
            "luck_index": round((h2h_pct - ap_pct) * 100, 1),
        }
    return result


def aggregate_season_metrics(week_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return aggregate_metrics(week_metrics, identity="roster")


def minmax(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    low, high = min(values.values()), max(values.values())
    if math.isclose(low, high):
        return {key: 50.0 for key in values}
    return {key: ((value - low) / (high - low)) * 100 for key, value in values.items()}


def power_rows(
    metrics: dict[str, Any],
    scoring_field: str = "recent_3_average",
    scoring_component_name: str = "recent_scoring",
) -> list[dict[str, Any]]:
    scoring_norm = minmax({key: float(x.get(scoring_field) or 0) for key, x in metrics.items()})
    rows = []
    for key, x in metrics.items():
        efficiency = x.get("lineup_efficiency")
        # If lineup metadata is incomplete, redistribute that 15% across the
        # four fully available performance signals rather than treating it as 0.
        if efficiency is None:
            weights = {
                "scoring": 0.4118,
                "all_play": 0.2941,
                "median": 0.1765,
                "h2h_record": 0.1176,
            }
            components = {
                scoring_component_name: round(scoring_norm.get(key, 0), 1),
                "all_play": round(float((x.get("all_play") or {}).get("pct") or 0) * 100, 1),
                "median": round(float((x.get("median") or {}).get("pct") or 0) * 100, 1),
                "lineup_efficiency": None,
                "h2h_record": round(float((x.get("h2h") or {}).get("pct") or 0) * 100, 1),
            }
            score = (
                components[scoring_component_name] * weights["scoring"]
                + components["all_play"] * weights["all_play"]
                + components["median"] * weights["median"]
                + components["h2h_record"] * weights["h2h_record"]
            )
        else:
            components = {
                scoring_component_name: round(scoring_norm.get(key, 0), 1),
                "all_play": round(float((x.get("all_play") or {}).get("pct") or 0) * 100, 1),
                "median": round(float((x.get("median") or {}).get("pct") or 0) * 100, 1),
                "lineup_efficiency": round(float(efficiency), 1),
                "h2h_record": round(float((x.get("h2h") or {}).get("pct") or 0) * 100, 1),
            }
            score = (
                components[scoring_component_name] * 0.35
                + components["all_play"] * 0.25
                + components["median"] * 0.15
                + components["lineup_efficiency"] * 0.15
                + components["h2h_record"] * 0.10
            )

        rows.append({
            **x,
            "power_score": round(score, 1),
            "components": components,
        })
    rows.sort(key=lambda x: (-x["power_score"], -x["points_for"], x.get("manager") or ""))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    return rows


def build_power_rankings(
    week_metrics: list[dict[str, Any]],
    scope: str = "season",
    identity: str = "roster",
    current_owner_to_roster: dict[str, int] | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    all_time = scope == "all_time"
    methodology = (
        "35% career average scoring, 25% all-play, 15% median record, 15% lineup efficiency, 10% head-to-head record."
        if all_time else
        "35% recent scoring, 25% all-play, 15% median record, 15% lineup efficiency, 10% head-to-head record."
    )
    if not week_metrics:
        return {
            "generated_at": generated_at,
            "status": "awaiting_results",
            "latest_completed_week": None,
            "latest_season": None,
            "methodology": methodology,
            "rankings": [],
        }

    metrics = aggregate_metrics(week_metrics, identity=identity, current_owner_to_roster=current_owner_to_roster)
    scoring_field = "average_score" if all_time else "recent_3_average"
    component_name = "career_scoring" if all_time else "recent_scoring"
    current = power_rows(metrics, scoring_field=scoring_field, scoring_component_name=component_name)

    previous_rank = {}
    if len(week_metrics) > 1:
        previous_metrics = aggregate_metrics(
            week_metrics[:-1],
            identity=identity,
            current_owner_to_roster=current_owner_to_roster,
        )
        previous = power_rows(
            previous_metrics,
            scoring_field=scoring_field,
            scoring_component_name=component_name,
        )
        previous_rank = {str(row["identity_id"]): row["rank"] for row in previous}

    for row in current:
        prev = previous_rank.get(str(row["identity_id"]))
        row["previous_rank"] = prev
        row["movement"] = 0 if prev is None else prev - row["rank"]

    return {
        "generated_at": generated_at,
        "status": "live",
        "latest_completed_week": week_metrics[-1]["week"],
        "latest_season": week_metrics[-1].get("season"),
        "methodology": methodology + (
            " Career scoring is normalized across all loaded regular-season weeks."
            if all_time else
            " Recent scoring is the last three completed weeks and is normalized within the league."
        ),
        "rankings": current,
    }


def build_standings_plus(
    week_metrics: list[dict[str, Any]],
    identity: str = "roster",
    current_owner_to_roster: dict[str, int] | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    metrics = aggregate_metrics(
        week_metrics,
        identity=identity,
        current_owner_to_roster=current_owner_to_roster,
    ) if week_metrics else {}
    teams = list(metrics.values())
    teams.sort(
        key=lambda x: (
            -float((x.get("h2h") or {}).get("pct") or 0),
            -float((x.get("median") or {}).get("pct") or 0),
            -float(x.get("points_for") or 0),
        )
    )
    return {
        "generated_at": generated_at,
        "status": "live" if week_metrics else "awaiting_results",
        "latest_completed_week": week_metrics[-1]["week"] if week_metrics else None,
        "latest_season": week_metrics[-1].get("season") if week_metrics else None,
        "teams": teams,
    }


def build_lineup_efficiency(
    week_metrics: list[dict[str, Any]],
    identity: str = "roster",
    current_owner_to_roster: dict[str, int] | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    metrics = aggregate_metrics(
        week_metrics,
        identity=identity,
        current_owner_to_roster=current_owner_to_roster,
    ) if week_metrics else {}
    rows = list(metrics.values())
    rows.sort(
        key=lambda x: (
            x.get("lineup_efficiency") is None,
            -(x.get("lineup_efficiency") or 0),
            x.get("manager") or "",
        )
    )
    latest = week_metrics[-1] if week_metrics else None
    return {
        "generated_at": generated_at,
        "status": "live" if latest else "awaiting_results",
        "latest_completed_week": latest["week"] if latest else None,
        "latest_season": latest.get("season") if latest else None,
        "latest_week": latest,
        "season": rows,
    }


def award(key: str, title: str, emoji: str, team: dict[str, Any] | None, detail: str) -> dict[str, Any] | None:
    if not team:
        return None
    return {
        "key": key,
        "title": title,
        "emoji": emoji,
        "roster_id": team.get("roster_id"),
        "manager": team.get("manager"),
        "team_name": team.get("team_name"),
        "detail": detail,
    }


def build_weekly_recap(week_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    if not week_metrics:
        return {
            "generated_at": generated_at,
            "status": "awaiting_results",
            "week": None,
            "awards": [],
            "week_data": None,
        }

    week = week_metrics[-1]
    teams = week.get("teams") or []
    winners = [x for x in teams if (x.get("h2h") or {}).get("result") == "W"]
    losers = [x for x in teams if (x.get("h2h") or {}).get("result") == "L"]

    top = max(teams, key=lambda x: x["score"], default=None)
    nuclear = max(teams, key=lambda x: x["score_vs_average"], default=None)
    pain = max(losers, key=lambda x: x["score"], default=None)
    robbery = min(winners, key=lambda x: x["score"], default=None)
    # Historical lineup reconstruction can legitimately be unavailable when
    # Sleeper no longer exposes enough position metadata for an old player.
    # Exclude those samples from lineup-efficiency awards rather than trying
    # to compare None with numeric efficiency values.
    lineup_candidates = [
        x for x in teams
        if isinstance((x.get("lineup") or {}).get("efficiency"), (int, float))
    ]
    perfect = max(
        lineup_candidates,
        key=lambda x: (x.get("lineup") or {}).get("efficiency"),
        default=None,
    )
    disaster = min(
        lineup_candidates,
        key=lambda x: (x.get("lineup") or {}).get("efficiency"),
        default=None,
    )

    bench_candidates = [
        x for x in teams
        if (x.get("lineup") or {}).get("bench_star") is not None
    ]
    benchwarmer = max(
        bench_candidates,
        key=lambda x: ((x.get("lineup") or {}).get("bench_star") or {}).get("points", 0),
        default=None,
    )

    awards = [
        award("top_dog", "Top Dog", "🏆", top, f"{top['score']:.2f} points" if top else ""),
        award("nuclear_week", "Nuclear Week", "💣", nuclear, f"{nuclear['score_vs_average']:+.2f} vs league average" if nuclear else ""),
        award("pain", "Pain", "☠️", pain, f"Lost despite scoring {pain['score']:.2f}" if pain else ""),
        award("highway_robbery", "Highway Robbery", "🍀", robbery, f"Won with only {robbery['score']:.2f}" if robbery else ""),
        award("perfect_manager", "Galaxy Brain", "🧠", perfect, f"{float((perfect.get('lineup') or {}).get('efficiency')):.1f}% lineup efficiency" if perfect else ""),
        award("coaching_disaster", "Coaching Disaster", "🤡", disaster, f"{float((disaster.get('lineup') or {}).get('points_left') or 0):.2f} points left on bench" if disaster else ""),
    ]

    if benchwarmer:
        star = (benchwarmer.get("lineup") or {}).get("bench_star") or {}
        awards.append(award(
            "benchwarmer",
            "Benchwarmer of the Week",
            "🪑",
            benchwarmer,
            f"{star.get('name')} scored {float(star.get('points') or 0):.2f} on the bench",
        ))

    return {
        "generated_at": generated_at,
        "status": "live",
        "week": week["week"],
        "awards": [x for x in awards if x],
        "week_data": week,
    }


def build_draft_capital_matrix(
    team_assets: dict[str, Any],
) -> dict[str, Any]:
    years = sorted({
        str(pick.get("season"))
        for team in team_assets.values()
        for pick in (team.get("picks") or [])
        if pick.get("season") is not None
    })
    teams = []
    for rid, team in team_assets.items():
        cells = {}
        for year in years:
            picks = []
            for p in team.get("picks") or []:
                if str(p.get("season")) != year:
                    continue
                picks.append({
                    "round": int(p.get("round") or 0),
                    "original_roster_id": p.get("original_roster_id"),
                    "original_manager": p.get("original_manager"),
                    "own": int(p.get("original_roster_id") or -1) == int(rid),
                })
            picks.sort(key=lambda x: (x["round"], str(x.get("original_manager") or "")))
            cells[year] = picks
        summary = pick_summary(team.get("picks") or [])
        teams.append({
            "roster_id": int(rid),
            "manager": team.get("manager"),
            "team_name": team.get("team_name"),
            "summary": summary,
            "years": cells,
        })
    teams.sort(key=lambda x: (-x["summary"]["firsts"], -x["summary"]["early_picks"], x.get("manager") or ""))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "years": years,
        "teams": teams,
    }


def history_datasets() -> list[dict[str, Any]]:
    manifest = read_json(HISTORY / "manifest.json", {}) or {}
    datasets = []
    for item in manifest.get("seasons") or []:
        folder = HISTORY / str(item.get("folder"))
        league = read_json(folder / "league.json", {}) or {}
        rosters = read_json(folder / "roster_index.json", {}) or {}
        matchups = read_json(folder / "matchups.json", {}) or {}
        if league and rosters and matchups:
            datasets.append({
                "league": league,
                "rosters": rosters,
                "matchups": matchups,
                "historical": True,
            })
    return datasets


def regular_season_scored_weeks(
    matchups: dict[str, Any],
    league: dict[str, Any],
) -> list[int]:
    playoff_start = int((league.get("settings") or {}).get("playoff_week_start") or 99)
    weeks = []
    for week_text, rows in (matchups or {}).items():
        if not str(week_text).isdigit():
            continue
        week = int(week_text)
        if week >= playoff_start:
            continue
        if any(float((row or {}).get("points") or 0) != 0 for row in (rows or [])):
            weeks.append(week)
    return sorted(weeks)


def build_record_book(
    league: dict[str, Any],
    rosters: dict[str, Any],
    matchups: dict[str, Any],
    current_completed_weeks: list[int],
) -> dict[str, Any]:
    datasets = history_datasets()
    current_playoff_start = int((league.get("settings") or {}).get("playoff_week_start") or 99)
    datasets.append({
        "league": league,
        "rosters": rosters,
        "matchups": matchups,
        "historical": False,
        "completed_weeks": [week for week in current_completed_weeks if week < current_playoff_start],
    })

    weekly_scores = []
    games = []
    manager_totals: dict[str, dict[str, Any]] = {}
    h2h_totals: dict[tuple[str, str], dict[str, Any]] = {}

    seasons_loaded = []

    for data in datasets:
        season_league = data["league"]
        season = str(season_league.get("season") or "Unknown")
        season_rosters = data["rosters"]
        season_matchups = data["matchups"]
        weeks = data.get("completed_weeks")
        if weeks is None:
            weeks = regular_season_scored_weeks(season_matchups, season_league)
        seasons_loaded.append({
            "season": season,
            "league_id": season_league.get("league_id"),
            "historical": bool(data.get("historical")),
            "weeks_with_scores": len(weeks),
        })

        for week in weeks:
            rows = season_matchups.get(str(week)) or []
            by_matchup: dict[str, list[dict[str, Any]]] = defaultdict(list)

            for row in rows:
                rid = str(row.get("roster_id"))
                roster = season_rosters.get(rid) or {}
                owner_id = str(roster.get("owner_id") or f"{season}:{rid}")
                manager = roster.get("display_name") or f"Roster {rid}"
                points = float(row.get("points") or 0)
                weekly_scores.append({
                    "season": season,
                    "week": week,
                    "roster_id": int(rid),
                    "owner_id": owner_id,
                    "manager": manager,
                    "team_name": roster.get("team_name"),
                    "points": round(points, 2),
                })

                if owner_id not in manager_totals:
                    manager_totals[owner_id] = {
                        "owner_id": owner_id,
                        "manager": manager,
                        "wins": 0, "losses": 0, "ties": 0,
                        "points_for": 0.0, "games": 0,
                        "seasons": set(),
                    }
                mt = manager_totals[owner_id]
                mt["manager"] = manager
                mt["points_for"] += points
                mt["games"] += 1
                mt["seasons"].add(season)

                mid = row.get("matchup_id")
                if mid is not None:
                    by_matchup[str(mid)].append({
                        "owner_id": owner_id,
                        "manager": manager,
                        "points": points,
                        "roster_id": int(rid),
                    })

            for pair in by_matchup.values():
                if len(pair) != 2:
                    continue
                a, b = pair
                if a["points"] > b["points"]:
                    a_result, b_result = "W", "L"
                elif a["points"] < b["points"]:
                    a_result, b_result = "L", "W"
                else:
                    a_result = b_result = "T"

                for team, result in ((a, a_result), (b, b_result)):
                    mt = manager_totals[team["owner_id"]]
                    if result == "W":
                        mt["wins"] += 1
                    elif result == "L":
                        mt["losses"] += 1
                    else:
                        mt["ties"] += 1

                games.append({
                    "season": season,
                    "week": week,
                    "a": a,
                    "b": b,
                    "margin": round(abs(a["points"] - b["points"]), 2),
                })

                key = tuple(sorted([a["owner_id"], b["owner_id"]]))
                if key not in h2h_totals:
                    h2h_totals[key] = {
                        "owner_ids": list(key),
                        "managers": {},
                        "wins": defaultdict(int),
                        "ties": 0,
                        "games": 0,
                        "points": defaultdict(float),
                    }
                ht = h2h_totals[key]
                ht["managers"][a["owner_id"]] = a["manager"]
                ht["managers"][b["owner_id"]] = b["manager"]
                ht["games"] += 1
                ht["points"][a["owner_id"]] += a["points"]
                ht["points"][b["owner_id"]] += b["points"]
                if a_result == "W":
                    ht["wins"][a["owner_id"]] += 1
                elif b_result == "W":
                    ht["wins"][b["owner_id"]] += 1
                else:
                    ht["ties"] += 1

    manager_rows = []
    for mt in manager_totals.values():
        manager_rows.append({
            **{k: v for k, v in mt.items() if k != "seasons"},
            "points_for": round(mt["points_for"], 2),
            "seasons": sorted(mt["seasons"]),
            "win_pct": round(pct(mt["wins"], mt["ties"], mt["wins"] + mt["losses"] + mt["ties"]), 4),
            "average_score": round(mt["points_for"] / mt["games"], 2) if mt["games"] else 0.0,
        })
    manager_rows.sort(key=lambda x: (-x["wins"], -x["win_pct"], -x["points_for"]))

    h2h_rows = []
    for ht in h2h_totals.values():
        owners = ht["owner_ids"]
        h2h_rows.append({
            "owner_ids": owners,
            "managers": [ht["managers"].get(x) for x in owners],
            "wins": {x: int(ht["wins"].get(x, 0)) for x in owners},
            "ties": ht["ties"],
            "games": ht["games"],
            "points": {x: round(ht["points"].get(x, 0), 2) for x in owners},
        })

    highest_week = max(weekly_scores, key=lambda x: x["points"], default=None)
    lowest_week = min((x for x in weekly_scores if x["points"] > 0), key=lambda x: x["points"], default=None)
    closest_game = min(games, key=lambda x: x["margin"], default=None)
    biggest_blowout = max(games, key=lambda x: x["margin"], default=None)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons_loaded": sorted(seasons_loaded, key=lambda x: x["season"]),
        "records": {
            "highest_week": highest_week,
            "lowest_nonzero_week": lowest_week,
            "closest_game": closest_game,
            "biggest_blowout": biggest_blowout,
        },
        "manager_careers": manager_rows,
        "head_to_head": h2h_rows,
        "note": "Record book uses regular-season Sleeper matchups only (through the week before each season's playoff_week_start), preventing inactive playoff-team rows from creating false games. Championship/bracket records can be added separately later.",
    }


def analytics_datasets(
    league: dict[str, Any],
    rosters: dict[str, Any],
    matchups: dict[str, Any],
    current_completed_weeks: list[int],
) -> list[dict[str, Any]]:
    datasets = history_datasets()
    current_playoff_start = int((league.get("settings") or {}).get("playoff_week_start") or 99)
    datasets.append({
        "league": league,
        "rosters": rosters,
        "matchups": matchups,
        "historical": False,
        "completed_weeks": [week for week in current_completed_weeks if week < current_playoff_start],
    })
    return sorted(datasets, key=lambda x: str((x.get("league") or {}).get("season") or ""))


def season_week_metrics(
    datasets: list[dict[str, Any]],
    players: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for data in datasets:
        season_league = data["league"]
        season = str(season_league.get("season") or "")
        season_rosters = data["rosters"]
        season_matchups = data["matchups"]
        weeks = data.get("completed_weeks")
        if weeks is None:
            weeks = regular_season_scored_weeks(season_matchups, season_league)
        result[season] = [
            build_week_metrics(
                week,
                season_matchups.get(str(week)) or [],
                season_rosters,
                players,
                season_league,
                season=season,
            )
            for week in weeks
        ]
    return result


def recap_archive(seasons: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    archive = {}
    latest = None
    for season in sorted(seasons):
        week_metrics = seasons[season]
        weeks = {}
        for metric in week_metrics:
            recap = build_weekly_recap([metric])
            recap["season"] = season
            weeks[str(metric["week"])] = recap
            latest = recap
        archive[season] = {
            "season": season,
            "weeks": weeks,
            "available_weeks": [x["week"] for x in week_metrics],
        }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seasons": archive,
        "latest_available": latest,
    }


def build_phase3(
    league: dict[str, Any],
    rosters: dict[str, Any],
    players: dict[str, Any],
    matchups: dict[str, Any],
    nfl_state: dict[str, Any],
    team_assets: dict[str, Any],
) -> dict[str, Any]:
    completed_weeks = completed_current_weeks(matchups, nfl_state)
    datasets = analytics_datasets(league, rosters, matchups, completed_weeks)
    seasons = season_week_metrics(datasets, players)
    current_season = str(league.get("season") or "")
    current_metrics = seasons.get(current_season, [])
    all_metrics = [
        metric
        for season in sorted(seasons)
        for metric in seasons[season]
    ]

    current_owner_to_roster = {
        str(roster.get("owner_id")): int(rid)
        for rid, roster in rosters.items()
        if roster.get("owner_id") is not None
    }

    season_power = {
        season: build_power_rankings(metrics, scope="season")
        for season, metrics in seasons.items()
    }
    season_standings = {
        season: build_standings_plus(metrics)
        for season, metrics in seasons.items()
    }
    season_lineups = {
        season: build_lineup_efficiency(metrics)
        for season, metrics in seasons.items()
    }

    power = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_season": current_season,
        "available_seasons": sorted(seasons),
        "scopes": {
            "current": season_power.get(current_season) or build_power_rankings([]),
            "all_time": build_power_rankings(
                all_metrics,
                scope="all_time",
                identity="owner",
                current_owner_to_roster=current_owner_to_roster,
            ),
        },
        "seasons": season_power,
    }
    standings = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_season": current_season,
        "available_seasons": sorted(seasons),
        "scopes": {
            "current": season_standings.get(current_season) or build_standings_plus([]),
            "all_time": build_standings_plus(
                all_metrics,
                identity="owner",
                current_owner_to_roster=current_owner_to_roster,
            ),
        },
        "seasons": season_standings,
    }
    lineups = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_season": current_season,
        "available_seasons": sorted(seasons),
        "scopes": {
            "current": season_lineups.get(current_season) or build_lineup_efficiency([]),
            "all_time": build_lineup_efficiency(
                all_metrics,
                identity="owner",
                current_owner_to_roster=current_owner_to_roster,
            ),
        },
        "seasons": season_lineups,
    }
    recaps = recap_archive(seasons)
    recaps["current_season"] = current_season
    recaps["latest_current"] = (
        build_weekly_recap(current_metrics) if current_metrics
        else build_weekly_recap([])
    )

    return {
        "completed_weeks": completed_weeks,
        "power_rankings": power,
        "standings_plus": standings,
        "lineup_efficiency": lineups,
        "weekly_recap": recaps,
        "draft_capital": build_draft_capital_matrix(team_assets),
        "record_book": build_record_book(league, rosters, matchups, completed_weeks),
    }



def main() -> None:
    league = read_json(CURRENT / "league.json", {}) or {}
    rosters = read_json(CURRENT / "roster_index.json", {}) or {}
    picks = read_json(CURRENT / "pick_ownership.json", []) or []
    players = read_json(CURRENT / "players_active.json", {}) or {}
    known_players = read_json(CURRENT / "players_known.json", {}) or players
    free_agents = read_json(CURRENT / "free_agents.json", {}) or {}
    transactions = read_json(CURRENT / "transactions.json", {}) or {}
    matchups = read_json(CURRENT / "matchups.json", {}) or {}
    nfl_state = read_json(CURRENT / "nfl_state.json", {}) or {}
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

    phase3 = build_phase3(
        league,
        rosters,
        known_players,
        matchups,
        nfl_state,
        team_assets,
    )

    # Phase 4.6 — shared Player Intelligence layer.
    # External feeds are optional. If the first external sync has not run yet,
    # these helpers simply attach empty market/performance fields and preserve
    # all pre-existing algorithms.
    player_intel = build_player_intel(
        ROOT, team_assets, free_agents, players, league
    )
    team_assets = attach_player_intel(
        team_assets, free_by_pos, player_intel, rosters, league
    )
    market_summary = build_market_summary(team_assets, league)
    team_needs = enrich_team_needs(team_needs, market_summary)
    trade_partners = enrich_trade_partners(trade_partners, market_summary)
    opportunities = enrich_opportunities(opportunities, player_intel)
    phase3["power_rankings"] = enrich_current_power(
        phase3["power_rankings"],
        market_summary,
        phase3.get("completed_weeks") or [],
    )

    # Compact analysis bundle for ChatGPT. Raw current/ files remain the
    # source of truth; this file is only a fast, derived decision-support view.
    opportunity_players = opportunities.get("players") or []
    opportunity_by_position = {
        pos: [p for p in opportunity_players if p.get("position") == pos][:20]
        for pos in POSITIONS
    }
    my_team = team_assets.get(MY_ROSTER_ID) or {}
    my_needs = (team_needs.get("teams") or {}).get(MY_ROSTER_ID) or {}
    my_trade_partners = (trade_partners.get("partners") or {}).get(MY_ROSTER_ID) or []

    chatgpt_context = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "Derived convenience file only. data/current remains authoritative for ownership, availability, picks, rosters, and league settings.",
        "league_summary": league_summary,
        "my_team": my_team,
        "my_roster_profile": my_needs,
        "trade_partners": my_trade_partners,
        "top_opportunities_by_position": opportunity_by_position,
        "latest_detected_changes": latest_changes[-30:],
        "recent_transactions": recent_transactions[:30],
        "power_rankings": phase3["power_rankings"].get("scopes"),
        "standings_plus": phase3["standings_plus"].get("scopes"),
        "lineup_efficiency": phase3["lineup_efficiency"].get("scopes"),
        "latest_weekly_recap": phase3["weekly_recap"].get("latest_available"),
        "draft_capital": phase3["draft_capital"],
        "player_intel_sources": {
            "market": player_intel.get("market_source"),
            "performance": player_intel.get("performance_source"),
            "coverage": player_intel.get("coverage"),
        },
        "my_market_profile": next(
            (x for x in (market_summary.get("teams") or []) if str(x.get("roster_id")) == MY_ROSTER_ID),
            None,
        ),
    }

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
    write_json("opportunity_top50.json", {
        "generated_at": opportunities.get("generated_at"),
        "methodology": opportunities.get("methodology"),
        "sleeper_attribution": opportunities.get("sleeper_attribution"),
        "players": (opportunities.get("players") or [])[:50],
    })
    write_json("player_intel.json", player_intel)
    write_json("roster_market_values.json", market_summary)
    write_json("chatgpt_context.json", chatgpt_context)

    # Phase 3 — League Lab
    write_json("power_rankings.json", phase3["power_rankings"])
    write_json("standings_plus.json", phase3["standings_plus"])
    write_json("lineup_efficiency.json", phase3["lineup_efficiency"])
    write_json("weekly_recap.json", phase3["weekly_recap"])
    write_json("draft_capital_matrix.json", phase3["draft_capital"])
    write_json("record_book.json", phase3["record_book"])

    # Phase 4 — Forecasting + franchise intelligence
    build_phase4_outputs(ROOT)


if __name__ == "__main__":
    main()
