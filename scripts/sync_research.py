from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "715-Dynasty-HQ/1.0 (personal research collector)"
MAX_ITEM_AGE_DAYS = 10
CLASSIFIER_VERSION = 2
NEGATIVE = {
    "out": 5, "injured reserve": 5, "ir": 5, "doubtful": 4, "limited": 2,
    "miss practice": 3, "missed practice": 3, "did not practice": 4, "dnp": 4,
    "demoted": 4, "benched": 4, "backup": 2, "committee": 2, "setback": 4,
    "suspended": 5, "waived": 4, "released": 4, "miss week": 4,
    "not debut until": 3,
}
POSITIVE = {
    "full practice": 3, "returned to practice": 3, "cleared": 4, "active": 4,
    "will start": 4, "named starter": 4, "first-team": 3, "lead back": 3,
    "increased role": 3, "more work": 2, "promoted": 3, "activated": 4,
    "goes through drills": 3, "went through drills": 3, "suited up": 3,
    "took the field": 3,
}


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)


def clean_text(value: Any) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def fetch(url: str, headers: dict[str, str] | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read()


def rss_items(payload: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(payload)
    items = []
    for node in root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry"):
        def value(*names: str) -> str | None:
            for name in names:
                child = node.find(name)
                if child is not None:
                    if child.text:
                        return child.text
                    if child.get("href"):
                        return child.get("href")
            return None
        items.append({
            "title": clean_text(value("title", "{http://www.w3.org/2005/Atom}title")),
            "summary": clean_text(value("description", "summary", "content", "{http://www.w3.org/2005/Atom}summary")),
            "url": value("link", "{http://www.w3.org/2005/Atom}link"),
            "published_at": value("pubDate", "published", "updated", "{http://www.w3.org/2005/Atom}updated"),
            "author": clean_text(value("author", "{http://purl.org/dc/elements/1.1/}creator")),
        })
    return items


def fantasypros_items(payload: bytes) -> list[dict[str, Any]]:
    raw = json.loads(payload)
    return [{
        "title": clean_text(row.get("title")),
        "summary": clean_text(row.get("desc")),
        "url": row.get("link"),
        "published_at": row.get("created") or row.get("created_formated"),
        "author": "FantasyPros",
    } for row in raw.get("items") or []]


def relevant_players() -> dict[str, dict[str, Any]]:
    players = read_json(ROOT / "data/current/players_active.json", {}) or {}
    teams = read_json(ROOT / "data/derived/team_assets.json", {}) or {}
    opportunities = read_json(ROOT / "data/derived/opportunity_scanner.json", {}) or {}
    ids = {
        str(p.get("player_id")) for team in teams.values() for p in team.get("players") or [] if p.get("player_id")
    } | {
        str(p.get("player_id")) for p in (opportunities.get("players") or [])[:100] if p.get("player_id")
    }
    return {pid: players[pid] for pid in ids if pid in players}


def match_player(text: str, players: dict[str, dict[str, Any]]) -> tuple[str, str] | None:
    lowered = text.lower()
    matches = []
    for player_id, player in players.items():
        name = str(player.get("full_name") or "").strip()
        if name and re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", lowered):
            matches.append((player_id, name))
    return matches[0] if len(matches) == 1 else None


def classify(text: str) -> tuple[str, str, int, str] | None:
    lowered = text.lower()
    def matches(keyword: str) -> bool:
        return bool(re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", lowered))
    negative = max(((magnitude, keyword) for keyword, magnitude in NEGATIVE.items() if matches(keyword)), default=None)
    positive = max(((magnitude, keyword) for keyword, magnitude in POSITIVE.items() if matches(keyword)), default=None)
    if negative and positive:
        return None
    selected = positive or negative
    if not selected:
        return None
    magnitude, keyword = selected
    direction = 1 if positive else -1
    if any(token in lowered for token in ("practice", "limited", "dnp", "injury", "injured reserve", "cleared", "active", "out", "ir")):
        kind, impact = "practice" if "practice" in lowered or "dnp" in lowered else "injury", "availability"
    elif any(token in lowered for token in ("starter", "first-team", "lead back", "backup", "committee", "role", "more work", "benched")):
        kind, impact = "role", "workload"
    elif any(token in lowered for token in ("waived", "released", "activated", "promoted", "suspended")):
        kind, impact = "news", "availability"
    else:
        kind, impact = "news", "workload"
    return kind, impact, direction, magnitude


def source_attribution(item: dict[str, Any], source: dict[str, Any]) -> str:
    if item.get("author"):
        return str(item["author"])
    summary = str(item.get("summary") or "")
    for pattern in (
        r"according to ([^.]+)",
        r", ([A-Z][^.]{2,80}?) reports(?:\.|$)",
    ):
        match = re.search(pattern, summary)
        if match:
            return f"{source.get('name')} / {match.group(1).strip()}"
    return str(source.get("name") or "Unknown source")


def collect() -> tuple[dict[str, Any], dict[str, Any]]:
    now = datetime.now(timezone.utc)
    players = relevant_players()
    config = read_json(ROOT / "config/research_sources.json", {}) or {}
    existing = read_json(ROOT / "data/external/player_context_reports.json", {}) or {}
    retained = [
        row for row in existing.get("signals") or []
        if parse_date(row.get("published_at")) and parse_date(row.get("published_at")) >= now - timedelta(days=MAX_ITEM_AGE_DAYS)
        and (not row.get("collector_source_id") or row.get("classifier_version") == CLASSIFIER_VERSION)
    ]
    signals_by_id = {str(row.get("signal_id")): row for row in retained if row.get("signal_id")}
    statuses = []
    for source in config.get("sources") or []:
        if not source.get("enabled"):
            continue
        secret_name = source.get("secret_env")
        secret = os.environ.get(str(secret_name)) if secret_name else None
        if secret_name and not secret:
            statuses.append({"id": source.get("id"), "status": "skipped_no_secret", "items": 0})
            continue
        try:
            headers = {"x-api-key": secret} if secret else {}
            payload = fetch(str(source["url"]), headers)
            items = fantasypros_items(payload) if source.get("format") == "fantasypros_json" else rss_items(payload)
            accepted = 0
            for item in items:
                published = parse_date(item.get("published_at"))
                if not published or published < now - timedelta(days=MAX_ITEM_AGE_DAYS):
                    continue
                text = f"{item.get('title') or ''} {item.get('summary') or ''}"
                matched = match_player(text, players)
                classification = classify(text)
                if not matched or not classification:
                    continue
                player_id, name = matched
                kind, impact, direction, magnitude = classification
                stable = f"{source.get('id')}|{player_id}|{item.get('url')}|{item.get('title')}"
                signal_id = hashlib.sha256(stable.encode()).hexdigest()[:20]
                signals_by_id[signal_id] = {
                    "signal_id": signal_id, "player_id": player_id, "name": name,
                    "type": kind, "impact": impact, "direction": direction, "magnitude": magnitude,
                    "source_type": source.get("source_type"), "source": source_attribution(item, source),
                    "url": item.get("url"), "published_at": published.isoformat(),
                    "summary": item.get("title"), "corroboration_count": 1,
                    "collector_source_id": source.get("id"), "source_tier": source.get("tier"),
                    "classifier_version": CLASSIFIER_VERSION,
                }
                accepted += 1
            statuses.append({"id": source.get("id"), "status": "ok", "items": len(items), "accepted": accepted})
        except (OSError, ValueError, ET.ParseError, json.JSONDecodeError, urllib.error.URLError) as exc:
            statuses.append({"id": source.get("id"), "status": "error", "items": 0, "error": str(exc)[:180]})
    signals = sorted(signals_by_id.values(), key=lambda row: row.get("published_at") or "", reverse=True)
    output = {
        "schema_version": "1.0", "generated_at": now.isoformat(),
        "status": "available" if signals else "not_available", "signals": signals,
    }
    status = {
        "generated_at": now.isoformat(), "relevant_players": len(players), "signals_retained": len(signals),
        "sources": statuses,
        "methodology": "Headline-only collection. A report is scored only when exactly one relevant player and an explicit availability/workload phrase match. Ambiguous and opinion-only items are ignored.",
    }
    return output, status


def main() -> None:
    output, status = collect()
    write_json(ROOT / "data/external/player_context_reports.json", output)
    write_json(ROOT / "data/external/research_collector_status.json", status)


if __name__ == "__main__":
    main()
