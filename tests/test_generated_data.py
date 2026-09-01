from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class GeneratedDataQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.teams = load("data/derived/team_assets.json")
        cls.opportunities = load("data/derived/opportunity_scanner.json")
        cls.report = load("data/derived/roster_intelligence.json")
        cls.records = load("data/derived/record_book.json")

    def test_roster_players_are_unique_across_league(self) -> None:
        owners: dict[str, str] = {}
        for roster_id, team in self.teams.items():
            for player in team.get("players") or []:
                player_id = str(player["player_id"])
                self.assertNotIn(player_id, owners, f"{player_id} appears on rosters {owners.get(player_id)} and {roster_id}")
                owners[player_id] = roster_id

    def test_opportunities_are_unrostered_and_unique(self) -> None:
        owned = {
            str(player["player_id"])
            for team in self.teams.values()
            for player in team.get("players") or []
        }
        ids = [str(player["player_id"]) for player in self.opportunities.get("players") or []]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(owned.intersection(ids))

    def test_tier_boards_cover_my_roster_exactly_once(self) -> None:
        expected = {
            str(player["player_id"])
            for player in self.teams["3"].get("players") or []
            if player.get("position") in {"QB", "RB", "WR", "TE"}
        }
        actual = [
            str(player["player_id"])
            for board in self.report.get("position_boards") or []
            for tier in board.get("tiers") or []
            for player in tier.get("players") or []
        ]
        self.assertEqual(set(actual), expected)
        self.assertEqual(len(actual), len(set(actual)))

    def test_research_mentions_do_not_masquerade_as_scored_reports(self) -> None:
        coverage = self.report["coverage"]
        self.assertGreaterEqual(coverage["research_mentions"], coverage["actionable_context_reports"])
        if coverage["actionable_context_reports"] == 0:
            self.assertEqual(self.report["data_confidence"]["status"], "provisional")

    def test_lineup_recommendations_require_current_evidence(self) -> None:
        for change in self.report["lineup"]["changes"]:
            if change["decision"] == "consider":
                self.assertTrue(change["current_decision_evidence"])
                self.assertGreaterEqual(change["projected_advantage"], 3)

    def test_record_book_excludes_empty_matchups(self) -> None:
        for key in ("closest_game", "biggest_blowout"):
            game = self.records.get("records", {}).get(key)
            if game:
                self.assertGreater(float(game["a"]["points"]) + float(game["b"]["points"]), 0)


if __name__ == "__main__":
    unittest.main()
