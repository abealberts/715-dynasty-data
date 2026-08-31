from __future__ import annotations

import itertools
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POSITIONS = ("QB", "RB", "WR", "TE")


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def minmax(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if math.isclose(lo, hi):
        return {k: 50.0 for k in values}
    return {k: ((v - lo) / (hi - lo)) * 100.0 for k, v in values.items()}


def market_optimal_lineup_value(players: list[dict[str, Any]], starter_slots: list[str]) -> float:
    by_pos = {pos: [] for pos in POSITIONS}
    for p in players:
        pos = p.get("position")
        if pos in by_pos:
            by_pos[pos].append(float(p.get("market_value") or 0))
    for pos in by_pos:
        by_pos[pos].sort(reverse=True)

    fixed = defaultdict(int)
    flex_count = 0
    sf_count = 0
    for slot in starter_slots:
        if slot in POSITIONS:
            fixed[slot] += 1
        elif slot == "FLEX":
            flex_count += 1
        elif slot == "SUPER_FLEX":
            sf_count += 1

    best = 0.0
    flex_eligible = ("RB", "WR", "TE")
    sf_eligible = ("QB", "RB", "WR", "TE")
    flex_assignments = list(itertools.product(flex_eligible, repeat=flex_count)) or [()]
    sf_assignments = list(itertools.product(sf_eligible, repeat=sf_count)) or [()]

    for flex in flex_assignments:
        for sf in sf_assignments:
            counts = dict(fixed)
            for pos in flex + sf:
                counts[pos] = counts.get(pos, 0) + 1
            legal = True
            total = 0.0
            for pos, count in counts.items():
                if count > len(by_pos.get(pos, [])):
                    legal = False
                    break
                total += sum(by_pos[pos][:count])
            if legal:
                best = max(best, total)
    return best


def selected_performance(performance: dict[str, Any], sid: str, season: int) -> dict[str, Any] | None:
    seasons = performance.get("seasons") or {}
    current = ((seasons.get(str(season)) or {}).get("players") or {}).get(sid)
    prior = ((seasons.get(str(season - 1)) or {}).get("players") or {}).get(sid)
    if current and int(current.get("games") or 0) > 0:
        return {**current, "basis": "current", "basis_label": str(season)}
    if prior and int(prior.get("games") or 0) > 0:
        return {**prior, "basis": "prior", "basis_label": str(season - 1)}
    return None


def build_player_intel(
    root: Path,
    team_assets: dict[str, Any],
    free_agents: dict[str, Any],
    players: dict[str, Any],
    league: dict[str, Any],
) -> dict[str, Any]:
    external = root / "data" / "external"
    market_payload = read_json(external / "dynasty_values.json", {}) or {}
    performance_payload = read_json(external / "player_performance.json", {}) or {}
    status = read_json(external / "external_status.json", {}) or {}
    market = market_payload.get("players") or {}
    season = int(league.get("season") or 2026)

    owned = {}
    relevant_ids = set(str(pid) for pid in free_agents)
    for rid, team in team_assets.items():
        for p in team.get("players") or []:
            pid = str(p.get("player_id"))
            relevant_ids.add(pid)
            owned[pid] = {
                "roster_id": int(rid),
                "manager": team.get("manager"),
                "team_name": team.get("team_name"),
            }

    rows = []
    by_id = {}
    for sid in relevant_ids:
        p = players.get(sid) or free_agents.get(sid) or {}
        name = p.get("full_name") or " ".join(
            x for x in [p.get("first_name"), p.get("last_name")] if x
        ) or f"Sleeper {sid}"
        pos = p.get("position")
        value = market.get(sid)
        perf = selected_performance(performance_payload, sid, season)
        row = {
            "player_id": sid,
            "name": name,
            "position": pos,
            "team": p.get("team"),
            "age": p.get("age"),
            "depth_chart_order": p.get("depth_chart_order"),
            "injury_status": p.get("injury_status"),
            "ownership": owned.get(sid),
            "available": sid not in owned,
            "market": value,
            "market_value": int((value or {}).get("current_value") or 0),
            "market_rank": (value or {}).get("rank"),
            "market_position_rank": (value or {}).get("position_rank"),
            "performance": perf,
        }
        rows.append(row)
        by_id[sid] = row

    rows.sort(key=lambda x: (-int(x.get("market_value") or 0), x.get("name") or ""))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_season": str(season),
        "market_source": {
            "name": "Dynasty Dealer",
            "url": "https://www.dynastydealer.com/",
            "attribution": "Values by Dynasty Dealer",
            "provider_timestamp": market_payload.get("provider_timestamp"),
        },
        "performance_source": {
            "name": "nflverse",
            "url": "https://nflverse.com/",
            "note": "Weekly box-score and snap-count data joined to Sleeper IDs through DynastyProcess.",
        },
        "external_status": status,
        "coverage": {
            "relevant_players": len(rows),
            "market_values": sum(1 for x in rows if x.get("market_value")),
            "performance_samples": sum(1 for x in rows if x.get("performance")),
        },
        "players": rows,
        "players_by_id": by_id,
    }


def attach_player_intel(
    team_assets: dict[str, Any],
    free_by_pos: dict[str, list[dict[str, Any]]],
    intel: dict[str, Any],
    rosters: dict[str, Any],
    league: dict[str, Any],
) -> dict[str, Any]:
    by_id = intel.get("players_by_id") or {}
    slots = [x for x in (league.get("roster_positions") or []) if x != "BN"]

    def decorate(p: dict[str, Any]) -> dict[str, Any]:
        sid = str(p.get("player_id"))
        info = by_id.get(sid) or {}
        return {
            **p,
            "market_value": int(info.get("market_value") or 0),
            "market_rank": info.get("market_rank"),
            "market_position_rank": info.get("market_position_rank"),
            "performance": info.get("performance"),
        }

    for rid, team in team_assets.items():
        team["players"] = [decorate(p) for p in (team.get("players") or [])]
        player_map = {str(p.get("player_id")): p for p in team["players"]}
        raw_starters = [str(x) for x in ((rosters.get(str(rid)) or {}).get("starters") or [])]

        position_slot_counts = defaultdict(int)
        lineup = []
        for idx, slot in enumerate(slots):
            position_slot_counts[slot] += 1
            suffix = position_slot_counts[slot]
            if slot in {"RB", "WR"}:
                label = f"{slot}{suffix}"
            elif slot == "SUPER_FLEX":
                label = "SUPERFLEX"
            else:
                label = slot
            sid = raw_starters[idx] if idx < len(raw_starters) else "0"
            player = player_map.get(sid) if sid != "0" else None
            lineup.append({
                "slot": slot,
                "slot_label": label,
                "slot_index": idx,
                "player_id": None if sid == "0" else sid,
                "player": player,
            })

        starter_ids = {x["player_id"] for x in lineup if x.get("player_id")}
        bench = [p for p in team["players"] if str(p.get("player_id")) not in starter_ids]
        bench_by_position = {
            pos: sorted(
                [p for p in bench if p.get("position") == pos],
                key=lambda p: (-int(p.get("market_value") or 0), p.get("name") or ""),
            )
            for pos in POSITIONS
        }
        other = [p for p in bench if p.get("position") not in POSITIONS]
        if other:
            bench_by_position["OTHER"] = other

        team["lineup"] = lineup
        team["bench"] = bench
        team["bench_by_position"] = bench_by_position
        team["starters"] = [x["player"] for x in lineup if x.get("player")]

    for pos, rows in free_by_pos.items():
        free_by_pos[pos] = [decorate(p) for p in rows]

    return team_assets


def build_market_summary(
    team_assets: dict[str, Any],
    league: dict[str, Any],
) -> dict[str, Any]:
    slots = [x for x in (league.get("roster_positions") or []) if x != "BN"]
    raw_total = {}
    raw_starter = {}
    raw_depth = {}
    raw_pos = {pos: {} for pos in POSITIONS}
    details = {}

    for rid, team in team_assets.items():
        players = team.get("players") or []
        total = sum(float(p.get("market_value") or 0) for p in players)
        optimal_starter = market_optimal_lineup_value(players, slots)
        depth = max(0.0, total - optimal_starter)
        pos_values = {
            pos: sum(float(p.get("market_value") or 0) for p in players if p.get("position") == pos)
            for pos in POSITIONS
        }
        submitted = sum(
            float((x.get("player") or {}).get("market_value") or 0)
            for x in (team.get("lineup") or [])
        )
        raw_total[str(rid)] = total
        raw_starter[str(rid)] = optimal_starter
        raw_depth[str(rid)] = depth
        for pos in POSITIONS:
            raw_pos[pos][str(rid)] = pos_values[pos]
        details[str(rid)] = {
            "roster_id": int(rid),
            "manager": team.get("manager"),
            "team_name": team.get("team_name"),
            "total_market_value": int(total),
            "optimal_starter_market_value": int(optimal_starter),
            "submitted_starter_market_value": int(submitted),
            "depth_market_value": int(depth),
            "position_values": {k: int(v) for k, v in pos_values.items()},
        }

    total_scores = minmax(raw_total)
    starter_scores = minmax(raw_starter)
    depth_scores = minmax(raw_depth)
    pos_scores = {pos: minmax(values) for pos, values in raw_pos.items()}

    teams = []
    for rid, row in details.items():
        starter_score = starter_scores.get(rid, 50.0)
        depth_score = depth_scores.get(rid, 50.0)
        row["roster_market_score"] = round(starter_score * 0.75 + depth_score * 0.25, 1)
        row["starter_market_score"] = round(starter_score, 1)
        row["depth_market_score"] = round(depth_score, 1)
        row["total_market_score"] = round(total_scores.get(rid, 50.0), 1)
        row["position_scores"] = {
            pos: round(pos_scores[pos].get(rid, 50.0), 1)
            for pos in POSITIONS
        }
        teams.append(row)

    teams.sort(key=lambda x: (-x["roster_market_score"], -x["total_market_value"]))
    for rank, row in enumerate(teams, 1):
        row["market_rank"] = rank

    available = any(int(x.get("total_market_value") or 0) > 0 for x in teams)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "available": available,
        "source": "Dynasty Dealer",
        "source_url": "https://www.dynastydealer.com/",
        "attribution": "Values by Dynasty Dealer",
        "methodology": "Roster market score is 75% optimal legal starter market value and 25% remaining depth market value, normalized within 715. It is a market-liquidity signal, not an intrinsic player projection.",
        "teams": teams,
    }


def enrich_team_needs(team_needs: dict[str, Any], market_summary: dict[str, Any]) -> dict[str, Any]:
    if not market_summary.get("available"):
        return team_needs
    market_by_rid = {str(x["roster_id"]): x for x in market_summary.get("teams") or []}
    profiles = team_needs.get("teams") or {}
    for rid, profile in profiles.items():
        market = market_by_rid.get(str(rid)) or {}
        pos_scores = market.get("position_scores") or {}
        pos_values = market.get("position_values") or {}

        needs_map = {x["position"]: dict(x) for x in profile.get("needs") or []}
        surp_map = {x["position"]: dict(x) for x in profile.get("surpluses") or []}

        for pos in POSITIONS:
            info = (profile.get("positions") or {}).get(pos) or {}
            score = float(pos_scores.get(pos, 50.0))
            info["market_value"] = int(pos_values.get(pos, 0))
            info["market_score"] = round(score, 1)
            if score <= 30:
                label = "market-thin"
                strength = round((50.0 - score) / 12.5, 2)
                current = needs_map.get(pos, {"position": pos, "strength": 0.0, "label": label})
                if strength > float(current.get("strength") or 0):
                    current.update({"strength": strength, "label": label})
                needs_map[pos] = current
            elif score >= 70:
                label = "market-deep"
                strength = round((score - 50.0) / 12.5, 2)
                current = surp_map.get(pos, {"position": pos, "strength": 0.0, "label": label})
                if strength > float(current.get("strength") or 0):
                    current.update({"strength": strength, "label": label})
                surp_map[pos] = current
            info["quality_label"] = (
                "market-thin" if score <= 30
                else "market-deep" if score >= 70
                else "market-balanced"
            )

        profile["market"] = market
        profile["needs"] = sorted(needs_map.values(), key=lambda x: x["strength"], reverse=True)
        profile["surpluses"] = sorted(surp_map.values(), key=lambda x: x["strength"], reverse=True)

    team_needs["methodology"] = (
        str(team_needs.get("methodology") or "")
        + " Phase 4.6 also layers Dynasty Dealer position-market scores onto count-based needs/surpluses; low-value rooms can register as needs even when the raw player count is adequate."
    )
    team_needs["market_attribution"] = "Values by Dynasty Dealer — https://www.dynastydealer.com/"
    return team_needs


def enrich_trade_partners(
    trade_partners: dict[str, Any],
    market_summary: dict[str, Any],
) -> dict[str, Any]:
    if not market_summary.get("available"):
        return trade_partners
    market = {str(x["roster_id"]): x for x in market_summary.get("teams") or []}
    for source_rid, partners in (trade_partners.get("partners") or {}).items():
        source = market.get(str(source_rid)) or {}
        source_pos = source.get("position_scores") or {}
        for p in partners:
            partner = market.get(str(p.get("roster_id"))) or {}
            partner_pos = partner.get("position_scores") or {}
            market_fit = 0.0
            market_reasons = []

            for pos in POSITIONS:
                src = float(source_pos.get(pos, 50.0))
                dst = float(partner_pos.get(pos, 50.0))
                if src <= 35 and dst >= 65:
                    market_fit += min(2.25, ((dst - src) / 35.0) * 1.5)
                    market_reasons.append(f"Their {pos} room is materially stronger by current dynasty market value.")
                if src >= 65 and dst <= 35:
                    market_fit += min(1.75, ((src - dst) / 35.0) * 1.2)
                    market_reasons.append(f"Your {pos} market depth lines up with one of their weaker rooms.")

            # Market fit supplements roster-count fit; it does not claim a
            # particular package is fair.
            old_fit = float(p.get("fit_score") or 0)
            final_fit = min(10.0, old_fit * 0.68 + min(10.0, market_fit * 2.3) * 0.32)
            if partner.get("total_market_value", 0) > source.get("total_market_value", 0) * 1.2:
                final_fit = min(10.0, final_fit + 0.25)

            p["count_fit_score"] = round(old_fit, 1)
            p["market_fit_score"] = round(min(10.0, market_fit * 2.3), 1)
            p["fit_score"] = round(final_fit, 1)
            p["market"] = {
                "their_total_value": partner.get("total_market_value"),
                "their_starter_value": partner.get("optimal_starter_market_value"),
                "their_market_rank": partner.get("market_rank"),
                "position_scores": partner_pos,
            }
            p["reasons"] = (market_reasons + (p.get("reasons") or []))[:6]

        partners.sort(key=lambda x: (-float(x.get("fit_score") or 0), x.get("manager") or ""))

    trade_partners["methodology"] = (
        "Trade-partner fit combines roster-count complementarity with current Dynasty Dealer position-market strength. It identifies plausible counterparties, not fair trade packages."
    )
    trade_partners["market_attribution"] = "Values by Dynasty Dealer — https://www.dynastydealer.com/"
    return trade_partners


def opportunity_market_bonus(value: int) -> float:
    if value >= 2500:
        return 12.0
    if value >= 1500:
        return 9.0
    if value >= 900:
        return 6.0
    if value >= 500:
        return 3.0
    return 0.0


def enrich_opportunities(opportunities: dict[str, Any], intel: dict[str, Any]) -> dict[str, Any]:
    by_id = intel.get("players_by_id") or {}
    for p in opportunities.get("players") or []:
        info = by_id.get(str(p.get("player_id"))) or {}
        value = int(info.get("market_value") or 0)
        perf = info.get("performance") or {}
        reasons = []
        bonus = opportunity_market_bonus(value)

        if value:
            p["market_value"] = value
            p["market_rank"] = info.get("market_rank")
            p["market_position_rank"] = info.get("market_position_rank")
            if bonus:
                reasons.append(f"Dynasty Dealer market value {value:,} adds insulation/upside signal.")
        p["performance"] = perf or None

        if perf:
            basis_weight = 1.0 if perf.get("basis") == "current" else 0.55
            snap = float(perf.get("offense_snap_pct") or 0)
            opp = float(perf.get("opportunities_per_game") or 0)
            ppg = float(perf.get("ppg_715") or 0)
            usage_bonus = 0.0
            if snap >= 70:
                usage_bonus += 8
            elif snap >= 50:
                usage_bonus += 6
            elif snap >= 30:
                usage_bonus += 3
            if opp >= 15:
                usage_bonus += 9
            elif opp >= 10:
                usage_bonus += 6
            elif opp >= 6:
                usage_bonus += 3
            if ppg >= 15:
                usage_bonus += 7
            elif ppg >= 10:
                usage_bonus += 5
            elif ppg >= 6:
                usage_bonus += 2

            last3 = perf.get("last3_opportunities_per_game")
            if isinstance(last3, (int, float)) and last3 - opp >= 2.0 and perf.get("basis") == "current":
                usage_bonus += 4
                reasons.append("Recent opportunity volume is running above the season baseline.")

            bonus += usage_bonus * basis_weight
            basis = "current-season" if perf.get("basis") == "current" else f"{perf.get('basis_label')} prior"
            reasons.append(
                f"{basis} usage: {opp:.1f} opportunities/game, {snap:.0f}% offensive snaps, {ppg:.1f} 715 PPG."
            )

        p["opportunity_score"] = round(min(100.0, float(p.get("opportunity_score") or 0) + bonus), 1)
        score = p["opportunity_score"]
        p["tier"] = "Priority" if score >= 70 else "Strong stash" if score >= 55 else "Watch" if score >= 40 else "Deep"
        p["reasons"] = (reasons + (p.get("reasons") or []))[:10]

    opportunities["players"].sort(key=lambda x: (-float(x.get("opportunity_score") or 0), x.get("name") or ""))
    opportunities["methodology"] = (
        str(opportunities.get("methodology") or "")
        + " Phase 4.6 adds Dynasty Dealer market value plus nflverse offensive snap share, opportunities, 715-scoring production, and current usage trend. Prior-season performance is deliberately discounted until current-season data exists."
    )
    opportunities["market_attribution"] = "Values by Dynasty Dealer — https://www.dynastydealer.com/"
    opportunities["performance_attribution"] = "NFL performance data via nflverse — https://nflverse.com/"
    return opportunities


def enrich_current_power(
    power_bundle: dict[str, Any],
    market_summary: dict[str, Any],
    completed_weeks: list[int],
) -> dict[str, Any]:
    scopes = power_bundle.get("scopes") or {}
    historical = scopes.get("all_time") or {}
    current = scopes.get("current") or {}

    prior_by_owner = {
        str(x.get("owner_id")): x
        for x in (historical.get("rankings") or [])
        if x.get("owner_id") is not None
    }
    market_rows = market_summary.get("teams") or []
    if not market_summary.get("available") or not market_rows:
        return power_bundle

    current_by_rid = {
        str(x.get("roster_id")): x
        for x in (current.get("rankings") or [])
    }
    weeks = len(completed_weeks)

    current_weight = min(0.70, (weeks / 6.0) * 0.70)
    market_weight = 0.70 - min(0.40, (weeks / 6.0) * 0.40)
    prior_weight = max(0.0, 1.0 - current_weight - market_weight)

    rows = []
    for m in market_rows:
        rid = str(m.get("roster_id"))
        live = current_by_rid.get(rid)
        owner_id = None
        if live:
            owner_id = live.get("owner_id")
        if owner_id is None:
            # Roster IDs are stable within the current league but all-time is
            # keyed by owner; find the historical row matching current roster ID.
            historical_match = next(
                (x for x in (historical.get("rankings") or []) if str(x.get("roster_id")) == rid),
                None,
            )
            owner_id = (historical_match or {}).get("owner_id")
        prior = prior_by_owner.get(str(owner_id)) if owner_id is not None else None

        live_score = float((live or {}).get("power_score") or 0)
        prior_score = float((prior or {}).get("power_score") or 50)
        market_score = float(m.get("roster_market_score") or 50)

        # If there are no completed weeks, current_weight is zero and live data
        # is intentionally ignored.
        score = live_score * current_weight + prior_score * prior_weight + market_score * market_weight
        template = live or prior or {}
        rows.append({
            **template,
            "roster_id": int(rid),
            "manager": m.get("manager") or template.get("manager"),
            "team_name": m.get("team_name") or template.get("team_name"),
            "owner_id": owner_id,
            "power_score": round(score, 1),
            "market_strength": round(market_score, 1),
            "starter_market_value": m.get("optimal_starter_market_value"),
            "total_market_value": m.get("total_market_value"),
            "historical_prior_score": round(prior_score, 1),
            "live_performance_score": round(live_score, 1) if live else None,
            "components": {
                "current_performance": round(live_score, 1) if live else None,
                "historical_prior": round(prior_score, 1),
                "roster_market": round(market_score, 1),
            },
        })

    rows.sort(key=lambda x: (-float(x.get("power_score") or 0), -float(x.get("market_strength") or 0)))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
        row["movement"] = 0

    scopes["current"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "live",
        "basis": "preseason_enriched" if weeks == 0 else "inseason_enriched",
        "latest_completed_week": max(completed_weeks) if completed_weeks else None,
        "latest_season": power_bundle.get("current_season"),
        "methodology": (
            f"Current Power Score blends {current_weight*100:.0f}% current-season performance, "
            f"{prior_weight*100:.0f}% historical performance prior, and {market_weight*100:.0f}% "
            "current Dynasty Dealer roster-market strength. Current performance ramps to 70% by six completed weeks; market strength remains a 30% live roster-quality signal."
        ),
        "rankings": rows,
        "market_attribution": "Values by Dynasty Dealer — https://www.dynastydealer.com/",
    }
    power_bundle["scopes"] = scopes
    return power_bundle
