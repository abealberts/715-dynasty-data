from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MY_ROSTER_ID = "3"
POSITIONS = ("QB", "RB", "WR", "TE")
FLEX_POSITIONS = {"RB", "WR", "TE"}
SUPER_FLEX_POSITIONS = set(POSITIONS)
MAX_HISTORY_REPORTS = 16
SCHEMA_VERSION = "2.0"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def tier_for_value(value: Any) -> dict[str, Any]:
    market_value = int(number(value) or 0)
    if market_value >= 7000:
        return {"number": 1, "label": "Cornerstone"}
    if market_value >= 5000:
        return {"number": 2, "label": "Core Starter"}
    if market_value >= 3000:
        return {"number": 3, "label": "Rotation"}
    return {"number": 4, "label": "Speculative"}


def projection_for(player: dict[str, Any]) -> dict[str, Any]:
    performance = player.get("performance") or {}
    season_ppg = number(performance.get("ppg_715"))
    recent_ppg = number(performance.get("last3_ppg_715"))
    market_value = int(number(player.get("market_value")) or 0)
    position = player.get("position") or "OTHER"

    if season_ppg is not None:
        recent = recent_ppg if recent_ppg is not None else season_ppg
        projected = season_ppg * 0.65 + recent * 0.35
        basis_label = performance.get("basis_label") or "available"
        basis = f"{basis_label} 715 PPG blended with recent form"
        confidence = "medium" if performance.get("basis") == "prior" else "high"
    else:
        base = {"QB": 8.0, "RB": 3.0, "WR": 3.0, "TE": 2.5}.get(position, 2.0)
        multiplier = {"QB": 1.15, "RB": 1.0, "WR": 1.0, "TE": 0.95}.get(position, 0.8)
        projected = base + min(market_value, 10000) / 1000 * multiplier
        basis = "Dynasty market-value proxy; no NFL performance sample"
        confidence = "low"

    weekly_points = sorted(
        value
        for row in (performance.get("weekly") or [])
        if isinstance(row, dict)
        for value in [number(row.get("fantasy_points_715"))]
        if value is not None
    )
    if len(weekly_points) >= 4:
        floor = weekly_points[max(0, round((len(weekly_points) - 1) * 0.25))]
        ceiling = weekly_points[min(len(weekly_points) - 1, round((len(weekly_points) - 1) * 0.75))]
    else:
        floor = projected * (0.72 if confidence == "low" else 0.8)
        ceiling = projected * (1.28 if confidence == "low" else 1.2)

    context = player.get("context") or {}
    current_context_evidence = any(
        signal.get("origin") == "curated_report" and abs(number(signal.get("weighted_score")) or 0) >= 0.2
        for signal in context.get("signals") or []
    )
    context_multiplier = number(context.get("weekly_multiplier"))
    baseline = projected
    if context_multiplier is not None:
        projected *= context_multiplier
        floor *= context_multiplier
        ceiling *= context_multiplier
        if abs(context_multiplier - 1) >= 0.005:
            basis += f"; current context multiplier {context_multiplier:.3f} applied"
    else:
        injury_status = str(player.get("injury_status") or "").lower()
        if injury_status in {"out", "ir", "pup", "doubtful"}:
            projected *= 0.4
            floor *= 0.3
            ceiling *= 0.5
            basis += "; availability penalty applied"
        elif injury_status == "questionable":
            projected *= 0.9
            floor *= 0.8
            ceiling *= 0.9
            basis += "; questionable-status penalty applied"

    floor = min(floor, projected)
    ceiling = max(ceiling, projected)

    rounded_points = round(max(projected, 0), 2)
    rounded_floor = min(round(max(floor, 0), 1), rounded_points)
    rounded_ceiling = max(round(max(ceiling, 0), 1), rounded_points)
    return {
        "points": rounded_points,
        "floor": rounded_floor,
        "ceiling": rounded_ceiling,
        "basis": basis,
        "confidence": confidence,
        "model_type": "evidence_estimate",
        "baseline_points": round(max(baseline, 0), 2),
        "context_multiplier": context_multiplier if context_multiplier is not None else 1.0,
        "context_adjustment_points": round(projected - baseline, 2),
        "performance_basis": performance.get("basis"),
        "current_decision_evidence": performance.get("basis") == "current" or current_context_evidence,
    }


def normalized_research(raw: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    candidates = raw.get("players", raw)
    if isinstance(candidates, dict):
        rows = [
            ({**value, "player_id": value.get("player_id") or key} if isinstance(value, dict) else value)
            for key, value in candidates.items()
        ]
    elif isinstance(candidates, list):
        rows = candidates
    else:
        rows = []
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        player_id = row.get("player_id") or row.get("sleeper_id")
        name = str(row.get("name") or "").strip().lower()
        if player_id is not None:
            indexed[str(player_id)] = row
        if name:
            indexed[f"name:{name}"] = row
    return indexed


def string_list(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("summary") or item.get("text") or item.get("note")
            if isinstance(text, str) and text.strip():
                source = item.get("source")
                result.append(f"{text.strip()} — {source}" if source else text.strip())
    return result


def research_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append({"text": item.strip(), "source": None, "url": None, "published_at": None})
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("summary") or item.get("text") or item.get("note")
        if not isinstance(text, str) or not text.strip():
            continue
        result.append({
            "text": text.strip(),
            "source": item.get("source") or item.get("author"),
            "url": item.get("url") or item.get("source_url"),
            "published_at": item.get("published_at") or item.get("fetched_at"),
            "event_date": item.get("event_date"),
        })
    return result


def player_decision_lenses(player: dict[str, Any], projection: dict[str, Any]) -> dict[str, Any]:
    performance = player.get("performance") or {}
    market_value = int(number(player.get("market_value")) or 0)
    age = number(player.get("age"))
    depth = number(player.get("depth_chart_order"))
    injury = player.get("injury_status")
    starter = bool(player.get("starter"))

    weekly_label = "Starter" if starter else "Depth"
    if projection.get("confidence") == "low":
        weekly_label = "Unproven"
    if injury:
        weekly_label = "Availability watch"
    weekly_summary = (
        f"Evidence range {projection.get('floor')}–{projection.get('ceiling')} with "
        f"{projection.get('confidence')} confidence; current matchup research is unavailable."
    )

    if performance:
        ros_label = "Role supported" if (number(performance.get("offense_snap_pct")) or 0) >= 60 else "Role sensitive"
        ros_summary = (
            f"The {performance.get('basis_label') or 'available'} sample shows "
            f"{performance.get('opportunities_per_game') or '—'} opportunities/game and "
            f"{performance.get('offense_snap_pct') or '—'}% snaps."
        )
    else:
        ros_label = "Insufficient evidence"
        ros_summary = "No matched NFL performance sample is available; role must be verified before relying on weekly utility."

    if market_value >= 7000:
        dynasty_label = "Foundation asset"
    elif market_value >= 5000:
        dynasty_label = "Strong hold"
    elif age is not None and age <= 24:
        dynasty_label = "Development hold"
    elif age is not None and age >= 30:
        dynasty_label = "Market-sensitive veteran"
    else:
        dynasty_label = "Flexible depth asset"
    dynasty_summary = (
        f"Market value {market_value:,} and position rank #{player.get('market_position_rank') or '—'}; "
        f"age {player.get('age') or '—'} shapes the liquidity and time-horizon risk."
    )

    if injury:
        stance = "Monitor availability"
    elif starter and projection.get("confidence") != "low":
        stance = "Start / hold"
    elif age is not None and age <= 24 and (depth is None or depth <= 2):
        stance = "Hold for upside"
    elif age is not None and age >= 30 and not starter:
        stance = "Shop if value holds"
    else:
        stance = "Hold / monitor role"

    return {
        "weekly": {"label": weekly_label, "summary": weekly_summary},
        "rest_of_season": {"label": ros_label, "summary": ros_summary},
        "dynasty": {"label": dynasty_label, "summary": dynasty_summary},
        "recommended_stance": stance,
    }


def speculative_outlook(player: dict[str, Any]) -> dict[str, str]:
    age = number(player.get("age"))
    depth = number(player.get("depth_chart_order"))
    value = int(number(player.get("market_value")) or 0)
    injury = player.get("injury_status")

    if injury:
        return {
            "label": "Monitor",
            "summary": f"Availability is the immediate swing factor ({injury}); recheck status before lineup lock.",
        }
    if age is not None and age <= 24 and (depth is None or depth <= 2) and value >= 4000:
        return {
            "label": "Ascending",
            "summary": "Youth, role and market support create a credible path to added dynasty value.",
        }
    if age is not None and age <= 24:
        return {
            "label": "Developmental",
            "summary": "Long-term upside remains, but role confirmation is needed before treating the player as a weekly starter.",
        }
    if age is not None and age >= 30:
        return {
            "label": "Volatile",
            "summary": "Near-term production can still help, while age increases the risk of a fast market-value decline.",
        }
    if value >= 5000:
        return {
            "label": "Stable",
            "summary": "Current market and role indicators support a dependable hold unless a clear tier-up is available.",
        }
    return {
        "label": "Speculative",
        "summary": "Depth-chart movement, usage growth or a market catalyst is needed for a meaningful value jump.",
    }


def trend_summary(performance: dict[str, Any]) -> tuple[str, float | None, float | None]:
    season_ppg = number(performance.get("ppg_715"))
    recent_ppg = number(performance.get("last3_ppg_715"))
    season_opp = number(performance.get("opportunities_per_game"))
    recent_opp = number(performance.get("last3_opportunities_per_game"))
    ppg_delta = round(recent_ppg - season_ppg, 2) if season_ppg is not None and recent_ppg is not None else None
    opp_delta = round(recent_opp - season_opp, 2) if season_opp is not None and recent_opp is not None else None
    if ppg_delta is None:
        summary = "No comparable recent NFL production sample is available."
    elif ppg_delta >= 1.5:
        summary = "Recent fantasy production is running above the broader sample."
    elif ppg_delta <= -1.5:
        summary = "Recent fantasy production is running below the broader sample."
    else:
        summary = "Recent fantasy production is broadly stable against the broader sample."
    return summary, ppg_delta, opp_delta


def compact_history_player(player: dict[str, Any], position_rank: int) -> dict[str, Any]:
    tier = tier_for_value(player.get("market_value"))
    return {
        "player_id": str(player.get("player_id")),
        "name": player.get("name"),
        "position": player.get("position"),
        "market_value": int(number(player.get("market_value")) or 0),
        "tier": tier["number"],
        "tier_label": tier["label"],
        "position_rank": position_rank,
    }


def history_snapshot(
    report_key: str,
    generated_at: str,
    season: str,
    week: int | None,
    players: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    for position in POSITIONS:
        position_players = sorted(
            [p for p in players if p.get("position") == position],
            key=lambda p: (-int(number(p.get("market_value")) or 0), p.get("name") or ""),
        )
        rows.extend(compact_history_player(player, rank) for rank, player in enumerate(position_players, 1))
    return {
        "report_key": report_key,
        "generated_at": generated_at,
        "season": season,
        "week": week,
        "players": rows,
    }


def seed_history_from_intelligence(
    root: Path,
    players: list[dict[str, Any]],
    current_date: str,
    season: str,
) -> dict[str, Any] | None:
    generic = read_json(root / "data" / "derived" / "intelligence_history.json", {}) or {}
    candidates = [entry for entry in (generic.get("entries") or []) if (entry.get("date") or "") < current_date]
    if not candidates:
        return None
    previous = candidates[-1]
    values = previous.get("player_market_values") or {}
    seeded_players = [{**p, "market_value": values.get(str(p.get("player_id")), p.get("market_value"))} for p in players]
    return history_snapshot(
        f"legacy-{previous.get('date')}",
        previous.get("generated_at") or f"{previous.get('date')}T00:00:00+00:00",
        season,
        None,
        seeded_players,
    )


def movement_for(
    player: dict[str, Any],
    current_rank: int,
    previous_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    player_id = str(player.get("player_id"))
    previous = previous_by_id.get(player_id)
    current_tier = tier_for_value(player.get("market_value"))
    if not previous:
        return {
            "has_previous": False,
            "value_change": None,
            "position_rank_change": None,
            "tier_from": None,
            "tier_to": current_tier["number"],
            "tier_changed": False,
        }
    previous_value = int(number(previous.get("market_value")) or 0)
    current_value = int(number(player.get("market_value")) or 0)
    previous_rank = int(number(previous.get("position_rank")) or current_rank)
    previous_tier = int(number(previous.get("tier")) or current_tier["number"])
    return {
        "has_previous": True,
        "value_change": current_value - previous_value,
        "position_rank_change": previous_rank - current_rank,
        "tier_from": previous_tier,
        "tier_to": current_tier["number"],
        "tier_changed": previous_tier != current_tier["number"],
    }


def player_card(
    player: dict[str, Any],
    position_rank: int,
    previous_by_id: dict[str, dict[str, Any]],
    research: dict[str, Any],
) -> dict[str, Any]:
    performance = player.get("performance") or {}
    context = player.get("context") or {}
    projection = projection_for(player)
    decision_lenses = player_decision_lenses(player, projection)
    tier = tier_for_value(player.get("market_value"))
    movement = movement_for(player, position_rank, previous_by_id)
    summary, ppg_delta, opportunity_delta = trend_summary(performance)
    research_row = research.get(str(player.get("player_id"))) or research.get(
        f"name:{str(player.get('name') or '').strip().lower()}",
        {},
    )
    outlook = speculative_outlook(player)
    if isinstance(research_row.get("speculative_outlook"), str):
        outlook["summary"] = research_row["speculative_outlook"]

    evidence = string_list(research_row.get("key_evidence"))
    if player.get("market_value"):
        evidence.append(
            f"Dynasty Dealer value {int(number(player.get('market_value')) or 0):,}; "
            f"position rank #{player.get('market_position_rank') or '—'}."
        )
    if performance:
        evidence.append(
            f"{performance.get('basis_label') or 'Available'} sample: {performance.get('ppg_715') or '—'} PPG, "
            f"{performance.get('opportunities_per_game') or '—'} opportunities/game, "
            f"{performance.get('offense_snap_pct') or '—'}% snaps."
        )
    else:
        evidence.append("No nflverse performance sample is currently matched to this player.")
    if player.get("depth_chart_order"):
        evidence.append(f"Sleeper depth-chart order: {player.get('depth_chart_order')}.")
    if player.get("injury_status"):
        injury_detail = f" ({player.get('injury_body_part')})" if player.get("injury_body_part") else ""
        evidence.append(
            f"Sleeper availability: {player.get('injury_status')}{injury_detail}."
        )

    news = research_items(research_row.get("news"))
    coach_reports = research_items(
        research_row.get("coach_reports")
        or research_row.get("coach_beat_reporter")
        or research_row.get("beat_reporter_notes")
    )
    for signal in context.get("signals") or []:
        item = {
            "text": signal.get("summary"),
            "source": signal.get("source"),
            "url": signal.get("url"),
            "published_at": signal.get("published_at"),
            "event_date": signal.get("event_date"),
            "signal_type": signal.get("type"),
            "weighted_score": signal.get("weighted_score"),
        }
        if signal.get("type") in {"coach_statement", "beat_report"}:
            coach_reports.append(item)
        elif signal.get("origin") == "curated_report" or signal.get("type") in {"injury", "practice", "inactive"}:
            news.append(item)
    app_comparisons = [
        {
            "source": "Sleeper",
            "label": "Role",
            "value": f"Depth {player.get('depth_chart_order') or '—'} · {player.get('team') or 'NFL FA'}",
        },
        {
            "source": "Dynasty Dealer",
            "label": "Market",
            "value": f"{int(number(player.get('market_value')) or 0):,} · #{player.get('market_position_rank') or '—'} {player.get('position') or ''}",
        },
        {
            "source": "nflverse",
            "label": "Production",
            "value": (
                f"{performance.get('ppg_715')} PPG · {performance.get('opportunities_per_game')} opp/g"
                if performance else "No matched sample"
            ),
        },
    ]
    takeaways = string_list(research_row.get("notable_takeaways"))
    if player.get("starter"):
        takeaways.append("Currently selected in the Sleeper starting lineup.")
    if projection["confidence"] == "low":
        takeaways.append("Treat the lineup projection as low confidence until real usage data is available.")
    if movement.get("value_change"):
        direction = "gained" if movement["value_change"] > 0 else "lost"
        takeaways.append(f"Market value {direction} {abs(movement['value_change']):,} since the previous report.")

    risks = string_list(research_row.get("risk_factors"))
    catalysts = string_list(research_row.get("catalysts"))
    age = number(player.get("age"))
    depth = number(player.get("depth_chart_order"))
    snaps = number(performance.get("offense_snap_pct"))
    if player.get("injury_status"):
        risks.append(f"Current {player.get('injury_status')} designation creates availability risk.")
    if age is not None and age >= 30:
        risks.append("Age increases role-loss and market-liquidity risk.")
    if depth is not None and depth >= 3:
        risks.append("The current depth-chart path requires movement ahead of the player.")
    if not performance:
        risks.append("No matched NFL performance sample supports the current weekly estimate.")
    elif snaps is not None and snaps < 40:
        risks.append(f"A {snaps}% snap rate limits the demonstrated weekly floor.")
    if age is not None and age <= 24:
        catalysts.append("Youth leaves room for role growth and market appreciation.")
    if depth is not None and depth <= 2:
        catalysts.append("A top-two depth-chart position creates a direct path to added opportunity.")
    if opportunity_delta is not None and opportunity_delta >= 2:
        catalysts.append(f"Recent opportunity is up {opportunity_delta} per game against the broader sample.")
    if movement.get("value_change") and movement["value_change"] > 0:
        catalysts.append(f"Market value increased {movement['value_change']:,} since the previous report.")

    return {
        "player_id": str(player.get("player_id")),
        "name": player.get("name"),
        "position": player.get("position"),
        "team": player.get("team"),
        "age": player.get("age"),
        "status": player.get("status"),
        "injury_status": player.get("injury_status"),
        "injury_body_part": player.get("injury_body_part"),
        "depth_chart_order": player.get("depth_chart_order"),
        "current_starter": bool(player.get("starter")),
        "position_rank_on_roster": position_rank,
        "tier": tier,
        "current_fantasy_value": {
            "market_value": int(number(player.get("market_value")) or 0),
            "market_rank": player.get("market_rank"),
            "market_position_rank": player.get("market_position_rank"),
            "projection": projection,
        },
        "speculative_outlook": outlook,
        "decision_lenses": decision_lenses,
        "key_evidence": evidence[:8],
        "trends": {
            "summary": summary,
            "ppg_delta": ppg_delta,
            "opportunity_delta": opportunity_delta,
            "season_ppg": performance.get("ppg_715"),
            "recent_ppg": performance.get("last3_ppg_715"),
            "season_opportunities_per_game": performance.get("opportunities_per_game"),
            "recent_opportunities_per_game": performance.get("last3_opportunities_per_game"),
        },
        "news": news,
        "coach_beat_reporter_information": coach_reports,
        "app_data_comparisons": app_comparisons,
        "notable_takeaways": takeaways[:6],
        "risk_factors": risks[:5],
        "catalysts": catalysts[:5],
        "context": {
            "net_direction": context.get("net_direction", "neutral"),
            "weekly_multiplier": context.get("weekly_multiplier", 1.0),
            "availability_probability": context.get("availability_probability", 1.0),
            "confidence": context.get("confidence", "low"),
            "signal_count": context.get("signal_count", 0),
            "signals": context.get("signals") or [],
        },
        "recommended_stance": decision_lenses["recommended_stance"],
        "movement": movement,
        "research_coverage": {
            "news": bool(news),
            "coach_beat_reporter": bool(coach_reports),
        },
    }


def eligible(slot: str, position: str | None) -> bool:
    if slot == "FLEX":
        return position in FLEX_POSITIONS
    if slot == "SUPER_FLEX":
        return position in SUPER_FLEX_POSITIONS
    return position == slot


def slot_labels(slots: list[str]) -> list[str]:
    totals = {slot: slots.count(slot) for slot in set(slots)}
    seen: dict[str, int] = {}
    labels = []
    for slot in slots:
        seen[slot] = seen.get(slot, 0) + 1
        display = "SUPERFLEX" if slot == "SUPER_FLEX" else slot
        labels.append(f"{display}{seen[slot]}" if totals[slot] > 1 else display)
    return labels


def optimize_lineup(players: list[dict[str, Any]], slots: list[str]) -> list[dict[str, Any]]:
    projections = {str(p.get("player_id")): projection_for(p) for p in players}
    flexible_indices = [i for i, slot in enumerate(slots) if slot in {"FLEX", "SUPER_FLEX"}]
    fixed_indices = [i for i, slot in enumerate(slots) if i not in flexible_indices]
    flexible_candidates = [
        [p for p in players if eligible(slots[index], p.get("position"))]
        for index in flexible_indices
    ]
    combinations = itertools.product(*flexible_candidates) if flexible_candidates else [tuple()]
    best: list[dict[str, Any] | None] | None = None
    best_score = -1.0

    for flexible_players in combinations:
        flexible_ids = [str(p.get("player_id")) for p in flexible_players]
        if len(set(flexible_ids)) != len(flexible_ids):
            continue
        chosen: list[dict[str, Any] | None] = [None] * len(slots)
        used = set(flexible_ids)
        for index, player in zip(flexible_indices, flexible_players):
            chosen[index] = player
        valid = True
        for index in fixed_indices:
            candidates = [
                p for p in players
                if str(p.get("player_id")) not in used and eligible(slots[index], p.get("position"))
            ]
            if not candidates:
                valid = False
                break
            player = max(
                candidates,
                key=lambda p: (projections[str(p.get("player_id"))]["points"], int(number(p.get("market_value")) or 0)),
            )
            chosen[index] = player
            used.add(str(player.get("player_id")))
        if not valid:
            continue
        score = sum(projections[str(p.get("player_id"))]["points"] for p in chosen if p)
        if score > best_score:
            best, best_score = chosen, score

    labels = slot_labels(slots)
    return [
        {
            "slot": slots[index],
            "slot_label": labels[index],
            "player_id": str(player.get("player_id")) if player else None,
            "name": player.get("name") if player else "Open slot",
            "position": player.get("position") if player else None,
            "team": player.get("team") if player else None,
            "injury_status": player.get("injury_status") if player else None,
            "projected_points": projections[str(player.get("player_id"))]["points"] if player else 0,
            "projected_floor": projections[str(player.get("player_id"))]["floor"] if player else 0,
            "projected_ceiling": projections[str(player.get("player_id"))]["ceiling"] if player else 0,
            "projection_basis": projections[str(player.get("player_id"))]["basis"] if player else "No eligible player",
            "confidence": projections[str(player.get("player_id"))]["confidence"] if player else "low",
            "current_decision_evidence": projections[str(player.get("player_id"))]["current_decision_evidence"] if player else False,
        }
        for index, player in enumerate(best or [None] * len(slots))
    ]


def current_lineup(team: dict[str, Any], players_by_id: dict[str, dict[str, Any]], slots: list[str]) -> list[dict[str, Any]]:
    lineup = team.get("lineup") or []
    starters = []
    for starter in team.get("starters") or []:
        player_id = starter.get("player_id") if isinstance(starter, dict) else starter
        if player_id is not None and str(player_id) != "0":
            starters.append(str(player_id))
    labels = slot_labels(slots)
    rows = []
    for index, slot in enumerate(slots):
        lineup_row = lineup[index] if index < len(lineup) else {}
        player_id = str(lineup_row.get("player_id")) if lineup_row.get("player_id") else (
            starters[index] if index < len(starters) and starters[index] != "0" else None
        )
        player = players_by_id.get(player_id or "", {})
        projection = projection_for(player) if player else {
            "points": 0, "floor": 0, "ceiling": 0, "basis": "Open slot", "confidence": "low"
        }
        rows.append({
            "slot": slot,
            "slot_label": lineup_row.get("slot_label") or labels[index],
            "player_id": player_id,
            "name": player.get("name") or "Open slot",
            "position": player.get("position"),
            "team": player.get("team"),
            "injury_status": player.get("injury_status"),
            "projected_points": projection["points"],
            "projected_floor": projection["floor"],
            "projected_ceiling": projection["ceiling"],
            "projection_basis": projection["basis"],
            "confidence": projection["confidence"],
            "current_decision_evidence": projection.get("current_decision_evidence", False),
        })
    return rows


def lineup_bundle(team: dict[str, Any], players: list[dict[str, Any]], slots: list[str]) -> dict[str, Any]:
    players_by_id = {str(p.get("player_id")): p for p in players}
    current = current_lineup(team, players_by_id, slots)
    optimized = optimize_lineup(players, slots)
    current_ids = {row.get("player_id") for row in current if row.get("player_id")}
    optimized_ids = {row.get("player_id") for row in optimized if row.get("player_id")}
    incoming = [row for row in optimized if row.get("player_id") not in current_ids]
    outgoing = [row for row in current if row.get("player_id") not in optimized_ids]
    incoming.sort(key=lambda row: -float(row.get("projected_points") or 0))
    outgoing.sort(key=lambda row: float(row.get("projected_points") or 0))
    changes = []
    for add, remove in itertools.zip_longest(incoming, outgoing, fillvalue={}):
        advantage = round(float(add.get("projected_points") or 0) - float(remove.get("projected_points") or 0), 2)
        if add.get("injury_status"):
            decision = "hold_current"
            decision_reason = f"Do not make the swap without clearing {add.get('name')}'s {add.get('injury_status')} status."
        elif advantage < 2:
            decision = "hold_current"
            decision_reason = "The modeled edge is below the two-point change threshold; keep the submitted starter."
        elif not add.get("current_decision_evidence"):
            decision = "research_required"
            decision_reason = "The model prefers this swap, but the incoming player's case relies on prior-season or proxy evidence and is not actionable without current confirmation."
        elif advantage < 3:
            decision = "lean"
            decision_reason = "This is a close call; matchup and late news should decide it."
        else:
            decision = "consider"
            decision_reason = "The evidence gap is large enough to merit a lineup change after final availability checks."
        changes.append({
            "start": add.get("name"),
            "sit": remove.get("name"),
            "projected_advantage": advantage,
            "decision": decision,
            "decision_reason": decision_reason,
            "start_confidence": add.get("confidence"),
            "sit_confidence": remove.get("confidence"),
            "current_decision_evidence": bool(add.get("current_decision_evidence")),
            "explanation": (
                f"{add.get('name') or 'The replacement'} carries the stronger evidence projection "
                f"({add.get('projected_points') or 0} vs {remove.get('projected_points') or 0})."
            ),
        })
    current_total = round(sum(float(row.get("projected_points") or 0) for row in current), 2)
    optimized_total = round(sum(float(row.get("projected_points") or 0) for row in optimized), 2)
    actionable_advantage = round(sum(
        float(change.get("projected_advantage") or 0)
        for change in changes
        if change.get("decision") == "consider"
    ), 2)
    return {
        "status": "provisional",
        "methodology": "The unconstrained lineup maximizes the evidence estimate, but the action board requires a two-point edge plus current-season usage or verified current reporting before recommending a change. Dynasty tier and market movement are not weekly-start scores. This is decision support, not a sportsbook projection.",
        "decision_thresholds": {
            "hold_current_below": 2,
            "close_call_below": 3,
            "availability_guardrail": True,
            "current_evidence_required": True,
        },
        "current": current,
        "optimized": optimized,
        "current_projected_points": current_total,
        "optimized_projected_points": optimized_total,
        "projected_advantage": round(optimized_total - current_total, 2),
        "actionable_projected_advantage": actionable_advantage,
        "changes": changes,
    }


def action_board(
    lineup: dict[str, Any],
    players: list[dict[str, Any]],
    opportunities: list[dict[str, Any]],
    research_available: bool,
) -> list[dict[str, Any]]:
    actions = []
    for change in lineup.get("changes") or []:
        if not change.get("start") or not change.get("sit"):
            continue
        if change.get("decision") == "hold_current":
            continue
        advantage = float(change.get("projected_advantage") or 0)
        needs_research = change.get("decision") == "research_required"
        is_close = change.get("decision") == "lean"
        priority = 5 if needs_research else 4 if is_close else max(6, min(8, round(6 + max(advantage, 0) / 4)))
        if not research_available:
            priority = min(priority, 7)
        actions.append({
            "priority": priority,
            "category": "Lineup",
            "title": (
                f"Research {change['start']} vs {change['sit']}"
                if needs_research else
                f"Recheck {change['start']} vs {change['sit']}"
                if is_close else f"Consider {change['start']} over {change['sit']}"
            ),
            "recommendation": (
                "Keep the submitted starter unless current role, matchup and availability evidence confirms the model preference."
                if needs_research else
                "Use matchup and late-news confirmation as the tiebreaker; keeping the submitted starter is reasonable."
                if is_close else
                "Treat this as provisional until current matchup, injury and inactive information is verified."
            ),
            "rationale": f"{change.get('explanation')} {change.get('decision_reason')}",
            "projected_advantage": advantage,
            "upside": f"The evidence model adds approximately {advantage:.1f} points if its role assumptions hold.",
            "risk": "The report does not yet contain verified current matchup or beat-report context.",
            "cost_or_cut": f"Bench {change['sit']}; no roster transaction required.",
            "urgency": "Before lineup lock",
            "confidence": "low" if not research_available or "low" in {
                change.get("start_confidence"), change.get("sit_confidence")
            } else "medium",
        })

    for player in players:
        if not player.get("injury_status"):
            continue
        severe = str(player.get("injury_status")).lower() in {"out", "ir", "doubtful"}
        starter = bool(player.get("starter"))
        actions.append({
            "priority": 9 if severe and starter else 7 if starter else 5,
            "category": "Availability",
            "title": f"Verify {player.get('name')} before lock",
            "recommendation": "Confirm the official game designation and keep a legal pivot available.",
            "rationale": f"Sleeper lists {player.get('name')} as {player.get('injury_status')}; no verified news item is attached.",
            "projected_advantage": None,
            "upside": "A prepared pivot protects the lineup from a zero or limited role.",
            "risk": "Sleeper status alone does not establish expected availability or workload.",
            "cost_or_cut": "No transaction required unless the final designation changes roster-slot options.",
            "urgency": "Before lineup lock",
            "confidence": "medium",
        })

    bench = sorted(
        [p for p in players if not p.get("starter")],
        key=lambda p: (int(number(p.get("market_value")) or 0), projection_for(p)["points"]),
    )
    used_drop_ids: set[str] = set()
    for candidate in opportunities[:20]:
        position = candidate.get("position")
        drop = next(
            (
                player for player in bench
                if player.get("position") == position and str(player.get("player_id")) not in used_drop_ids
            ),
            None,
        )
        if not drop:
            continue
        priority = max(3, min(6, round(float(candidate.get("opportunity_score") or 0) / 18)))
        if not research_available:
            priority = min(priority, 5)
        candidate_value = int(number(candidate.get("market_value")) or 0)
        drop_value = int(number(drop.get("market_value")) or 0)
        if candidate_value <= drop_value and float(candidate.get("opportunity_score") or 0) < 80:
            continue
        used_drop_ids.add(str(drop.get("player_id")))
        actions.append({
            "priority": priority,
            "category": "Waiver review",
            "title": f"Compare {candidate.get('name')} with {drop.get('name')}",
            "recommendation": "Do not submit the move until role, current news and roster fit are verified.",
            "rationale": " ".join((candidate.get("reasons") or [])[:2]) or "The app opportunity score flags a possible roster upgrade.",
            "projected_advantage": None,
            "upside": f"Candidate market value {candidate_value:,} versus {drop_value:,} for the likely cut.",
            "risk": "Opportunity score is a discovery signal, not proof of future touches or trade value.",
            "cost_or_cut": f"Likely cut: {drop.get('name')}; verify lineup, taxi and IR constraints first.",
            "urgency": "Monitor waiver window",
            "confidence": "low" if not research_available else "medium",
            "verified_available": True,
        })
        if len(used_drop_ids) >= 2:
            break

    if not research_available:
        actions.append({
            "priority": 7,
            "category": "Data check",
            "title": "Refresh news and matchup context before acting",
            "recommendation": "Add verified player news and coach/beat-reporter notes before acting on low-confidence decisions.",
            "rationale": "No structured roster-intelligence research file was available for this report.",
            "projected_advantage": None,
            "upside": "A current evidence pass can confirm, reverse or suppress tentative lineup and waiver calls.",
            "risk": "Acting now would rely mostly on prior-season usage, market values and Sleeper status fields.",
            "cost_or_cut": "No roster cost; information-gathering step.",
            "urgency": "Before any Week 1 transaction or lineup change",
            "confidence": "high",
        })

    actions.sort(key=lambda action: (-int(action.get("priority") or 0), action.get("title") or ""))
    return actions[:10]


def validate_report(
    report: dict[str, Any],
    history: dict[str, Any],
    expected_player_ids: set[str],
) -> None:
    cards = [
        player
        for board in report.get("position_boards") or []
        for tier in board.get("tiers") or []
        for player in tier.get("players") or []
    ]
    card_ids = [str(player.get("player_id")) for player in cards]
    errors = []
    if report.get("schema_version") != SCHEMA_VERSION:
        errors.append("unexpected schema version")
    if set(card_ids) != expected_player_ids or len(card_ids) != len(set(card_ids)):
        errors.append("tier boards must contain every roster player exactly once")
    optimized = (report.get("lineup") or {}).get("optimized") or []
    optimized_ids = [str(row.get("player_id")) for row in optimized if row.get("player_id")]
    if len(optimized_ids) != len(set(optimized_ids)):
        errors.append("optimized lineup contains a duplicate player")
    for row in optimized:
        if row.get("player_id") and not eligible(str(row.get("slot")), row.get("position")):
            errors.append(f"illegal optimized lineup slot for {row.get('name')}")
    if any(not 1 <= int(action.get("priority") or 0) <= 10 for action in report.get("action_board") or []):
        errors.append("action priorities must be between 1 and 10")
    if not isinstance(history.get("entries"), list):
        errors.append("history entries must be a list")
    if errors:
        raise RuntimeError("Invalid roster intelligence report: " + "; ".join(errors))


def build_roster_intelligence_outputs(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    derived = root / "data" / "derived"
    current = root / "data" / "current"
    external = root / "data" / "external"
    team_assets = read_json(derived / "team_assets.json", {}) or {}
    league = read_json(current / "league.json", {}) or {}
    nfl_state = read_json(current / "nfl_state.json", {}) or {}
    opportunities = read_json(derived / "opportunity_scanner.json", {}) or {}
    player_intel = read_json(derived / "player_intel.json", {}) or {}
    data_health = read_json(derived / "data_health.json", {}) or {}
    player_context = read_json(derived / "player_context_signals.json", {}) or {}
    context_by_id = player_context.get("players_by_id") or {}
    team = team_assets.get(MY_ROSTER_ID) or {}
    players = [
        {**p, "context": context_by_id.get(str(p.get("player_id")), {})}
        for p in (team.get("players") or [])
        if p.get("position") in POSITIONS
    ]
    if not team or not players:
        raise RuntimeError("Roster intelligence requires roster 3 in team_assets.json")

    research_raw = read_json(external / "roster_intelligence_research.json", {}) or {}
    research = normalized_research(research_raw)
    now = datetime.now(timezone.utc)
    generated_at = now.isoformat()
    date_key = now.date().isoformat()
    season = str(league.get("season") or nfl_state.get("season") or "")
    week_value = nfl_state.get("week") or nfl_state.get("display_week")
    week = int(week_value) if isinstance(week_value, (int, float)) else None
    report_key = f"{season}-W{week or 0}-{date_key}"

    history_path = derived / "roster_intelligence_history.json"
    history = read_json(history_path, {}) or {}
    entries = [entry for entry in (history.get("entries") or []) if entry.get("report_key") != report_key]
    if not entries:
        seeded = seed_history_from_intelligence(root, players, date_key, season)
        if seeded:
            entries.append(seeded)
    previous = entries[-1] if entries else None
    previous_by_id = {
        str(player.get("player_id")): player
        for player in ((previous or {}).get("players") or [])
    }

    position_boards = []
    all_cards = []
    for position in POSITIONS:
        position_players = sorted(
            [p for p in players if p.get("position") == position],
            key=lambda p: (-int(number(p.get("market_value")) or 0), p.get("name") or ""),
        )
        cards = [
            player_card(player, rank, previous_by_id, research)
            for rank, player in enumerate(position_players, 1)
        ]
        all_cards.extend(cards)
        position_boards.append({
            "position": position,
            "player_count": len(cards),
            "tiers": [
                {
                    "number": tier_number,
                    "label": tier_for_value({1: 7000, 2: 5000, 3: 3000, 4: 0}[tier_number])["label"],
                    "players": [card for card in cards if card["tier"]["number"] == tier_number],
                }
                for tier_number in range(1, 5)
                if any(card["tier"]["number"] == tier_number for card in cards)
            ],
        })

    starter_slots = [slot for slot in (league.get("roster_positions") or []) if slot != "BN"]
    lineup = lineup_bundle(team, players, starter_slots)
    curated_context_count = int((player_context.get("coverage") or {}).get("curated_reports") or 0)
    roster_curated_context_count = sum(
        1
        for player in players
        for signal in (player.get("context") or {}).get("signals") or []
        if signal.get("origin") == "curated_report"
    )
    contextual_research_available = bool(research) or roster_curated_context_count > 0
    actions = action_board(
        lineup,
        players,
        opportunities.get("players") or [],
        contextual_research_available,
    )
    movement = [
        {
            "player_id": card["player_id"],
            "name": card["name"],
            "position": card["position"],
            **card["movement"],
        }
        for card in all_cards
    ]
    movement.sort(
        key=lambda row: (
            -abs(int(number(row.get("value_change")) or 0)),
            row.get("name") or "",
        )
    )

    performance_bases = sorted({
        str((player.get("performance") or {}).get("basis_label"))
        for player in players
        if (player.get("performance") or {}).get("basis_label")
    })
    market_source = player_intel.get("market_source") or {}
    performance_source = player_intel.get("performance_source") or {}
    research_status = str(research_raw.get("status") or ("available" if research else "not_available"))
    roster_contexts = [player.get("context") or {} for player in players]
    roster_context_signal_count = sum(int(context.get("signal_count") or 0) for context in roster_contexts)
    current_performance_count = sum(
        1 for player in players if (player.get("performance") or {}).get("basis") == "current"
    )
    data_confidence = "decision_ready" if contextual_research_available and current_performance_count else "provisional"

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "report_key": report_key,
        "season": season,
        "week": week,
        "roster": {
            "roster_id": team.get("roster_id"),
            "manager": team.get("manager"),
            "team_name": team.get("team_name"),
            "player_count": len(players),
        },
        "coverage": {
            "roster_players": len(players),
            "market_values": sum(1 for p in players if p.get("market_value")),
            "performance_samples": sum(1 for p in players if p.get("performance")),
            "news_players": sum(1 for card in all_cards if card["research_coverage"]["news"]),
            "coach_beat_reporter_players": sum(
                1 for card in all_cards if card["research_coverage"]["coach_beat_reporter"]
            ),
            "current_season_performance_samples": current_performance_count,
            "research_status": research_status,
            "context_signal_players": sum(1 for context in roster_contexts if context.get("signal_count")),
            "objective_context_signals": roster_context_signal_count - roster_curated_context_count,
            "curated_context_reports": roster_curated_context_count,
        },
        "data_confidence": {
            "status": data_confidence,
            "label": "Decision ready" if data_confidence == "decision_ready" else "Provisional",
            "reasons": [
                reason for reason in [
                    None if contextual_research_available else "Verified news, matchup and coach/beat-reporter research is not attached.",
                    None if current_performance_count else "NFL performance inputs are prior-season samples or market proxies.",
                    "Sleeper roster, lineup and availability fields are present."
                    if (data_health.get("sleeper") or {}).get("status") == "ok" else
                    "Sleeper data health is not confirmed.",
                ] if reason
            ],
        },
        "freshness": {
            "sleeper_data_checked_at": data_health.get("generated_at"),
            "market_provider_timestamp": market_source.get("provider_timestamp"),
            "external_sync_generated_at": (player_intel.get("external_status") or {}).get("generated_at"),
            "research_generated_at": research_raw.get("generated_at"),
            "player_context_generated_at": player_context.get("generated_at"),
            "performance_basis": performance_bases,
        },
        "sources": [
            {
                "name": "Sleeper",
                "type": "authoritative_roster_data",
                "status": (data_health.get("sleeper") or {}).get("status") or "unknown",
                "checked_at": data_health.get("generated_at"),
                "url": "https://sleeper.com/",
            },
            {
                "name": market_source.get("name") or "Dynasty Dealer",
                "type": "market_context",
                "status": "available" if market_source else "unavailable",
                "checked_at": market_source.get("provider_timestamp"),
                "url": market_source.get("url"),
            },
            {
                "name": performance_source.get("name") or "nflverse",
                "type": "performance_context",
                "status": "available" if performance_bases else "unavailable",
                "checked_at": (player_intel.get("external_status") or {}).get("generated_at"),
                "url": performance_source.get("url"),
                "basis": performance_bases,
            },
            {
                "name": "Player context signals",
                "type": "availability_depth_usage_and_reporting",
                "status": "available" if player_context.get("players_by_id") else "unavailable",
                "checked_at": player_context.get("generated_at"),
                "url": None,
            },
            {
                "name": "Roster research",
                "type": "news_matchup_coach_reporting",
                "status": research_status,
                "checked_at": research_raw.get("generated_at"),
                "url": research_raw.get("source_url"),
            },
        ],
        "position_boards": position_boards,
        "lineup": lineup,
        "action_board": actions,
        "movement": movement,
        "previous_report": {
            "available": previous is not None,
            "report_key": (previous or {}).get("report_key"),
            "generated_at": (previous or {}).get("generated_at"),
        },
        "source_notes": [
            "Sleeper is authoritative for roster, lineup, role and availability fields.",
            "Dynasty Dealer supplies market values; nflverse supplies 715-scored performance and usage.",
            "Player, roster-rank and tier movement is calculated from roster_intelligence_history.json.",
            "Lineup projections are evidence-weighted decision support and are not sportsbook projections.",
            "Current context adjustments are capped, time-decayed and retain their source evidence.",
            "News and coach/beat-reporter sections remain empty unless verified structured research is supplied.",
        ],
    }

    current_snapshot = history_snapshot(report_key, generated_at, season, week, players)
    entries.append(current_snapshot)
    entries.sort(key=lambda entry: entry.get("generated_at") or "")
    history_output = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "retention_reports": MAX_HISTORY_REPORTS,
        "entries": entries[-MAX_HISTORY_REPORTS:],
    }
    validate_report(report, history_output, {str(player.get("player_id")) for player in players})
    write_json(derived / "roster_intelligence.json", report)
    write_json(history_path, history_output)
    return report, history_output


if __name__ == "__main__":
    build_roster_intelligence_outputs(Path(__file__).resolve().parents[1])
