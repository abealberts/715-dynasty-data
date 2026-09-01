from __future__ import annotations

import unittest
from datetime import datetime, timezone

from scripts.player_context import aggregate_player, manual_signals
from scripts.roster_intelligence import eligible, lineup_bundle, optimize_lineup, projection_for


class DecisionQualityTests(unittest.TestCase):
    def test_unscored_research_is_context_only(self) -> None:
        now = datetime.now(timezone.utc)
        players = {"1": {"full_name": "Test Player"}}
        raw = {"signals": [{
            "player_id": "1", "summary": "Generic analysis", "published_at": now.isoformat(),
            "direction": 1, "magnitude": 5, "source_type": "aggregator", "scored": False,
        }]}
        signals = manual_signals(raw, players, now)
        context = aggregate_player("1", signals)
        self.assertEqual(signals[0]["weighted_score"], 0)
        self.assertEqual(context["weekly_multiplier"], 1.0)
        self.assertEqual(context["opportunity_score_adjustment"], 0)
        self.assertEqual(context["confidence"], "low")
        self.assertEqual(context["research_mention_count"], 1)

    def test_workload_report_is_not_double_counted(self) -> None:
        signal = {
            "signal_id": "role", "player_id": "1", "origin": "curated_report",
            "impact": "workload", "direction": 1, "weighted_score": 0.5,
            "reliability": 0.8, "summary": "Named starter", "type": "role",
        }
        context = aggregate_player("1", [signal])
        self.assertEqual(context["weekly_multiplier"], 1.05)

    def test_proxy_projection_is_never_current_evidence(self) -> None:
        projection = projection_for({"player_id": "1", "position": "RB", "market_value": 5000})
        self.assertEqual(projection["confidence"], "low")
        self.assertFalse(projection["current_decision_evidence"])

    def test_optimizer_produces_unique_legal_lineup(self) -> None:
        players = [
            {"player_id": "q1", "name": "Q1", "position": "QB", "market_value": 5000},
            {"player_id": "q2", "name": "Q2", "position": "QB", "market_value": 4000},
            {"player_id": "r1", "name": "R1", "position": "RB", "market_value": 5000},
            {"player_id": "r2", "name": "R2", "position": "RB", "market_value": 4000},
            {"player_id": "w1", "name": "W1", "position": "WR", "market_value": 5000},
            {"player_id": "t1", "name": "T1", "position": "TE", "market_value": 5000},
        ]
        lineup = optimize_lineup(players, ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"])
        ids = [row["player_id"] for row in lineup]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(eligible(row["slot"], row["position"]) for row in lineup))

    def test_prior_season_swap_requires_research(self) -> None:
        weekly = [{"fantasy_points_715": 20}] * 4
        players = [
            {"player_id": "1", "name": "Starter", "position": "QB", "starter": True,
             "performance": {"ppg_715": 10, "last3_ppg_715": 10, "basis": "prior", "weekly": weekly}},
            {"player_id": "2", "name": "Bench", "position": "QB", "starter": False,
             "performance": {"ppg_715": 20, "last3_ppg_715": 20, "basis": "prior", "weekly": weekly}},
        ]
        team = {"lineup": [{"player_id": "1", "slot_label": "QB"}], "starters": ["1"]}
        changes = lineup_bundle(team, players, ["QB"])["changes"]
        self.assertEqual(changes[0]["decision"], "research_required")


if __name__ == "__main__":
    unittest.main()
