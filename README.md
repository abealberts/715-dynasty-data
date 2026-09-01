# 715 Dynasty HQ

League data and the static Dynasty HQ decision dashboard.

## Player context reports

`scripts/build_derived.py` automatically converts Sleeper availability/depth data and current-season nflverse usage changes into `data/derived/player_context_signals.json`. Verified news, practice reports, coach statements, and beat reports can be supplied in `data/external/player_context_reports.json`:

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-09-01T12:00:00Z",
  "status": "available",
  "signals": [{
    "player_id": "10859",
    "type": "practice",
    "impact": "availability",
    "direction": 1,
    "magnitude": 3,
    "source_type": "team_reporter",
    "source": "Reporter name",
    "url": "https://example.com/report",
    "published_at": "2026-09-01T11:30:00Z",
    "summary": "Player returned to full practice.",
    "corroboration_count": 1
  }]
}
```

Direction is `-1` to `1`; magnitude is `0` to `5`. Supported source types are `official`, `team`, `team_reporter`, `established_media`, `aggregator`, and `unknown`. Old or invalid reports are ignored. Narrative effects are time-decayed, source-weighted, fully attributable, and capped before they can affect lineup or opportunity scores.

## Scheduled research collector

`.github/workflows/sync-research.yml` runs every four hours and can also be dispatched manually. It collects recent headline-level evidence, rebuilds the decision models, and commits only changed research and analytics files.

The source registry is `config/research_sources.json`. RotoWire RSS and PFF RSS work without credentials. FantasyPros is supported when the repository secret `FANTASYPROS_API_KEY` is configured. FantasySP remains disabled because its documented NFL RSS endpoint returned HTTP 404 during validation.

The collector ignores generic analysis, ambiguous multi-player items, and reports without an explicit availability or workload phrase. A report must match exactly one relevant player before it becomes a scored signal.
