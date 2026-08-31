from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MY_ROSTER_ID = "3"
POSITIONS = ("QB", "RB", "WR", "TE")
MAX_HISTORY_DAYS = 120


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


def compact_performance(perf: dict[str, Any] | None) -> dict[str, Any] | None:
    if not perf:
        return None
    return {
        "basis": perf.get("basis"),
        "basis_label": perf.get("basis_label"),
        "games": perf.get("games"),
        "ppg_715": perf.get("ppg_715"),
        "last3_ppg_715": perf.get("last3_ppg_715"),
        "opportunities_per_game": perf.get("opportunities_per_game"),
        "last3_opportunities_per_game": perf.get("last3_opportunities_per_game"),
        "touches_per_game": perf.get("touches_per_game"),
        "targets_per_game": perf.get("targets_per_game"),
        "carries_per_game": perf.get("carries_per_game"),
        "offense_snap_pct": perf.get("offense_snap_pct"),
        "target_share": perf.get("target_share"),
        "air_yards_share": perf.get("air_yards_share"),
    }


def compact_player(player: dict[str, Any] | None) -> dict[str, Any] | None:
    if not player:
        return None
    return {
        "player_id": str(player.get("player_id")) if player.get("player_id") is not None else None,
        "name": player.get("name"),
        "position": player.get("position"),
        "team": player.get("team"),
        "age": player.get("age"),
        "starter": bool(player.get("starter")),
        "injury_status": player.get("injury_status"),
        "depth_chart_order": player.get("depth_chart_order") or player.get("depth"),
        "market_value": player.get("market_value"),
        "market_rank": player.get("market_rank"),
        "market_position_rank": player.get("market_position_rank"),
        "performance": compact_performance(player.get("performance")),
    }


def compact_opportunity(player: dict[str, Any]) -> dict[str, Any]:
    return {
        "player_id": str(player.get("player_id")),
        "name": player.get("name"),
        "position": player.get("position"),
        "team": player.get("team"),
        "age": player.get("age"),
        "depth": player.get("depth") or player.get("depth_chart_order"),
        "injury_status": player.get("injury_status"),
        "opportunity_score": player.get("opportunity_score"),
        "tier": player.get("tier"),
        "trending_adds_24h": player.get("trending_adds_24h"),
        "market_value": player.get("market_value"),
        "market_rank": player.get("market_rank"),
        "market_position_rank": player.get("market_position_rank"),
        "performance": compact_performance(player.get("performance")),
        "reasons": (player.get("reasons") or [])[:5],
    }


def current_completed_week(root: Path) -> int | None:
    power = read_json(root / "data" / "derived" / "power_rankings.json", {}) or {}
    current = (power.get("scopes") or {}).get("current") or {}
    week = current.get("latest_completed_week")
    return int(week) if isinstance(week, (int, float)) else None


def build_data_health(root: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    current = root / "data" / "current"
    external = root / "data" / "external"
    derived = root / "data" / "derived"

    required = [
        "league.json", "rosters.json", "roster_index.json", "pick_ownership.json",
        "free_agents.json", "players_active.json", "transactions.json", "matchups.json",
        "nfl_state.json",
    ]
    sleeper_files = {}
    sleeper_ok = True
    for name in required:
        path = current / name
        exists = path.exists() and path.stat().st_size > 0
        sleeper_files[name] = {
            "status": "ok" if exists else "missing",
            "bytes": path.stat().st_size if path.exists() else 0,
        }
        sleeper_ok = sleeper_ok and exists

    ext = read_json(external / "external_status.json", {}) or {}
    sources = ext.get("sources") or {}
    league = read_json(current / "league.json", {}) or {}
    season = str(league.get("season") or "")
    completed_week = current_completed_week(root)

    dealer = sources.get("dynasty_dealer") or {}
    stats = sources.get(f"nflverse_stats_{season}") or {}
    snaps = sources.get(f"nflverse_snaps_{season}") or {}

    def nfl_status(source: dict[str, Any]) -> str:
        status = source.get("status")
        if status == "ok":
            return "ok"
        if completed_week is None and status in {"unavailable", "error", None}:
            return "expected_preseason"
        return "stale_or_unavailable"

    stats_status = nfl_status(stats)
    snaps_status = nfl_status(snaps)
    intel = read_json(derived / "player_intel.json", {}) or {}
    coverage = intel.get("coverage") or {}

    warnings = []
    if not sleeper_ok:
        warnings.append("One or more authoritative Sleeper snapshot files are missing.")
    if dealer.get("status") not in {"ok", "stale"}:
        warnings.append("Dynasty Dealer market feed is unavailable and no healthy status is reported.")
    if stats_status == "stale_or_unavailable":
        warnings.append(f"nflverse {season} player stats are unavailable after current-season games have begun.")
    if snaps_status == "stale_or_unavailable":
        warnings.append(f"nflverse {season} snap counts are unavailable after current-season games have begun.")

    if not sleeper_ok:
        overall = "error"
    elif warnings:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "generated_at": now,
        "overall": overall,
        "season": season,
        "latest_completed_week": completed_week,
        "sleeper": {
            "status": "ok" if sleeper_ok else "error",
            "authoritative": True,
            "files": sleeper_files,
        },
        "derived": {
            "status": "ok",
            "generated_at": (read_json(derived / "league_summary.json", {}) or {}).get("generated_at"),
        },
        "dynasty_dealer": {
            "status": dealer.get("status") or "unknown",
            "players": dealer.get("players"),
            "external_sync_generated_at": ext.get("generated_at"),
        },
        "nflverse": {
            "current_season_stats": stats_status,
            "current_season_snaps": snaps_status,
            "stats_rows": stats.get("rows"),
            "snap_rows": snaps.get("rows"),
            "note": (
                "Current-season nflverse files are not expected before regular-season data is published. Prior-season performance remains labeled as prior."
                if stats_status == "expected_preseason" or snaps_status == "expected_preseason"
                else None
            ),
        },
        "player_intel_coverage": coverage,
        "warnings": warnings,
    }


def team_metrics(root: Path) -> list[dict[str, Any]]:
    derived = root / "data" / "derived"
    market = read_json(derived / "roster_market_values.json", {}) or {}
    power = read_json(derived / "power_rankings.json", {}) or {}
    playoffs = read_json(derived / "playoff_simulator.json", {}) or {}
    profiles = read_json(derived / "team_profiles.json", {}) or {}

    market_by = {str(x.get("roster_id")): x for x in market.get("teams") or []}
    power_by = {
        str(x.get("roster_id")): x
        for x in (((power.get("scopes") or {}).get("current") or {}).get("rankings") or [])
    }
    playoff_by = {str(x.get("roster_id")): x for x in playoffs.get("teams") or []}
    profile_by = {str(x.get("roster_id")): x for x in profiles.get("teams") or []}

    ids = sorted(set(market_by) | set(power_by) | set(playoff_by) | set(profile_by), key=lambda x: int(x))
    rows = []
    for rid in ids:
        m, p, po, pr = market_by.get(rid, {}), power_by.get(rid, {}), playoff_by.get(rid, {}), profile_by.get(rid, {})
        rows.append({
            "roster_id": int(rid),
            "manager": m.get("manager") or p.get("manager") or po.get("manager") or pr.get("manager"),
            "team_name": m.get("team_name") or p.get("team_name") or po.get("team_name") or pr.get("team_name"),
            "market_value": m.get("total_market_value"),
            "starter_market_value": m.get("optimal_starter_market_value"),
            "market_score": m.get("roster_market_score"),
            "market_rank": m.get("market_rank"),
            "power_score": p.get("power_score"),
            "power_rank": p.get("rank"),
            "playoff_odds": po.get("playoff_odds"),
            "title_odds": po.get("title_odds"),
            "model_mean": po.get("model_mean"),
            "franchise_score": pr.get("franchise_score"),
            "window": pr.get("window"),
        })
    return rows


def build_intelligence_history(root: Path) -> dict[str, Any]:
    derived = root / "data" / "derived"
    path = derived / "intelligence_history.json"
    existing = read_json(path, {}) or {}
    entries = list(existing.get("entries") or [])
    now = datetime.now(timezone.utc)
    date_key = now.date().isoformat()

    intel = read_json(derived / "player_intel.json", {}) or {}
    market_players = intel.get("players") or []
    opportunities = read_json(derived / "opportunity_scanner.json", {}) or {}
    my_team = (read_json(derived / "team_assets.json", {}) or {}).get(MY_ROSTER_ID) or {}
    my_ids = {str(p.get("player_id")) for p in my_team.get("players") or []}
    top_market_ids = {
        str(p.get("player_id"))
        for p in sorted(market_players, key=lambda x: -int(x.get("market_value") or 0))[:250]
    }
    top_opp_ids = {str(p.get("player_id")) for p in (opportunities.get("players") or [])[:75]}
    keep_ids = my_ids | top_market_ids | top_opp_ids
    player_values = {
        str(p.get("player_id")): int(p.get("market_value") or 0)
        for p in market_players
        if str(p.get("player_id")) in keep_ids and int(p.get("market_value") or 0) > 0
    }

    snapshot = {
        "date": date_key,
        "generated_at": now.isoformat(),
        "teams": team_metrics(root),
        "player_market_values": player_values,
        "market_provider_timestamp": (intel.get("market_source") or {}).get("provider_timestamp"),
    }
    entries = [x for x in entries if x.get("date") != date_key]
    entries.append(snapshot)
    entries.sort(key=lambda x: x.get("date") or "")
    entries = entries[-MAX_HISTORY_DAYS:]
    return {
        "generated_at": now.isoformat(),
        "retention_days": MAX_HISTORY_DAYS,
        "entries": entries,
    }


def build_ai_bridge(root: Path, health: dict[str, Any], history: dict[str, Any]) -> dict[str, dict[str, Any]]:
    derived = root / "data" / "derived"
    league = read_json(derived / "league_summary.json", {}) or {}
    teams = read_json(derived / "team_assets.json", {}) or {}
    needs = read_json(derived / "team_needs.json", {}) or {}
    trade_partners = read_json(derived / "trade_partners.json", {}) or {}
    opportunities = read_json(derived / "opportunity_scanner.json", {}) or {}
    market = read_json(derived / "roster_market_values.json", {}) or {}
    power = read_json(derived / "power_rankings.json", {}) or {}
    standings = read_json(derived / "standings_plus.json", {}) or {}
    draft = read_json(derived / "draft_capital_matrix.json", {}) or {}
    playoffs = read_json(derived / "playoff_simulator.json", {}) or {}
    profiles = read_json(derived / "team_profiles.json", {}) or {}
    tendencies = read_json(derived / "manager_tendencies.json", {}) or {}
    recent_tx = read_json(derived / "recent_transactions.json", []) or []
    changes = read_json(derived / "league_changes.json", {}) or {}

    my_team = teams.get(MY_ROSTER_ID) or {}
    my_market = next((x for x in market.get("teams") or [] if str(x.get("roster_id")) == MY_ROSTER_ID), None)
    my_profile = next((x for x in profiles.get("teams") or [] if str(x.get("roster_id")) == MY_ROSTER_ID), None)
    my_playoff = next((x for x in playoffs.get("teams") or [] if str(x.get("roster_id")) == MY_ROSTER_ID), None)
    my_power = next((x for x in (((power.get("scopes") or {}).get("current") or {}).get("rankings") or []) if str(x.get("roster_id")) == MY_ROSTER_ID), None)

    compact_lineup = []
    for slot in my_team.get("lineup") or []:
        compact_lineup.append({
            "slot": slot.get("slot_label") or slot.get("slot"),
            "player": compact_player(slot.get("player")),
        })
    compact_bench = {
        pos: [compact_player(p) for p in (my_team.get("bench_by_position") or {}).get(pos, [])]
        for pos in POSITIONS
    }

    opp_rows = [compact_opportunity(x) for x in (opportunities.get("players") or [])[:75]]
    opp_by_pos = {
        pos: [x for x in opp_rows if x.get("position") == pos][:15]
        for pos in POSITIONS
    }

    market_teams = market.get("teams") or []
    profile_teams = profiles.get("teams") or []
    current_power = ((power.get("scopes") or {}).get("current") or {}).get("rankings") or []
    all_time_power = ((power.get("scopes") or {}).get("all_time") or {}).get("rankings") or []

    context = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "Compact first-pass context for ChatGPT. Authoritative ownership/roster/pick/free-agent facts still come from data/current.",
        "data_health": health,
        "league": {
            "league_id": league.get("league_id"),
            "name": league.get("name"),
            "season": league.get("season"),
            "teams": league.get("teams"),
            "starter_slots": league.get("starter_slots"),
            "superflex": league.get("superflex"),
            "full_ppr": league.get("full_ppr"),
            "league_median_match": league.get("league_median_match"),
            "draft_rounds": league.get("draft_rounds"),
            "faab_budget": league.get("faab_budget"),
        },
        "my_team": {
            "manager": my_team.get("manager"),
            "team_name": my_team.get("team_name"),
            "market": my_market,
            "profile": my_profile,
            "playoff": my_playoff,
            "current_power": my_power,
            "needs": (needs.get("teams") or {}).get(MY_ROSTER_ID),
        },
        "league_leaders": {
            "current_power": current_power[:5],
            "all_time_power": all_time_power[:5],
            "market": market_teams[:5],
            "profiles": profile_teams[:5],
            "playoffs": (playoffs.get("teams") or [])[:5],
        },
        "top_opportunities": opp_rows[:20],
        "history": {
            "tracked_days": len(history.get("entries") or []),
            "first_date": ((history.get("entries") or [{}])[0]).get("date") if history.get("entries") else None,
            "latest_date": ((history.get("entries") or [{}])[-1]).get("date") if history.get("entries") else None,
        },
    }

    my_team_file = {
        "generated_at": context["generated_at"],
        "roster_id": 3,
        "manager": my_team.get("manager"),
        "team_name": my_team.get("team_name"),
        "record": my_team.get("record"),
        "waivers": my_team.get("waivers"),
        "position_counts": my_team.get("position_counts"),
        "lineup": compact_lineup,
        "bench_by_position": compact_bench,
        "picks": my_team.get("picks") or [],
        "market": my_market,
        "profile": my_profile,
        "playoff": my_playoff,
        "current_power": my_power,
        "needs": (needs.get("teams") or {}).get(MY_ROSTER_ID),
        "trade_partners": ((trade_partners.get("partners") or {}).get(MY_ROSTER_ID) or [])[:12],
        "recent_changes": (changes.get("changes") or [])[-20:],
    }

    waiver_file = {
        "generated_at": context["generated_at"],
        "note": "Every player in this file came from the confirmed current free-agent opportunity scanner. Verify against data/current/free_agents.json before a final waiver recommendation.",
        "methodology": opportunities.get("methodology"),
        "top": opp_rows[:50],
        "by_position": opp_by_pos,
    }

    trade_file = {
        "generated_at": context["generated_at"],
        "my_roster_id": 3,
        "my_market": my_market,
        "teams": [
            {
                "roster_id": x.get("roster_id"),
                "manager": x.get("manager"),
                "team_name": x.get("team_name"),
                "market_rank": x.get("market_rank"),
                "total_market_value": x.get("total_market_value"),
                "optimal_starter_market_value": x.get("optimal_starter_market_value"),
                "depth_market_value": x.get("depth_market_value"),
                "position_values": x.get("position_values"),
                "position_scores": x.get("position_scores"),
            }
            for x in market_teams
        ],
        "profiles": profile_teams,
        "current_power": current_power,
        "draft_capital": draft.get("teams") or [],
        "my_trade_partners": ((trade_partners.get("partners") or {}).get(MY_ROSTER_ID) or [])[:12],
        "recent_transactions": recent_tx[:40],
        "manager_tendencies": (tendencies.get("scopes") or {}).get("all_time"),
    }

    return {
        "ai_context.json": context,
        "ai_my_team.json": my_team_file,
        "ai_waivers.json": waiver_file,
        "ai_trade_market.json": trade_file,
    }


def build_ai_outputs(root: Path) -> None:
    derived = root / "data" / "derived"
    health = build_data_health(root)
    history = build_intelligence_history(root)
    bridge = build_ai_bridge(root, health, history)

    write_json(derived / "data_health.json", health)
    write_json(derived / "intelligence_history.json", history)
    for name, value in bridge.items():
        write_json(derived / name, value)
