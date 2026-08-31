# 715 Dynasty — Sleeper Sync

This repository keeps a machine-readable snapshot of Sleeper league **715 Dynasty**
(`1312115903088852992`) so ChatGPT or any other analysis tool can read current league
state without manual spreadsheet exports.

## What it syncs

The league workflow runs every 6 hours and can also be run manually. It writes:

- `data/current/league.json` — normalized league settings/scoring
- `data/current/users.json` — manager/team mapping
- `data/current/rosters.json` — current rosters and starters
- `data/current/roster_index.json` — easy roster-ID lookup
- `data/current/traded_picks.json` — Sleeper's raw traded-pick state
- `data/current/pick_ownership.json` — normalized ownership of every pick
- `data/current/transactions.json` — weeks 1–18
- `data/current/matchups.json` — weeks 1–18
- `data/current/drafts.json` and `data/current/drafts/*` — league draft history
- `data/current/nfl_state.json` — current NFL week/season state

A second workflow runs daily and writes:

- `data/current/players_active.json` — active QB/RB/WR/TE player metadata
- `data/current/free_agents.json` — active players not currently rostered in 715 Dynasty

Git history itself acts as the historical snapshot log, so the repo does not create
a new timestamped copy of every file on every run.

## Setup

1. Create a new GitHub repository. **Private** is recommended.
2. Upload the contents of this folder to the repository root.
3. Open the repository's **Actions** tab.
4. Run **Sync Sleeper Players** once manually.
5. Run **Sync Sleeper League** once manually.
6. Confirm that JSON files appear under `data/current/`.

No Sleeper token or GitHub secret is required. Sleeper's API is read-only/public.
The workflows use GitHub's built-in `GITHUB_TOKEN` with `contents: write` permission
to commit refreshed files.

If the workflow cannot push, open:

**Settings → Actions → General → Workflow permissions**

and enable **Read and write permissions** for workflows, then rerun it.

## Schedule

- League state: every 6 hours at minute 17 UTC
- Active players: daily at 08:41 UTC

Both workflows also support `workflow_dispatch`, so you can click **Run workflow**
whenever you want an immediate refresh.

## Using it with ChatGPT

Once a GitHub connector is available and connected, give ChatGPT access to this repo.
Then requests can be as simple as:

- "Refresh my dynasty league and evaluate my roster."
- "Who is actually available at RB?"
- "Compare Nathan's current roster and picks with mine."
- "What changed in the league since yesterday?"
- "Evaluate this trade using the current Sleeper state."

For current NFL news, injuries, depth-chart changes, and dynasty-market values, the
repo should be combined with fresh web research rather than treated as the sole source.

## Local test

Requires Python 3.11+ and no third-party packages:

```bash
python scripts/sync_players.py
python scripts/sync_league.py
```

## Notes

Sleeper recommends being mindful of API frequency. The schedules here are deliberately
conservative. The larger player metadata refresh runs only once per day, while the
smaller league-specific calls run four times per day.
