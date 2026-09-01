from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
SOURCE_RELIABILITY = {
    "official": 1.0,
    "team": 0.9,
    "team_reporter": 0.8,
    "established_media": 0.7,
    "aggregator": 0.45,
    "unknown": 0.3,
}
TYPE_TTL_DAYS = {
    "inactive": 2,
    "injury": 7,
    "practice": 4,
    "depth_chart": 14,
    "role": 10,
    "coach_statement": 10,
    "beat_report": 7,
    "news": 7,
}


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
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return float(value)


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)
    except ValueError:
        return None


def player_name(player: dict[str, Any], player_id: str) -> str:
    return player.get("full_name") or " ".join(
        part for part in (player.get("first_name"), player.get("last_name")) if part
    ) or f"Sleeper {player_id}"


def signal_score(signal: dict[str, Any], now: datetime) -> float:
    direction = max(-1.0, min(1.0, number(signal.get("direction"))))
    magnitude = max(0.0, min(5.0, number(signal.get("magnitude")))) / 5.0
    reliability = max(0.0, min(1.0, number(signal.get("reliability"))))
    published = parse_time(signal.get("published_at"))
    ttl = max(1, int(number(signal.get("ttl_days"), 7)))
    age_days = max(0.0, (now - published).total_seconds() / 86400) if published else ttl
    recency = max(0.0, 1.0 - age_days / ttl)
    corroboration = min(1.2, 1.0 + max(0, int(number(signal.get("corroboration_count"), 1)) - 1) * 0.08)
    return round(direction * magnitude * reliability * recency * corroboration, 4)


def manual_signals(raw: dict[str, Any], players: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    rows = raw.get("signals") or []
    by_name = {player_name(p, str(pid)).lower(): str(pid) for pid, p in players.items()}
    signals = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        player_id = str(row.get("player_id") or "")
        if not player_id and row.get("name"):
            player_id = by_name.get(str(row["name"]).strip().lower(), "")
        if not player_id or player_id not in players:
            continue
        kind = str(row.get("type") or "news").lower()
        source_type = str(row.get("source_type") or "unknown").lower()
        published = parse_time(row.get("published_at"))
        ttl = max(1, int(number(row.get("ttl_days"), TYPE_TTL_DAYS.get(kind, 7))))
        if not published or (now - published).total_seconds() > ttl * 86400:
            continue
        summary = str(row.get("summary") or row.get("text") or "").strip()
        if not summary:
            continue
        signal = {
            "signal_id": str(row.get("signal_id") or f"manual-{player_id}-{index}"),
            "player_id": player_id,
            "player_name": player_name(players[player_id], player_id),
            "type": kind,
            "impact": str(row.get("impact") or "workload"),
            "direction": max(-1.0, min(1.0, number(row.get("direction")))),
            "magnitude": max(0.0, min(5.0, number(row.get("magnitude"), 1))),
            "source_type": source_type,
            "source": row.get("source"),
            "url": row.get("url"),
            "published_at": published.isoformat(),
            "event_date": row.get("event_date"),
            "ttl_days": ttl,
            "reliability": SOURCE_RELIABILITY.get(source_type, SOURCE_RELIABILITY["unknown"]),
            "corroboration_count": max(1, int(number(row.get("corroboration_count"), 1))),
            "summary": summary,
            "origin": "curated_report",
        }
        signal["weighted_score"] = signal_score(signal, now)
        signals.append(signal)
    return signals


def objective_signals(players: dict[str, Any], intel: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    intel_by_id = intel.get("players_by_id") or {}
    signals = []
    for raw_id, player in players.items():
        player_id = str(raw_id)
        name = player_name(player, player_id)
        injury = str(player.get("injury_status") or "").strip()
        if injury:
            severity = {"out": (-1, 5), "ir": (-1, 5), "pup": (-1, 5), "doubtful": (-1, 4), "questionable": (-1, 2)}
            direction, magnitude = severity.get(injury.lower(), (-1, 1))
            signals.append({
                "signal_id": f"sleeper-injury-{player_id}", "player_id": player_id, "player_name": name,
                "type": "injury", "impact": "availability", "direction": direction, "magnitude": magnitude,
                "source_type": "official", "source": "Sleeper player status", "url": None,
                "published_at": now.isoformat(), "event_date": None, "ttl_days": 2, "reliability": 0.82,
                "corroboration_count": 1, "summary": f"Sleeper lists {name} as {injury}.", "origin": "sleeper",
            })
        depth = player.get("depth_chart_order")
        if isinstance(depth, (int, float)) and int(depth) > 0:
            direction = 1 if int(depth) <= 2 else -1
            magnitude = 2 if int(depth) == 1 else 1 if int(depth) == 2 else min(3, int(depth) - 1)
            signals.append({
                "signal_id": f"sleeper-depth-{player_id}", "player_id": player_id, "player_name": name,
                "type": "depth_chart", "impact": "workload", "direction": direction, "magnitude": magnitude,
                "source_type": "team", "source": "Sleeper depth chart", "url": None,
                "published_at": now.isoformat(), "event_date": None, "ttl_days": 3, "reliability": 0.65,
                "corroboration_count": 1, "summary": f"Current Sleeper depth-chart order is {int(depth)}.", "origin": "sleeper",
            })
        performance = (intel_by_id.get(player_id) or {}).get("performance") or {}
        recent = performance.get("last3_opportunities_per_game")
        season = performance.get("opportunities_per_game")
        if performance.get("basis") == "current" and isinstance(recent, (int, float)) and isinstance(season, (int, float)):
            delta = recent - season
            if abs(delta) >= 1.5:
                signals.append({
                    "signal_id": f"usage-trend-{player_id}", "player_id": player_id, "player_name": name,
                    "type": "usage_trend", "impact": "workload", "direction": 1 if delta > 0 else -1,
                    "magnitude": min(5, max(1, abs(delta) / 2)), "source_type": "official",
                    "source": "nflverse play-by-play", "url": "https://nflverse.com/",
                    "published_at": now.isoformat(), "event_date": None, "ttl_days": 8, "reliability": 0.9,
                    "corroboration_count": 1,
                    "summary": f"Last-three-game opportunity volume is {abs(delta):.1f} per game {'above' if delta > 0 else 'below'} the season baseline.",
                    "origin": "measured_usage",
                })
    for signal in signals:
        signal["weighted_score"] = signal_score(signal, now)
    return signals


def aggregate_player(player_id: str, signals: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [signal for signal in signals if signal["player_id"] == player_id]
    narrative = sum(s["weighted_score"] for s in rows if s["origin"] == "curated_report")
    workload = sum(s["weighted_score"] for s in rows if s["impact"] == "workload")
    availability = 1.0
    for signal in rows:
        if signal["impact"] != "availability" or signal["direction"] >= 0:
            continue
        status = signal["summary"].lower()
        availability = min(availability, 0.0 if any(x in status for x in (" as out", " as ir", " as pup")) else 0.35 if "doubtful" in status else 0.85)
    # Narratives are deliberately capped at ±8%; all workload context at ±12%.
    narrative_pct = max(-0.08, min(0.08, narrative * 0.08))
    workload_pct = max(-0.12, min(0.12, workload * 0.10))
    weekly_multiplier = round(max(0.0, availability * (1 + workload_pct + narrative_pct)), 3)
    # Opportunity Scanner already scores Sleeper depth and injury fields. Only
    # new measured usage or curated reporting may adjust that baseline here.
    opportunity_evidence = sum(
        s["weighted_score"] for s in rows if s["origin"] in {"measured_usage", "curated_report"}
    )
    opportunity_adjustment = round(max(-12.0, min(12.0, opportunity_evidence * 10)), 1)
    confidence = "high" if any(s["reliability"] >= 0.9 for s in rows) else "medium" if rows else "low"
    net_direction = "positive" if weekly_multiplier > 1.015 else "negative" if weekly_multiplier < 0.985 else "neutral"
    return {
        "player_id": player_id,
        "signal_count": len(rows),
        "weekly_multiplier": weekly_multiplier,
        "availability_probability": availability,
        "opportunity_score_adjustment": opportunity_adjustment,
        "confidence": confidence,
        "net_direction": net_direction,
        "signals": sorted(rows, key=lambda s: (-abs(s["weighted_score"]), s["signal_id"])),
    }


def build_player_context_outputs(root: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    current = root / "data" / "current"
    derived = root / "data" / "derived"
    external = root / "data" / "external"
    players = read_json(current / "players_active.json", {}) or {}
    intel = read_json(derived / "player_intel.json", {}) or {}
    reports = read_json(external / "player_context_reports.json", {}) or {}
    opportunities = read_json(derived / "opportunity_scanner.json", {}) or {}
    team_assets = read_json(derived / "team_assets.json", {}) or {}
    relevant_ids = {
        str(player.get("player_id"))
        for team in team_assets.values()
        for player in (team.get("players") or [])
        if player.get("player_id")
    } | {
        str(player.get("player_id"))
        for player in (opportunities.get("players") or [])
        if player.get("player_id")
    }
    players = {str(pid): player for pid, player in players.items() if str(pid) in relevant_ids}
    signals = objective_signals(players, intel, now) + manual_signals(reports, players, now)
    player_ids = sorted({signal["player_id"] for signal in signals})
    by_id = {player_id: aggregate_player(player_id, signals) for player_id in player_ids}
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "methodology": "Time-decayed, source-weighted context. Narrative effects are capped at ±8%, combined workload context at ±12%, and availability remains a separate guardrail. Every adjustment retains its source and explanation.",
        "coverage": {
            "players_with_signals": len(by_id),
            "objective_signals": sum(1 for signal in signals if signal["origin"] != "curated_report"),
            "curated_reports": sum(1 for signal in signals if signal["origin"] == "curated_report"),
            "expired_or_invalid_reports_ignored": max(0, len(reports.get("signals") or []) - sum(1 for signal in signals if signal["origin"] == "curated_report")),
        },
        "source_status": {
            "sleeper_depth_and_status": "available" if players else "unavailable",
            "current_usage_trends": "available" if any(s["origin"] == "measured_usage" for s in signals) else "not_available",
            "curated_news_and_reports": "available" if any(s["origin"] == "curated_report" for s in signals) else "not_available",
        },
        "players_by_id": by_id,
    }
    write_json(derived / "player_context_signals.json", report)

    for player in opportunities.get("players") or []:
        context = by_id.get(str(player.get("player_id")))
        if not context:
            continue
        adjustment = context["opportunity_score_adjustment"]
        if adjustment:
            player["base_opportunity_score"] = player.get("opportunity_score")
            player["context_adjustment"] = adjustment
            player["context"] = {
                key: value for key, value in context.items() if key != "signals"
            } | {"signals": context.get("signals", [])[:3]}
            player["opportunity_score"] = round(max(0, min(100, number(player.get("opportunity_score")) + adjustment)), 1)
            player["reasons"] = ([f"Current context adjusts the opportunity score {adjustment:+.1f}."] + (player.get("reasons") or []))[:10]
        score = player["opportunity_score"]
        player["tier"] = "Priority" if score >= 70 else "Strong stash" if score >= 55 else "Watch" if score >= 40 else "Deep"
    opportunities["players"] = sorted(opportunities.get("players") or [], key=lambda p: (-number(p.get("opportunity_score")), p.get("name") or ""))
    opportunities["context_methodology"] = report["methodology"]
    write_json(derived / "opportunity_scanner.json", opportunities)
    write_json(derived / "opportunity_top50.json", {
        "generated_at": opportunities.get("generated_at"),
        "methodology": opportunities.get("methodology"),
        "context_methodology": opportunities.get("context_methodology"),
        "sleeper_attribution": opportunities.get("sleeper_attribution"),
        "players": (opportunities.get("players") or [])[:50],
    })
    return report


if __name__ == "__main__":
    build_player_context_outputs(Path(__file__).resolve().parents[1])
