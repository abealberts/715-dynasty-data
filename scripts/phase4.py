from __future__ import annotations

import json
import math
import random
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POSITIONS = ("QB", "RB", "WR", "TE")
SIMULATIONS = 10_000
TRANSITION_WEEKS = 6
RNG_SEED = 7152026


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


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def normalize_map(values: dict[str, float], invert: bool = False) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if math.isclose(lo, hi):
        base = {k: 50.0 for k in values}
    else:
        base = {k: ((v - lo) / (hi - lo)) * 100.0 for k, v in values.items()}
    if invert:
        return {k: 100.0 - v for k, v in base.items()}
    return base


def pct(wins: float, ties: float, games: float) -> float:
    if games <= 0:
        return 0.0
    return (wins + 0.5 * ties) / games


def safe_mean(values: list[float], fallback: float = 120.0) -> float:
    return statistics.mean(values) if values else fallback


def safe_stdev(values: list[float], fallback: float = 25.0) -> float:
    if len(values) >= 2:
        return max(12.0, statistics.stdev(values))
    return max(12.0, fallback)


def completed_current_weeks(matchups: dict[str, Any], nfl_state: dict[str, Any]) -> list[int]:
    current_week = int(nfl_state.get("week") or nfl_state.get("display_week") or 1)
    out = []
    for key, rows in (matchups or {}).items():
        if not str(key).isdigit():
            continue
        week = int(key)
        if week >= current_week:
            continue
        if any(float((row or {}).get("points") or 0) != 0 for row in (rows or [])):
            out.append(week)
    return sorted(out)


def regular_season_weeks(league: dict[str, Any], matchups: dict[str, Any]) -> list[int]:
    playoff_start = int((league.get("settings") or {}).get("playoff_week_start") or 99)
    out = []
    for key, rows in (matchups or {}).items():
        if not str(key).isdigit():
            continue
        week = int(key)
        if week >= playoff_start:
            continue
        if any(float((row or {}).get("points") or 0) != 0 for row in (rows or [])):
            out.append(week)
    return sorted(out)


def history_datasets(history_dir: Path) -> list[dict[str, Any]]:
    manifest = read_json(history_dir / "manifest.json", {}) or {}
    datasets = []
    for item in manifest.get("seasons") or []:
        folder = history_dir / str(item.get("folder"))
        league = read_json(folder / "league.json", {}) or {}
        rosters = read_json(folder / "roster_index.json", {}) or {}
        matchups = read_json(folder / "matchups.json", {}) or {}
        transactions = read_json(folder / "transactions.json", {}) or {}
        if league and rosters and matchups:
            datasets.append({
                "season": str(league.get("season") or item.get("season") or ""),
                "league": league,
                "rosters": rosters,
                "matchups": matchups,
                "transactions": transactions,
            })
    return sorted(datasets, key=lambda x: x["season"])


def score_samples(
    league: dict[str, Any],
    rosters: dict[str, Any],
    matchups: dict[str, Any],
    weeks: list[int],
) -> dict[str, list[float]]:
    samples: dict[str, list[float]] = defaultdict(list)
    for week in weeks:
        for row in matchups.get(str(week)) or []:
            rid = str(row.get("roster_id"))
            roster = rosters.get(rid) or {}
            owner = roster.get("owner_id")
            if owner is None:
                continue
            samples[str(owner)].append(float(row.get("points") or 0))
    return dict(samples)


def all_history_score_samples(datasets: list[dict[str, Any]]) -> dict[str, list[float]]:
    result: dict[str, list[float]] = defaultdict(list)
    for data in datasets:
        weeks = regular_season_weeks(data["league"], data["matchups"])
        samples = score_samples(data["league"], data["rosters"], data["matchups"], weeks)
        for owner, values in samples.items():
            result[owner].extend(values)
    return dict(result)


def build_model_parameters(
    current_league: dict[str, Any],
    current_rosters: dict[str, Any],
    current_matchups: dict[str, Any],
    nfl_state: dict[str, Any],
    datasets: list[dict[str, Any]],
) -> dict[str, Any]:
    completed = completed_current_weeks(current_matchups, nfl_state)
    current_samples = score_samples(
        current_league,
        current_rosters,
        current_matchups,
        completed,
    )
    historical = all_history_score_samples(datasets)
    league_history_values = [x for values in historical.values() for x in values]
    league_prior_mean = safe_mean(league_history_values, 120.0)
    league_prior_sd = safe_stdev(league_history_values, 25.0)
    current_weight = min(1.0, len(completed) / float(TRANSITION_WEEKS))

    models = {}
    for rid, roster in current_rosters.items():
        owner = str(roster.get("owner_id") or f"current:{rid}")
        prior = historical.get(owner) or league_history_values
        current = current_samples.get(owner) or []

        prior_mean = safe_mean(prior, league_prior_mean)
        prior_sd = safe_stdev(prior, league_prior_sd)
        current_mean = safe_mean(current, prior_mean)
        current_sd = safe_stdev(current, prior_sd) if len(current) >= 2 else prior_sd

        if current:
            mean = (prior_mean * (1.0 - current_weight)) + (current_mean * current_weight)
            sd = (prior_sd * (1.0 - current_weight)) + (current_sd * current_weight)
        else:
            mean, sd = prior_mean, prior_sd

        models[str(rid)] = {
            "roster_id": int(rid),
            "owner_id": owner,
            "manager": roster.get("display_name"),
            "team_name": roster.get("team_name"),
            "prior_weeks": len(prior),
            "current_weeks": len(current),
            "prior_mean": round(prior_mean, 2),
            "prior_sd": round(prior_sd, 2),
            "current_mean": round(current_mean, 2) if current else None,
            "current_sd": round(current_sd, 2) if len(current) >= 2 else None,
            "model_mean": round(mean, 2),
            "model_sd": round(max(12.0, sd), 2),
        }

    mean_norm = normalize_map({rid: float(m["model_mean"]) for rid, m in models.items()})
    for rid, model in models.items():
        model["strength_score"] = round(mean_norm.get(rid, 50.0), 1)

    if not completed:
        status = "preseason_prior"
    elif current_weight < 1.0:
        status = "blended"
    else:
        status = "current_season"

    return {
        "completed_weeks": completed,
        "current_weight": round(current_weight, 4),
        "prior_weight": round(1.0 - current_weight, 4),
        "status": status,
        "transition_weeks": TRANSITION_WEEKS,
        "models": models,
    }


def current_standings(
    current_rosters: dict[str, Any],
    current_matchups: dict[str, Any],
    completed: list[int],
) -> dict[str, Any]:
    standings = {
        str(rid): {
            "wins": 0,
            "losses": 0,
            "ties": 0,
            "points_for": 0.0,
        }
        for rid in current_rosters
    }

    for week in completed:
        rows = [row for row in (current_matchups.get(str(week)) or []) if row.get("roster_id") is not None]
        scores = {str(row["roster_id"]): float(row.get("points") or 0) for row in rows}
        if not scores:
            continue
        median = statistics.median(scores.values())
        for rid, score in scores.items():
            standings[rid]["points_for"] += score
            if score > median:
                standings[rid]["wins"] += 1
            elif score < median:
                standings[rid]["losses"] += 1
            else:
                standings[rid]["ties"] += 1

        pairs: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            mid = row.get("matchup_id")
            if mid is not None:
                pairs[str(mid)].append(str(row["roster_id"]))
        for pair in pairs.values():
            if len(pair) != 2:
                continue
            a, b = pair
            if scores[a] > scores[b]:
                standings[a]["wins"] += 1
                standings[b]["losses"] += 1
            elif scores[b] > scores[a]:
                standings[b]["wins"] += 1
                standings[a]["losses"] += 1
            else:
                standings[a]["ties"] += 1
                standings[b]["ties"] += 1

    return standings


def future_schedule(
    league: dict[str, Any],
    matchups: dict[str, Any],
    completed: list[int],
) -> dict[int, list[tuple[str, str]]]:
    playoff_start = int((league.get("settings") or {}).get("playoff_week_start") or 14)
    complete_set = set(completed)
    schedule = {}
    for week in range(1, playoff_start):
        if week in complete_set:
            continue
        pairs: dict[str, list[str]] = defaultdict(list)
        for row in matchups.get(str(week)) or []:
            if row.get("roster_id") is None or row.get("matchup_id") is None:
                continue
            pairs[str(row["matchup_id"])].append(str(row["roster_id"]))
        valid = []
        for pair in pairs.values():
            if len(pair) == 2:
                valid.append((pair[0], pair[1]))
        if valid:
            schedule[week] = valid
    return schedule


def draw_score(rng: random.Random, model: dict[str, Any]) -> float:
    return max(0.0, rng.gauss(float(model["model_mean"]), float(model["model_sd"])))


def playoff_matchup_score(
    rng: random.Random,
    rid: str,
    models: dict[str, Any],
    round_weeks: int,
) -> float:
    return sum(draw_score(rng, models[rid]) for _ in range(round_weeks))


def build_playoff_simulator(
    league: dict[str, Any],
    rosters: dict[str, Any],
    matchups: dict[str, Any],
    nfl_state: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    model = build_model_parameters(league, rosters, matchups, nfl_state, history)
    models = model["models"]
    completed = model["completed_weeks"]
    actual = current_standings(rosters, matchups, completed)
    schedule = future_schedule(league, matchups, completed)
    playoff_teams = int((league.get("settings") or {}).get("playoff_teams") or 4)
    round_weeks = 2 if int((league.get("settings") or {}).get("playoff_round_type") or 1) == 2 else 1

    rng = random.Random(RNG_SEED)
    playoff_counts = defaultdict(int)
    one_seed_counts = defaultdict(int)
    title_counts = defaultdict(int)
    final_wins = defaultdict(float)
    fourth_seed_wins = []

    roster_ids = sorted(models, key=lambda x: int(x))
    total_regular_decisions = max(1, (int((league.get("settings") or {}).get("playoff_week_start") or 14) - 1) * 2)

    for _ in range(SIMULATIONS):
        table = {
            rid: {
                "wins": float(actual.get(rid, {}).get("wins") or 0),
                "losses": float(actual.get(rid, {}).get("losses") or 0),
                "ties": float(actual.get(rid, {}).get("ties") or 0),
                "points_for": float(actual.get(rid, {}).get("points_for") or 0),
            }
            for rid in roster_ids
        }

        for week in sorted(schedule):
            scores = {rid: draw_score(rng, models[rid]) for rid in roster_ids}
            med = statistics.median(scores.values())
            for rid, score in scores.items():
                table[rid]["points_for"] += score
                if score > med:
                    table[rid]["wins"] += 1
                elif score < med:
                    table[rid]["losses"] += 1
                else:
                    table[rid]["ties"] += 1

            for a, b in schedule[week]:
                if scores[a] > scores[b]:
                    table[a]["wins"] += 1
                    table[b]["losses"] += 1
                elif scores[b] > scores[a]:
                    table[b]["wins"] += 1
                    table[a]["losses"] += 1
                else:
                    table[a]["ties"] += 1
                    table[b]["ties"] += 1

        ordered = sorted(
            roster_ids,
            key=lambda rid: (
                -(table[rid]["wins"] + 0.5 * table[rid]["ties"]),
                -table[rid]["points_for"],
                int(rid),
            ),
        )
        seeds = ordered[:playoff_teams]
        if seeds:
            one_seed_counts[seeds[0]] += 1
            cutoff = table[seeds[-1]]["wins"] + 0.5 * table[seeds[-1]]["ties"]
            fourth_seed_wins.append(cutoff)
        for rid in seeds:
            playoff_counts[rid] += 1
        for rid in roster_ids:
            final_wins[rid] += table[rid]["wins"] + 0.5 * table[rid]["ties"]

        if len(seeds) >= 4:
            semi_pairs = [(seeds[0], seeds[3]), (seeds[1], seeds[2])]
            finalists = []
            for a, b in semi_pairs:
                a_score = playoff_matchup_score(rng, a, models, round_weeks)
                b_score = playoff_matchup_score(rng, b, models, round_weeks)
                finalists.append(a if a_score >= b_score else b)
            a, b = finalists
            a_score = playoff_matchup_score(rng, a, models, round_weeks)
            b_score = playoff_matchup_score(rng, b, models, round_weeks)
            champion = a if a_score >= b_score else b
            title_counts[champion] += 1

    teams = []
    for rid in roster_ids:
        m = models[rid]
        avg_wins = final_wins[rid] / SIMULATIONS
        teams.append({
            **m,
            "playoff_odds": round((playoff_counts[rid] / SIMULATIONS) * 100, 1),
            "one_seed_odds": round((one_seed_counts[rid] / SIMULATIONS) * 100, 1),
            "title_odds": round((title_counts[rid] / SIMULATIONS) * 100, 1),
            "projected_standings_wins": round(avg_wins, 1),
            "projected_standings_losses": round(max(0.0, total_regular_decisions - avg_wins), 1),
            "actual_standings_wins": actual.get(rid, {}).get("wins", 0),
            "actual_standings_losses": actual.get(rid, {}).get("losses", 0),
            "actual_points_for": round(float(actual.get(rid, {}).get("points_for") or 0), 2),
        })
    teams.sort(key=lambda x: (-x["playoff_odds"], -x["title_odds"], -x["model_mean"]))

    return {
        "generated_at": generated_at,
        "simulations": SIMULATIONS,
        "current_season": str(league.get("season") or ""),
        "model_status": model["status"],
        "model_blend": {
            "historical_weight": round(model["prior_weight"] * 100, 1),
            "current_season_weight": round(model["current_weight"] * 100, 1),
            "full_transition_after_weeks": TRANSITION_WEEKS,
        },
        "completed_weeks": completed,
        "remaining_schedule_weeks": sorted(schedule),
        "playoff_teams": playoff_teams,
        "playoff_round_weeks": round_weeks,
        "average_fourth_seed_standings_wins": round(statistics.mean(fourth_seed_wins), 1) if fourth_seed_wins else None,
        "methodology": "Historical-performance simulator, not a player-projection model. Before 2026 games, each manager's 2025 regular-season scoring distribution is the prior. Completed 2026 weeks phase in linearly and fully replace the prior after six completed weeks. Each simulated regular-season week awards both scheduled H2H and league-median results; playoff seeding uses standings wins with points-for as tiebreaker. Title odds use the league's configured playoff round length.",
        "teams": teams,
    }


def pick_value(pick: dict[str, Any], current_year: int) -> float:
    round_weights = {1: 5.0, 2: 2.5, 3: 1.2, 4: 0.6, 5: 0.3}
    year = int(pick.get("season") or current_year)
    distance = max(0, year - current_year)
    discount = max(0.55, 1.0 - (0.1 * distance))
    return round_weights.get(int(pick.get("round") or 5), 0.2) * discount


def build_team_profiles(
    root: Path,
    playoff: dict[str, Any],
) -> dict[str, Any]:
    current = root / "data" / "current"
    derived = root / "data" / "derived"
    league = read_json(current / "league.json", {}) or {}
    rosters = read_json(current / "roster_index.json", {}) or {}
    players = read_json(current / "players_known.json", {}) or read_json(current / "players_active.json", {}) or {}
    picks = read_json(current / "pick_ownership.json", []) or []
    team_needs = read_json(derived / "team_needs.json", {}) or {}
    lineups = read_json(derived / "lineup_efficiency.json", {}) or {}
    current_year = int(league.get("season") or 2026)

    model_by_rid = {str(x["roster_id"]): x for x in playoff.get("teams") or []}
    all_time_lineups = ((lineups.get("scopes") or {}).get("all_time") or {}).get("season") or []
    lineup_by_owner = {str(x.get("owner_id")): x for x in all_time_lineups if x.get("owner_id") is not None}

    raw_youth = {}
    raw_capital = {}
    raw_balance = {}
    raw_management = {}
    raw_stability = {}
    details = {}

    for rid, roster in rosters.items():
        ages = []
        young = 0
        for pid in roster.get("players") or []:
            p = players.get(str(pid)) or {}
            if p.get("position") not in POSITIONS:
                continue
            age = p.get("age")
            if isinstance(age, (int, float)):
                ages.append(float(age))
                if age <= 25:
                    young += 1
        young_share = (young / len(ages)) if ages else 0.0
        raw_youth[str(rid)] = young_share

        owned = [p for p in picks if int(p.get("owner_roster_id") or -1) == int(rid)]
        capital_value = sum(pick_value(p, current_year) for p in owned)
        raw_capital[str(rid)] = capital_value

        needs = ((team_needs.get("teams") or {}).get(str(rid)) or {}).get("positions") or {}
        gap = 0.0
        for pos in POSITIONS:
            info = needs.get(pos) or {}
            target = float(info.get("target") or 0)
            count = float(info.get("count") or 0)
            gap += max(0.0, target - count)
        raw_balance[str(rid)] = max(0.0, 100.0 - (gap * 18.0))

        owner = str(roster.get("owner_id") or "")
        lineup = lineup_by_owner.get(owner) or {}
        raw_management[str(rid)] = float(lineup.get("lineup_efficiency") or 75.0)

        model = model_by_rid.get(str(rid)) or {}
        raw_stability[str(rid)] = float(model.get("model_sd") or 25.0)

        details[str(rid)] = {
            "ages": ages,
            "young_share": young_share,
            "owned_picks": owned,
            "capital_value": capital_value,
        }

    youth_scores = normalize_map(raw_youth)
    capital_scores = normalize_map(raw_capital)
    balance_scores = normalize_map(raw_balance)
    management_scores = normalize_map(raw_management)
    stability_scores = normalize_map(raw_stability, invert=True)

    profiles = []
    for rid, roster in rosters.items():
        model = model_by_rid.get(str(rid)) or {}
        perf = float(model.get("strength_score") or 50.0)
        youth = youth_scores.get(str(rid), 50.0)
        capital = capital_scores.get(str(rid), 50.0)
        balance = balance_scores.get(str(rid), 50.0)
        management = management_scores.get(str(rid), 50.0)
        stability = stability_scores.get(str(rid), 50.0)
        franchise_score = (
            perf * 0.40 + capital * 0.20 + youth * 0.15 +
            balance * 0.10 + management * 0.10 + stability * 0.05
        )
        playoff_odds = float(model.get("playoff_odds") or 0)

        if playoff_odds >= 65:
            window = "Contender"
        elif playoff_odds >= 40:
            window = "Playoff Hunt"
        elif playoff_odds <= 25:
            # A team that is far outside the playoff picture should not be
            # labeled "Middle" simply because its draft-capital score lands
            # near league average. Separate intentional rebuild profiles from
            # low-upside teams that need a retool.
            if (capital >= 40 and youth >= 60) or capital >= 65:
                window = "Rebuilder"
            else:
                window = "Retool Needed"
        else:
            window = "Middle"

        metrics = {
            "performance_prior": round(perf, 1),
            "draft_capital": round(capital, 1),
            "youth": round(youth, 1),
            "roster_balance": round(balance, 1),
            "lineup_management": round(management, 1),
            "stability": round(stability, 1),
        }
        sorted_metrics = sorted(metrics.items(), key=lambda x: x[1], reverse=True)
        strengths = [k.replace("_", " ").title() for k, v in sorted_metrics[:2] if v >= 55]
        risks = [k.replace("_", " ").title() for k, v in sorted(metrics.items(), key=lambda x: x[1])[:2] if v <= 45]

        ages = details[str(rid)]["ages"]
        owned = details[str(rid)]["owned_picks"]
        profiles.append({
            "roster_id": int(rid),
            "owner_id": roster.get("owner_id"),
            "manager": roster.get("display_name"),
            "team_name": roster.get("team_name"),
            "window": window,
            "franchise_score": round(franchise_score, 1),
            "metrics": metrics,
            "strengths": strengths,
            "risks": risks,
            "playoff_odds": playoff_odds,
            "title_odds": float(model.get("title_odds") or 0),
            "model_mean": model.get("model_mean"),
            "model_sd": model.get("model_sd"),
            "average_roster_age": round(statistics.mean(ages), 1) if ages else None,
            "young_player_share": round(details[str(rid)]["young_share"] * 100, 1),
            "pick_count": len(owned),
            "first_round_picks": sum(1 for p in owned if int(p.get("round") or 0) == 1),
            "early_picks": sum(1 for p in owned if int(p.get("round") or 0) <= 2),
        })

    profiles.sort(key=lambda x: (-x["franchise_score"], -x["playoff_odds"]))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_status": playoff.get("model_status"),
        "model_blend": playoff.get("model_blend"),
        "methodology": "Current franchise profile combining the historical/current scoring model with today's roster age, roster-shape balance, current draft capital, historical lineup efficiency, and scoring stability. It is a decision-support profile, not a dynasty market-value ranking.",
        "teams": profiles,
    }


def transaction_datasets(root: Path) -> list[dict[str, Any]]:
    current = root / "data" / "current"
    history = history_datasets(root / "data" / "history")
    datasets = []
    for data in history:
        if data.get("transactions"):
            datasets.append(data)
    league = read_json(current / "league.json", {}) or {}
    rosters = read_json(current / "roster_index.json", {}) or {}
    transactions = read_json(current / "transactions.json", {}) or {}
    datasets.append({
        "season": str(league.get("season") or ""),
        "league": league,
        "rosters": rosters,
        "transactions": transactions,
    })
    return datasets


def empty_manager(owner_id: str, manager: str | None, team_name: str | None) -> dict[str, Any]:
    return {
        "owner_id": owner_id,
        "manager": manager,
        "team_name": team_name,
        "seasons": set(),
        "trades": 0,
        "trades_initiated": 0,
        "players_acquired_trade": 0,
        "players_sent_trade": 0,
        "picks_acquired": 0,
        "picks_sent": 0,
        "firsts_acquired": 0,
        "firsts_sent": 0,
        "waiver_attempts": 0,
        "waiver_successes": 0,
        "failed_waiver_attempts": 0,
        "faab_spent": 0,
        "free_agent_moves": 0,
        "players_added": 0,
        "players_dropped": 0,
        "trade_partners": defaultdict(int),
    }


def aggregate_transactions(
    datasets: list[dict[str, Any]],
    allowed_seasons: set[str] | None = None,
) -> dict[str, Any]:
    managers: dict[str, dict[str, Any]] = {}

    for data in datasets:
        season = str(data.get("season") or "")
        if allowed_seasons is not None and season not in allowed_seasons:
            continue
        rosters = data.get("rosters") or {}
        roster_owner = {}
        for rid, roster in rosters.items():
            owner = str(roster.get("owner_id") or f"{season}:{rid}")
            roster_owner[str(rid)] = owner
            if owner not in managers:
                managers[owner] = empty_manager(owner, roster.get("display_name"), roster.get("team_name"))
            managers[owner]["manager"] = roster.get("display_name") or managers[owner].get("manager")
            managers[owner]["team_name"] = roster.get("team_name") or managers[owner].get("team_name")
            managers[owner]["seasons"].add(season)

        txs = data.get("transactions") or {}
        for rows in txs.values():
            for tx in rows or []:
                tx_type = tx.get("type")
                status = tx.get("status")
                roster_ids = [str(x) for x in (tx.get("roster_ids") or [])]

                if tx_type == "waiver":
                    for rid in roster_ids:
                        owner = roster_owner.get(rid)
                        if not owner:
                            continue
                        managers[owner]["waiver_attempts"] += 1
                        if status == "complete":
                            managers[owner]["waiver_successes"] += 1
                            managers[owner]["faab_spent"] += int((tx.get("settings") or {}).get("waiver_bid") or 0)
                        elif status == "failed":
                            managers[owner]["failed_waiver_attempts"] += 1

                if status != "complete":
                    continue

                adds = tx.get("adds") or {}
                drops = tx.get("drops") or {}
                if tx_type == "trade":
                    participants = [rid for rid in roster_ids if rid in roster_owner]
                    for rid in participants:
                        owner = roster_owner[rid]
                        managers[owner]["trades"] += 1
                        managers[owner]["players_acquired_trade"] += sum(1 for _, target in adds.items() if str(target) == rid)
                        managers[owner]["players_sent_trade"] += sum(1 for _, target in drops.items() if str(target) == rid)
                        creator = str(tx.get("creator") or "")
                        if creator == owner:
                            managers[owner]["trades_initiated"] += 1
                        for other in participants:
                            if other != rid:
                                partner_owner = roster_owner.get(other)
                                if partner_owner:
                                    managers[owner]["trade_partners"][partner_owner] += 1

                    for pick in tx.get("draft_picks") or []:
                        new_rid = str(pick.get("owner_id"))
                        old_rid = str(pick.get("previous_owner_id"))
                        rnd = int(pick.get("round") or 0)
                        if new_rid in roster_owner:
                            owner = roster_owner[new_rid]
                            managers[owner]["picks_acquired"] += 1
                            if rnd == 1:
                                managers[owner]["firsts_acquired"] += 1
                        if old_rid in roster_owner:
                            owner = roster_owner[old_rid]
                            managers[owner]["picks_sent"] += 1
                            if rnd == 1:
                                managers[owner]["firsts_sent"] += 1

                elif tx_type == "waiver":
                    for rid in roster_ids:
                        owner = roster_owner.get(rid)
                        if owner:
                            managers[owner]["players_added"] += sum(1 for _, target in adds.items() if str(target) == rid)
                            managers[owner]["players_dropped"] += sum(1 for _, target in drops.items() if str(target) == rid)
                elif tx_type == "free_agent":
                    for rid in roster_ids:
                        owner = roster_owner.get(rid)
                        if owner:
                            managers[owner]["free_agent_moves"] += 1
                            managers[owner]["players_added"] += sum(1 for _, target in adds.items() if str(target) == rid)
                            managers[owner]["players_dropped"] += sum(1 for _, target in drops.items() if str(target) == rid)

    return managers


def manager_scope_rows(managers: dict[str, Any]) -> list[dict[str, Any]]:
    if not managers:
        return []
    metrics = {
        "trades": {k: float(v["trades"]) for k, v in managers.items()},
        "moves": {k: float(v["waiver_successes"] + v["free_agent_moves"]) for k, v in managers.items()},
        "faab": {k: float(v["faab_spent"]) for k, v in managers.items()},
        "waiver_attempts": {k: float(v["waiver_attempts"]) for k, v in managers.items()},
    }
    normalized = {name: normalize_map(values) for name, values in metrics.items()}

    rows = []
    for owner, m in managers.items():
        net_firsts = int(m["firsts_acquired"]) - int(m["firsts_sent"])
        moves = int(m["waiver_successes"]) + int(m["free_agent_moves"])
        tags = []
        if m["trades"] >= 3 and normalized["trades"].get(owner, 0) >= 75:
            tags.append("Trade Machine")
        if moves >= 8 and normalized["moves"].get(owner, 0) >= 75:
            tags.append("Roster Tinkerer")
        if m["faab_spent"] >= 20 and normalized["faab"].get(owner, 0) >= 75:
            tags.append("FAAB Burner")
        if m["waiver_attempts"] >= 8 and normalized["waiver_attempts"].get(owner, 0) >= 75:
            tags.append("Waiver Grinder")
        if net_firsts >= 2:
            tags.append("Pick Hoarder")
        elif net_firsts <= -2:
            tags.append("Pick Spender")
        if not tags and m["trades"] <= 1 and moves <= 4:
            tags.append("Hands Off")
        if not tags:
            tags.append("Balanced Operator")

        partners = sorted(m["trade_partners"].items(), key=lambda x: (-x[1], x[0]))
        rows.append({
            "owner_id": owner,
            "manager": m.get("manager"),
            "team_name": m.get("team_name"),
            "seasons": sorted(m["seasons"]),
            "primary_tendency": tags[0],
            "tags": tags[:3],
            "trades": m["trades"],
            "trades_initiated": m["trades_initiated"],
            "players_acquired_trade": m["players_acquired_trade"],
            "players_sent_trade": m["players_sent_trade"],
            "picks_acquired": m["picks_acquired"],
            "picks_sent": m["picks_sent"],
            "firsts_acquired": m["firsts_acquired"],
            "firsts_sent": m["firsts_sent"],
            "net_firsts": net_firsts,
            "waiver_attempts": m["waiver_attempts"],
            "waiver_successes": m["waiver_successes"],
            "failed_waiver_attempts": m["failed_waiver_attempts"],
            "waiver_success_rate": round((m["waiver_successes"] / m["waiver_attempts"]) * 100, 1) if m["waiver_attempts"] else None,
            "faab_spent": m["faab_spent"],
            "free_agent_moves": m["free_agent_moves"],
            "roster_moves": moves,
            "players_added": m["players_added"],
            "players_dropped": m["players_dropped"],
            "top_trade_partners": [{"owner_id": p, "trades": c} for p, c in partners[:3]],
        })
    rows.sort(key=lambda x: (-x["trades"], -x["roster_moves"], x.get("manager") or ""))
    return rows


def build_manager_tendencies(root: Path) -> dict[str, Any]:
    datasets = transaction_datasets(root)
    current_season = str((read_json(root / "data" / "current" / "league.json", {}) or {}).get("season") or "")
    history_tx_seasons = sorted({d["season"] for d in datasets if d["season"] != current_season and d.get("transactions")})
    current = aggregate_transactions(datasets, {current_season})
    all_time = aggregate_transactions(datasets, None)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_season": current_season,
        "historical_transaction_seasons_loaded": history_tx_seasons,
        "methodology": "Behavioral summary from Sleeper transactions. Complete trades, successful/failed waiver claims, FAAB bids, free-agent moves, and draft-pick movement are counted by manager identity. Labels are relative to activity inside 715 and are descriptive, not value judgments.",
        "scopes": {
            "current": {"status": "live", "managers": manager_scope_rows(current)},
            "all_time": {"status": "live", "managers": manager_scope_rows(all_time)},
        },
    }


def update_chatgpt_context(root: Path, playoff: dict[str, Any], profiles: dict[str, Any], tendencies: dict[str, Any]) -> None:
    path = root / "data" / "derived" / "chatgpt_context.json"
    context = read_json(path, {}) or {}
    context["phase4"] = {
        "playoff_simulator": {
            "model_status": playoff.get("model_status"),
            "model_blend": playoff.get("model_blend"),
            "completed_weeks": playoff.get("completed_weeks"),
            "teams": playoff.get("teams"),
        },
        "team_profiles": profiles.get("teams"),
        "manager_tendencies": tendencies.get("scopes"),
    }
    write_json(path, context)


def build_phase4_outputs(root: Path) -> None:
    current = root / "data" / "current"
    derived = root / "data" / "derived"
    league = read_json(current / "league.json", {}) or {}
    rosters = read_json(current / "roster_index.json", {}) or {}
    matchups = read_json(current / "matchups.json", {}) or {}
    nfl_state = read_json(current / "nfl_state.json", {}) or {}
    history = history_datasets(root / "data" / "history")

    playoff = build_playoff_simulator(league, rosters, matchups, nfl_state, history)
    profiles = build_team_profiles(root, playoff)
    tendencies = build_manager_tendencies(root)

    write_json(derived / "playoff_simulator.json", playoff)
    write_json(derived / "team_profiles.json", profiles)
    write_json(derived / "manager_tendencies.json", tendencies)
    update_chatgpt_context(root, playoff, profiles, tendencies)
