from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data" / "current"
EXTERNAL = ROOT / "data" / "external"

POSITIONS = {"QB", "RB", "WR", "TE"}
USER_AGENT = "715-dynasty-hq/1.0 (+https://github.com/abealberts/715-dynasty-data)"

DYNASTY_DEALER_URL = "https://www.dynastydealer.com/api/player-values"
PLAYER_IDS_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
NFLVERSE_STATS = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"
NFLVERSE_SNAPS = "https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.csv"


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def fetch_bytes(url: str, attempts: int = 3, timeout: int = 45) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "*/*",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # network/transient HTTP errors
            last = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")


def fetch_json(url: str) -> Any:
    return json.loads(fetch_bytes(url).decode("utf-8"))


def fetch_csv(url: str) -> list[dict[str, str]]:
    text = fetch_bytes(url).decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def num(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    if value in (None, "", "NA", "NaN", "nan"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def text_id(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.upper() in {"NA", "NAN", "NONE"}:
        return None
    # IDs sometimes arrive from CSV tooling as "1234.0".
    if value.endswith(".0") and value[:-2].isdigit():
        value = value[:-2]
    return value


def build_crosswalk(rows: list[dict[str, str]]) -> dict[str, Any]:
    by_gsis: dict[str, str] = {}
    by_pfr: dict[str, str] = {}
    player_meta: dict[str, dict[str, Any]] = {}

    for row in rows:
        sleeper = text_id(row.get("sleeper_id"))
        if not sleeper:
            continue
        pos = (row.get("position") or "").strip().upper()
        meta = {
            "sleeper_id": sleeper,
            "name": row.get("name"),
            "position": pos or None,
            "gsis_id": text_id(row.get("gsis_id")),
            "pfr_id": text_id(row.get("pfr_id")),
        }
        player_meta[sleeper] = meta
        if meta["gsis_id"]:
            by_gsis[str(meta["gsis_id"])] = sleeper
        if meta["pfr_id"]:
            by_pfr[str(meta["pfr_id"])] = sleeper

    return {
        "by_gsis": by_gsis,
        "by_pfr": by_pfr,
        "players": player_meta,
    }


def league_fantasy_points(row: dict[str, Any], scoring: dict[str, Any]) -> float:
    # 715 currently uses these standard offensive categories. Read the live
    # settings so this remains correct if the commissioner ever changes them.
    total = 0.0
    total += num(row, "passing_yards") * float(scoring.get("pass_yd", 0.04) or 0)
    total += num(row, "passing_tds") * float(scoring.get("pass_td", 4) or 0)
    total += num(row, "passing_interceptions") * float(scoring.get("pass_int", -2) or 0)
    total += num(row, "passing_2pt_conversions") * float(scoring.get("pass_2pt", 2) or 0)

    total += num(row, "rushing_yards") * float(scoring.get("rush_yd", 0.1) or 0)
    total += num(row, "rushing_tds") * float(scoring.get("rush_td", 6) or 0)
    total += num(row, "rushing_2pt_conversions") * float(scoring.get("rush_2pt", 2) or 0)

    total += num(row, "receptions") * float(scoring.get("rec", 0) or 0)
    total += num(row, "receiving_yards") * float(scoring.get("rec_yd", 0.1) or 0)
    total += num(row, "receiving_tds") * float(scoring.get("rec_td", 6) or 0)
    total += num(row, "receiving_2pt_conversions") * float(scoring.get("rec_2pt", 2) or 0)

    # nflverse splits offensive lost fumbles by play type. These categories
    # are mutually exclusive for a lost fumble and match the usual -2 setting.
    lost = (
        num(row, "sack_fumbles_lost")
        + num(row, "rushing_fumbles_lost")
        + num(row, "receiving_fumbles_lost")
    )
    total += lost * float(scoring.get("fum_lost", -2) or 0)

    # Individual return/special-teams touchdowns.
    total += num(row, "special_teams_tds") * float(scoring.get("st_td", 6) or 0)
    return round(total, 3)


def normalize_snap_pct(value: float) -> float:
    if value <= 0:
        return 0.0
    # PFR/nflverse stores this as a fraction (0–1). This guard also supports
    # a future source that might emit 0–100.
    return value * 100.0 if value <= 1.01 else value


def aggregate_performance(
    season: int,
    stat_rows: list[dict[str, str]],
    snap_rows: list[dict[str, str]],
    crosswalk: dict[str, Any],
    scoring: dict[str, Any],
) -> dict[str, Any]:
    by_gsis = crosswalk["by_gsis"]
    by_pfr = crosswalk["by_pfr"]
    meta = crosswalk["players"]

    weekly: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)

    for row in stat_rows:
        if str(row.get("season") or "") != str(season):
            continue
        if str(row.get("season_type") or "").upper() not in {"REG", "REGULAR"}:
            continue
        sid = by_gsis.get(str(row.get("player_id") or "").strip())
        if not sid:
            continue
        pos = (meta.get(sid) or {}).get("position")
        if pos not in POSITIONS:
            continue
        week = int(num(row, "week"))
        if week <= 0:
            continue

        attempts = num(row, "attempts")
        carries = num(row, "carries")
        targets = num(row, "targets")
        receptions = num(row, "receptions")
        skill_opps = carries + targets
        opportunities = attempts + carries if pos == "QB" else skill_opps

        weekly[sid][week] = {
            "week": week,
            "team": row.get("team"),
            "opponent": row.get("opponent_team"),
            "fantasy_points_715": league_fantasy_points(row, scoring),
            "attempts": attempts,
            "carries": carries,
            "targets": targets,
            "receptions": receptions,
            "touches": carries + receptions,
            "opportunities": opportunities,
            "passing_yards": num(row, "passing_yards"),
            "passing_tds": num(row, "passing_tds"),
            "passing_interceptions": num(row, "passing_interceptions"),
            "rushing_yards": num(row, "rushing_yards"),
            "rushing_tds": num(row, "rushing_tds"),
            "receiving_yards": num(row, "receiving_yards"),
            "receiving_tds": num(row, "receiving_tds"),
            "target_share": num(row, "target_share"),
            "air_yards_share": num(row, "air_yards_share"),
            "offense_snaps": 0.0,
            "offense_snap_pct": None,
        }

    for row in snap_rows:
        if str(row.get("season") or "") != str(season):
            continue
        if str(row.get("game_type") or "").upper() not in {"REG", "REGULAR"}:
            continue
        sid = by_pfr.get(str(row.get("pfr_player_id") or "").strip())
        if not sid:
            continue
        pos = (meta.get(sid) or {}).get("position")
        if pos not in POSITIONS:
            continue
        week = int(num(row, "week"))
        if week <= 0:
            continue
        entry = weekly[sid].setdefault(
            week,
            {
                "week": week,
                "team": row.get("team"),
                "opponent": row.get("opponent"),
                "fantasy_points_715": 0.0,
                "attempts": 0.0,
                "carries": 0.0,
                "targets": 0.0,
                "receptions": 0.0,
                "touches": 0.0,
                "opportunities": 0.0,
                "passing_yards": 0.0,
                "passing_tds": 0.0,
                "passing_interceptions": 0.0,
                "rushing_yards": 0.0,
                "rushing_tds": 0.0,
                "receiving_yards": 0.0,
                "receiving_tds": 0.0,
                "target_share": 0.0,
                "air_yards_share": 0.0,
                "offense_snaps": 0.0,
                "offense_snap_pct": None,
            },
        )
        entry["offense_snaps"] = num(row, "offense_snaps")
        entry["offense_snap_pct"] = round(normalize_snap_pct(num(row, "offense_pct")), 1)

    players = {}
    for sid, weeks_map in weekly.items():
        weeks = [weeks_map[w] for w in sorted(weeks_map)]
        if not weeks:
            continue

        # A "game" for usage purposes is any regular-season week where the
        # player logged an offensive snap or an offensive box-score event.
        game_rows = [
            w for w in weeks
            if (w.get("offense_snaps") or 0) > 0
            or (w.get("opportunities") or 0) > 0
            or abs(float(w.get("fantasy_points_715") or 0)) > 0
        ]
        if not game_rows:
            continue

        def total(key: str) -> float:
            return sum(float(w.get(key) or 0) for w in game_rows)

        def avg(key: str) -> float:
            vals = [float(w.get(key) or 0) for w in game_rows]
            return sum(vals) / len(vals) if vals else 0.0

        snap_vals = [
            float(w["offense_snap_pct"])
            for w in game_rows
            if isinstance(w.get("offense_snap_pct"), (int, float))
        ]
        target_share_vals = [float(w.get("target_share") or 0) for w in game_rows]
        air_share_vals = [float(w.get("air_yards_share") or 0) for w in game_rows]

        last3 = game_rows[-3:]
        players[sid] = {
            **(meta.get(sid) or {}),
            "season": season,
            "games": len(game_rows),
            "fantasy_points_715": round(total("fantasy_points_715"), 2),
            "ppg_715": round(avg("fantasy_points_715"), 2),
            "opportunities": round(total("opportunities"), 1),
            "opportunities_per_game": round(avg("opportunities"), 2),
            "touches_per_game": round(avg("touches"), 2),
            "targets_per_game": round(avg("targets"), 2),
            "carries_per_game": round(avg("carries"), 2),
            "offense_snap_pct": round(sum(snap_vals) / len(snap_vals), 1) if snap_vals else None,
            "target_share": round((sum(target_share_vals) / len(target_share_vals)) * 100, 1) if target_share_vals else None,
            "air_yards_share": round((sum(air_share_vals) / len(air_share_vals)) * 100, 1) if air_share_vals else None,
            "last3_ppg_715": round(
                sum(float(w.get("fantasy_points_715") or 0) for w in last3) / len(last3), 2
            ) if last3 else None,
            "last3_opportunities_per_game": round(
                sum(float(w.get("opportunities") or 0) for w in last3) / len(last3), 2
            ) if last3 else None,
            "weekly": game_rows,
        }

    return {
        "season": season,
        "players": players,
        "matched_players": len(players),
    }


def build_market(payload: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in payload.get("players") or []:
        sid = text_id(item.get("sleeper_id"))
        pos = str(item.get("position") or "").upper()
        if not sid or pos not in POSITIONS:
            continue
        rows.append({
            "sleeper_id": sid,
            "name": item.get("name"),
            "position": pos,
            "team": item.get("team"),
            "age": item.get("age"),
            "base_value": int(float(item.get("base_value") or 0)),
            "current_value": int(float(item.get("current_value") or 0)),
            "votes": int(float(item.get("votes") or 0)),
            "vote_rating": item.get("vote_rating"),
            "updated_at": item.get("updated_at"),
        })

    rows.sort(key=lambda x: (-x["current_value"], x.get("name") or ""))
    pos_counts: dict[str, int] = defaultdict(int)
    by_id = {}
    for rank, item in enumerate(rows, 1):
        pos_counts[item["position"]] += 1
        item["rank"] = rank
        item["position_rank"] = pos_counts[item["position"]]
        by_id[item["sleeper_id"]] = item

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Dynasty Dealer",
        "source_url": "https://www.dynastydealer.com/",
        "api_url": DYNASTY_DEALER_URL,
        "attribution": "Values by Dynasty Dealer",
        "provider_timestamp": payload.get("timestamp"),
        "total_players": len(rows),
        "players": by_id,
    }


def main() -> None:
    league = read_json(CURRENT / "league.json", {}) or {}
    if not league:
        raise RuntimeError("data/current/league.json is required before external sync")

    season = int(league.get("season") or datetime.now().year)
    seasons = [season - 1, season]
    scoring = league.get("scoring_settings") or {}
    status = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {},
    }

    # Crosswalk
    crosswalk = None
    try:
        rows = fetch_csv(PLAYER_IDS_URL)
        crosswalk = build_crosswalk(rows)
        status["sources"]["player_ids"] = {
            "status": "ok",
            "rows": len(rows),
            "url": PLAYER_IDS_URL,
        }
    except Exception as exc:
        status["sources"]["player_ids"] = {"status": "error", "error": str(exc), "url": PLAYER_IDS_URL}

    # Dynasty Dealer
    try:
        market_payload = fetch_json(DYNASTY_DEALER_URL)
        market = build_market(market_payload)
        write_json(EXTERNAL / "dynasty_values.json", market)
        status["sources"]["dynasty_dealer"] = {
            "status": "ok",
            "players": market["total_players"],
            "url": DYNASTY_DEALER_URL,
        }
    except Exception as exc:
        status["sources"]["dynasty_dealer"] = {
            "status": "stale" if (EXTERNAL / "dynasty_values.json").exists() else "error",
            "error": str(exc),
            "url": DYNASTY_DEALER_URL,
        }

    # nflverse
    performance = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "nflverse",
        "source_url": "https://nflverse.com/",
        "id_crosswalk_source": "DynastyProcess",
        "id_crosswalk_url": PLAYER_IDS_URL,
        "scoring_basis": {
            "league_id": league.get("league_id"),
            "season": str(season),
            "note": "Fantasy points are recalculated from nflverse box-score stats using the current 715 scoring settings.",
        },
        "seasons": {},
    }

    if crosswalk:
        for year in seasons:
            stat_url = NFLVERSE_STATS.format(season=year)
            snap_url = NFLVERSE_SNAPS.format(season=year)
            try:
                stats = fetch_csv(stat_url)
            except Exception as exc:
                stats = []
                status["sources"][f"nflverse_stats_{year}"] = {
                    "status": "unavailable",
                    "error": str(exc),
                    "url": stat_url,
                }
            else:
                status["sources"][f"nflverse_stats_{year}"] = {
                    "status": "ok",
                    "rows": len(stats),
                    "url": stat_url,
                }

            try:
                snaps = fetch_csv(snap_url)
            except Exception as exc:
                snaps = []
                status["sources"][f"nflverse_snaps_{year}"] = {
                    "status": "unavailable",
                    "error": str(exc),
                    "url": snap_url,
                }
            else:
                status["sources"][f"nflverse_snaps_{year}"] = {
                    "status": "ok",
                    "rows": len(snaps),
                    "url": snap_url,
                }

            if stats or snaps:
                performance["seasons"][str(year)] = aggregate_performance(
                    year, stats, snaps, crosswalk, scoring
                )

        write_json(EXTERNAL / "player_performance.json", performance)

    # Preserve stale performance if the feed is temporarily unavailable.
    if not performance["seasons"] and not (EXTERNAL / "player_performance.json").exists():
        status["sources"]["performance"] = {
            "status": "error",
            "error": "No nflverse season files could be loaded and no cached performance feed exists.",
        }

    write_json(EXTERNAL / "external_status.json", status)
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
