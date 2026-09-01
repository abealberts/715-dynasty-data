const REPO = "abealberts/715-dynasty-data";
const RAW = `https://raw.githubusercontent.com/${REPO}/main/data/derived`;
const MY_ROSTER_ID = "3";

const state = {
  summary: null,
  teams: null,
  waivers: null,
  changes: null,
  transactions: null,
  needs: null,
  tradePartners: null,
  opportunities: null,
  power: null,
  standings: null,
  lineups: null,
  recap: null,
  draftCapital: null,
  records: null,
  playoffs: null,
  profiles: null,
  managerTendencies: null,
  playerIntel: null,
  marketSummary: null,
  dataHealth: null,
  intelligenceHistory: null,
  rosterIntelligence: null,
  rosterIntelligenceHistory: null,
  profileRosterId: MY_ROSTER_ID,
  view: "home",
  tradePartnerId: null,
  analyticsScope: "current",
  recapSeason: null,
  recapWeek: null,
};

async function getJson(name) {
  const res = await fetch(`${RAW}/${name}?t=${Date.now()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${name}: ${res.status}`);
  return res.json();
}

async function getOptionalJson(name, fallback = null) {
  try { return await getJson(name); } catch { return fallback; }
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmtTime(value) {
  if (!value) return "Unknown";
  try { return new Date(value).toLocaleString(); } catch { return value; }
}

function stat(label, value, note = "") {
  return `<article class="stat-card"><div class="stat-label">${esc(label)}</div><div class="stat-value">${esc(value)}</div><div class="stat-note">${esc(note)}</div></article>`;
}

function sourceAttribution(showMarket = true, showPerformance = true) {
  const bits = [];
  if (showMarket) bits.push(`Market values by <a href="https://www.dynastydealer.com/" target="_blank" rel="noopener">Dynasty Dealer</a>`);
  if (showPerformance) bits.push(`NFL performance via <a href="https://nflverse.com/" target="_blank" rel="noopener">nflverse</a>`);
  return `<div class="source-line">${bits.join(" · ")}</div>`;
}

function perfLabel(player) {
  const p = player?.performance;
  if (!p) return "—";
  const basis = p.basis === "current" ? p.basis_label : `${p.basis_label} prior`;
  return `${p.ppg_715 ?? "—"} PPG · ${p.opportunities_per_game ?? "—"} opp/g · ${basis}`;
}

function playerTable(players) {
  if (!players?.length) return `<div class="empty">No players found.</div>`;
  const enriched = players.some(p => p.market_value || p.performance);
  return `<div class="table-wrap"><table>
    <thead><tr><th>Player</th><th>Pos</th><th>NFL</th><th>Age</th><th>Depth</th><th>Status</th>${enriched ? "<th>Market</th><th>Performance</th>" : ""}</tr></thead>
    <tbody>${players.map(p => `<tr>
      <td><span class="player-name">${esc(p.name)}</span> ${p.starter ? '<span class="starter-badge">START</span>' : ''}</td>
      <td><span class="position-tag pos-${esc(p.position || "OTHER")}">${esc(p.position || "—")}</span></td>
      <td>${esc(p.team || "FA")}</td>
      <td>${esc(p.age ?? "—")}</td>
      <td>${esc(p.depth ?? p.depth_chart_order ?? "—")}</td>
      <td class="${p.injury_status ? 'injury' : 'muted'}">${esc(p.injury_status || p.status || "—")}</td>
      ${enriched ? `<td>${p.market_value ? `<strong>${Number(p.market_value).toLocaleString()}</strong><span class="table-note">#${esc(p.market_position_rank ?? "—")} ${esc(p.position || "")}</span>` : "—"}</td><td>${esc(perfLabel(p))}</td>` : ""}
    </tr>`).join("")}</tbody>
  </table></div>${enriched ? sourceAttribution(true, true) : ""}`;
}

function rosterPlayerCard(player, slotLabel = null) {
  if (!player) {
    return `<div class="roster-player empty-slot"><div class="slot-badge">${esc(slotLabel || "OPEN")}</div><div><strong>Open slot</strong><small>No starter submitted</small></div></div>`;
  }
  const perf = player.performance;
  const market = Number(player.market_value || 0);
  return `<div class="roster-player pos-card-${esc(player.position || "OTHER")}">
    <div class="slot-badge">${esc(slotLabel || player.position || "BN")}</div>
    <div class="roster-player-main">
      <div class="roster-player-name">${esc(player.name)}</div>
      <div class="roster-player-meta">
        <span class="position-tag pos-${esc(player.position || "OTHER")}">${esc(player.position || "—")}</span>
        <span>${esc(player.team || "FA")}</span>
        ${player.age != null ? `<span>Age ${esc(player.age)}</span>` : ""}
        ${player.injury_status ? `<span class="injury">${esc(player.injury_status)}</span>` : ""}
      </div>
    </div>
    <div class="roster-player-data">
      <strong class="market-number">${market ? market.toLocaleString() : "—"}</strong>
      <small>${perf ? `${esc(perf.ppg_715)} PPG · ${esc(perf.opportunities_per_game)} opp/g` : "No performance sample"}</small>
    </div>
  </div>`;
}

function rosterBoard(team) {
  if (!team) return `<div class="empty">Roster unavailable.</div>`;
  const lineup = team.lineup || [];
  const bench = team.bench_by_position || {};
  const posOrder = ["QB","RB","WR","TE","OTHER"];

  return `<div class="roster-board">
    <section class="roster-section">
      <div class="roster-section-title"><span>STARTING LINEUP</span><small>${lineup.filter(x => x.player).length}/${lineup.length || 9} filled</small></div>
      <div class="starter-board">${lineup.map(x => rosterPlayerCard(x.player, x.slot_label)).join("")}</div>
    </section>
    <section class="roster-section">
      <div class="roster-section-title"><span>BENCH</span><small>Grouped by position</small></div>
      <div class="bench-groups">${posOrder.filter(pos => (bench[pos] || []).length).map(pos => `
        <div class="bench-group">
          <div class="bench-group-head"><span class="position-tag pos-${pos}">${pos}</span><strong>${(bench[pos] || []).length}</strong></div>
          <div class="bench-player-list">${(bench[pos] || []).map(p => rosterPlayerCard(p, "BN")).join("")}</div>
        </div>`).join("")}</div>
    </section>
    ${sourceAttribution(true, true)}
  </div>`;
}


function picksTable(picks) {
  if (!picks?.length) return `<div class="empty">No picks found.</div>`;
  return `<div class="table-wrap"><table>
    <thead><tr><th>Year</th><th>Round</th><th>Originally</th></tr></thead>
    <tbody>${picks.map(p => `<tr><td>${esc(p.season)}</td><td>R${esc(p.round)}</td><td>${esc(p.original_manager || `Roster ${p.original_roster_id}`)}</td></tr>`).join("")}</tbody>
  </table></div>`;
}

function teamCard(team) {
  const mine = String(team.roster_id) === MY_ROSTER_ID;
  const counts = team.position_counts || {};
  const profile = state.needs?.teams?.[String(team.roster_id)];
  const need = profile?.needs?.[0]?.position;
  const surplus = profile?.surpluses?.[0]?.position;
  return `<article class="team-card ${mine ? 'mine' : ''}">
    <div class="team-name">${esc(team.team_name || team.manager || `Roster ${team.roster_id}`)}</div>
    <div class="team-meta">${esc(team.manager || "Unknown manager")} · ${team.record?.wins ?? 0}-${team.record?.losses ?? 0}</div>
    <div class="position-line">
      ${["QB","RB","WR","TE"].map(pos => `<span class="chip">${pos} ${counts[pos] || 0}</span>`).join("")}
      <span class="chip accent">${team.picks?.length || 0} picks</span>
      <span class="chip">$${team.waivers?.faab_remaining ?? "—"} FAAB</span>
    </div>
    ${(need || surplus) ? `<div class="team-signal">${need ? `Need: <strong>${esc(need)}</strong>` : ""}${need && surplus ? " · " : ""}${surplus ? `Depth: <strong>${esc(surplus)}</strong>` : ""}</div>` : ""}
  </article>`;
}

function opportunityTable(players, limit = 100) {
  if (!players?.length) return `<div class="empty">No matching opportunities.</div>`;
  return `<div class="table-wrap"><table>
    <thead><tr><th>Score</th><th>Player</th><th>Pos</th><th>NFL</th><th>Depth</th><th>24h Adds</th><th>Tier</th><th>Why</th></tr></thead>
    <tbody>${players.slice(0, limit).map(p => `<tr>
      <td><span class="score-badge score-${p.tier === "Priority" ? "high" : p.tier === "Strong stash" ? "mid" : "low"}">${esc(p.opportunity_score)}</span></td>
      <td><span class="player-name">${esc(p.name)}</span><div class="table-note">Age ${esc(p.age ?? "—")}${p.injury_status ? ` · ${esc(p.injury_status)}` : ""}</div></td>
      <td>${esc(p.position || "—")}</td>
      <td>${esc(p.team || "FA")}</td>
      <td>${esc(p.depth ?? "—")}</td>
      <td>${p.trending_adds_24h ? esc(Number(p.trending_adds_24h).toLocaleString()) : "—"}</td>
      <td>${esc(p.tier)}</td>
      <td class="reason-cell">${esc((p.reasons || []).slice(0, 2).join(" "))}</td>
    </tr>`).join("")}</tbody>
  </table></div>`;
}

function renderHome() {
  const s = state.summary;
  const me = state.teams?.[MY_ROSTER_ID];
  const recentChanges = state.changes?.changes || [];
  const tx = state.transactions || [];
  const topOps = (state.opportunities?.players || []).slice(0, 5);
  const partners = state.tradePartners?.partners?.[MY_ROSTER_ID] || [];

  return `
    <div class="stats-grid">
      ${stat("Format", s.superflex ? "Superflex" : "1QB", s.full_ppr ? "Full PPR" : "Custom scoring")}
      ${stat("My FAAB", `$${me?.waivers?.faab_remaining ?? "—"}`, `Waiver priority ${me?.waivers?.waiver_position ?? "—"}`)}
      ${stat("My Picks", me?.picks?.length ?? 0, "Current future picks")}
      ${stat("League Median", s.league_median_match ? "ON" : "OFF", "Extra weekly matchup")}
    </div>

    <div class="grid-2">
      <div>
        <div class="panel">
          <div class="panel-header"><div><h2>Opportunity Board</h2><div class="panel-sub">Top confirmed free-agent signals right now</div></div><button class="button ghost" data-go="opportunities">Open scanner</button></div>
          ${opportunityTable(topOps, 5)}
        </div>
        <div class="panel">
          <div class="panel-header"><div><h2>League Snapshot</h2><div class="panel-sub">All 12 teams at a glance</div></div></div>
          <div class="team-grid">${Object.values(state.teams || {}).map(teamCard).join("")}</div>
        </div>
      </div>
      <div>
        <div class="panel">
          <div class="panel-header"><div><h2>Best Trade Fits</h2><div class="panel-sub">Roster complementarity, not trade value</div></div></div>
          ${partners.slice(0, 5).map(p => `<button class="partner-row" data-partner="${p.roster_id}">
            <span><strong>${esc(p.team_name || p.manager)}</strong><small>${esc(p.manager)}</small></span>
            <span class="fit-score">${esc(p.fit_score)}/10</span>
          </button>`).join("") || '<div class="empty">No partner data yet.</div>'}
        </div>
        <div class="panel">
          <div class="panel-header"><div><h2>Latest Changes</h2><div class="panel-sub">Detected between syncs</div></div></div>
          ${renderChanges(recentChanges.slice(-8).reverse())}
        </div>
        <div class="panel">
          <div class="panel-header"><div><h2>Recent Transactions</h2><div class="panel-sub">Latest Sleeper activity</div></div></div>
          ${renderTransactions(tx.slice(0, 6))}
        </div>
      </div>
    </div>`;
}


function movementLabel(value) {
  if (value > 0) return `<span class="movement up">▲${value}</span>`;
  if (value < 0) return `<span class="movement down">▼${Math.abs(value)}</span>`;
  return `<span class="movement flat">—</span>`;
}

function recordText(record) {
  if (!record) return "0-0";
  return `${record.wins || 0}-${record.losses || 0}${record.ties ? `-${record.ties}` : ""}`;
}

function isMe(row) {
  return String(row?.roster_id) === MY_ROSTER_ID || row?.manager === "abewav";
}

function scopeData(bundle) {
  return bundle?.scopes?.[state.analyticsScope] || null;
}

function scopeToggle() {
  return `<div class="scope-toggle" role="group" aria-label="Analytics scope">
    <button class="scope-button ${state.analyticsScope === "current" ? "active" : ""}" data-scope="current">Current Season</button>
    <button class="scope-button ${state.analyticsScope === "all_time" ? "active" : ""}" data-scope="all_time">All Time</button>
  </div>`;
}

function scopeLabel(data) {
  if (state.analyticsScope === "all_time") {
    const seasons = data?.rankings?.[0]?.seasons || data?.teams?.[0]?.seasons || [];
    return seasons.length ? `All Time · ${seasons.join(" + ")}` : "All Time";
  }
  return data?.latest_season ? `${data.latest_season} Season` : "Current Season";
}

function renderPower() {
  const data = scopeData(state.power);
  const header = `<div class="panel scope-panel"><div><h2>715 Power Rankings</h2><div class="panel-sub">${esc(scopeLabel(data))}</div></div>${scopeToggle()}</div>`;

  if (!data || data.status !== "live" || !data.rankings?.length) {
    return `${header}<div class="notice-card">
      <div class="notice-icon">⚡</div>
      <div><h2>Current-season rankings unlock after Week 1</h2>
      <p>Switch to <strong>All Time</strong> to see the historical ranking immediately. Current-season rankings use recent scoring; all-time rankings use career scoring average.</p></div>
    </div>
    <div class="panel"><div class="method-note">${esc(data?.methodology || "")}</div></div>`;
  }

  return `${header}<div class="panel">
    <div class="method-note">${esc(data.methodology)}</div>
    <div class="table-wrap"><table>
      <thead><tr><th>Rank</th><th>Team</th><th>Power</th>${state.analyticsScope === "all_time" ? "<th>Career Avg</th><th>All-Play</th><th>Median</th><th>Efficiency</th><th>H2H</th>" : "<th>Market</th><th>Starter Value</th><th>Historical Prior</th><th>Live Perf</th><th>H2H</th>"}</tr></thead>
      <tbody>${data.rankings.map(r => `<tr class="${isMe(r) ? "highlight-row" : ""}">
        <td><span class="rank-number">${r.rank}</span> ${movementLabel(r.movement)}</td>
        <td><span class="player-name">${esc(r.team_name || r.manager)}</span><div class="table-note">${esc(r.manager || "")}${r.seasons?.length ? ` · ${esc(r.seasons.join(", "))}` : ""}</div></td>
        <td><span class="power-score">${esc(r.power_score)}</span></td>
        ${state.analyticsScope === "all_time" ? `
          <td>${esc(r.average_score)}</td>
          <td>${recordText(r.all_play)}</td>
          <td>${recordText(r.median)}</td>
          <td>${r.lineup_efficiency == null ? "—" : `${esc(r.lineup_efficiency)}%`}</td>
          <td>${recordText(r.h2h)}</td>` : `
          <td>${r.market_strength != null ? `${esc(r.market_strength)}/100` : "—"}</td>
          <td>${r.starter_market_value ? Number(r.starter_market_value).toLocaleString() : "—"}</td>
          <td>${esc(r.historical_prior_score ?? "—")}</td>
          <td>${esc(r.live_performance_score ?? "—")}</td>
          <td>${recordText(r.h2h)}</td>`}
      </tr>`).join("")}</tbody>
    </table></div>
  </div>`;
}

function renderStandingsPlus() {
  const data = scopeData(state.standings);
  const header = `<div class="panel scope-panel"><div><h2>Standings+</h2><div class="panel-sub">${esc(scopeLabel(data))}</div></div>${scopeToggle()}</div>`;

  if (!data || data.status !== "live" || !data.teams?.length) {
    return `${header}<div class="notice-card"><div class="notice-icon">📊</div><div><h2>Current Standings+ is waiting for Week 1</h2><p>Switch to All Time to compare the 2025 historical performance already imported.</p></div></div>`;
  }

  const luckiest = [...data.teams].sort((a,b) => b.luck_index - a.luck_index)[0];
  const cursed = [...data.teams].sort((a,b) => a.luck_index - b.luck_index)[0];

  return `${header}
    <div class="stats-grid">
      ${stat("Luckiest", luckiest?.team_name || luckiest?.manager || "—", `${luckiest?.luck_index > 0 ? "+" : ""}${luckiest?.luck_index ?? 0} luck index`)}
      ${stat("Most Cursed", cursed?.team_name || cursed?.manager || "—", `${cursed?.luck_index > 0 ? "+" : ""}${cursed?.luck_index ?? 0} luck index`)}
      ${stat("Weeks", data.teams?.[0]?.weeks || 0, state.analyticsScope === "all_time" ? "Career regular-season weeks" : "Completed this season")}
      ${stat("Scope", state.analyticsScope === "all_time" ? "ALL TIME" : "CURRENT", scopeLabel(data))}
    </div>
    <div class="panel">
      <div class="table-wrap"><table>
        <thead><tr><th>Team</th><th>H2H</th><th>Median</th><th>All-Play</th><th>PF</th><th>Avg</th><th>Efficiency</th><th>Luck</th></tr></thead>
        <tbody>${data.teams.map(t => `<tr class="${isMe(t) ? "highlight-row" : ""}">
          <td><span class="player-name">${esc(t.team_name || t.manager)}</span><div class="table-note">${esc(t.manager || "")}</div></td>
          <td>${recordText(t.h2h)}</td>
          <td>${recordText(t.median)}</td>
          <td>${recordText(t.all_play)}</td>
          <td>${esc(t.points_for)}</td>
          <td>${esc(t.average_score)}</td>
          <td>${t.lineup_efficiency == null ? "—" : `${esc(t.lineup_efficiency)}%`}</td>
          <td class="${t.luck_index > 5 ? "luck-good" : t.luck_index < -5 ? "luck-bad" : "muted"}">${t.luck_index > 0 ? "+" : ""}${esc(t.luck_index)}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>`;
}

function renderLineups() {
  const data = scopeData(state.lineups);
  const header = `<div class="panel scope-panel"><div><h2>Lineup Lab</h2><div class="panel-sub">${esc(scopeLabel(data))} · optimal legal lineup analysis</div></div>${scopeToggle()}</div>`;

  if (!data || data.status !== "live" || !data.season?.length) {
    return `${header}<div class="notice-card"><div class="notice-icon">🧠</div><div><h2>Current Lineup Lab is waiting for Week 1</h2><p>All-Time mode reconstructs 2025 legal lineups using historical player IDs and Sleeper player-position metadata.</p></div></div>`;
  }

  const valid = data.season.filter(x => x.lineup_efficiency != null);
  const best = [...valid].sort((a,b) => b.lineup_efficiency - a.lineup_efficiency)[0];
  const regret = [...valid].sort((a,b) => (b.points_left_on_bench || 0) - (a.points_left_on_bench || 0))[0];

  return `${header}
    <div class="stats-grid">
      ${stat("Best Manager", best?.team_name || best?.manager || "—", best ? `${best.lineup_efficiency}% efficiency` : "No valid data")}
      ${stat("Most Bench Regret", regret?.team_name || regret?.manager || "—", regret ? `${regret.points_left_on_bench} points left` : "No valid data")}
      ${stat("Valid Weeks", valid.reduce((n,x) => n + (x.lineup_weeks || 0), 0), "Manager-week samples")}
      ${stat("Scope", state.analyticsScope === "all_time" ? "ALL TIME" : "CURRENT", scopeLabel(data))}
    </div>
    <div class="panel">
      <div class="table-wrap"><table>
        <thead><tr><th>Team</th><th>Efficiency</th><th>Points Left</th><th>Lineup Weeks</th><th>Avg Score</th><th>H2H</th></tr></thead>
        <tbody>${data.season.map(t => `<tr class="${isMe(t) ? "highlight-row" : ""}">
          <td><span class="player-name">${esc(t.team_name || t.manager)}</span><div class="table-note">${esc(t.manager || "")}</div></td>
          <td>${t.lineup_efficiency == null ? "—" : `${esc(t.lineup_efficiency)}%`}</td>
          <td>${t.points_left_on_bench == null ? "—" : esc(t.points_left_on_bench)}</td>
          <td>${esc(t.lineup_weeks || 0)} / ${esc(t.weeks || 0)}</td>
          <td>${esc(t.average_score)}</td>
          <td>${recordText(t.h2h)}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>`;
}

function selectedRecap() {
  const seasons = state.recap?.seasons || {};
  const seasonKeys = Object.keys(seasons).sort().reverse();

  if (!state.recapSeason || !seasons[state.recapSeason]) {
    const current = state.recap?.current_season;
    if (current && seasons[current]?.available_weeks?.length) {
      state.recapSeason = current;
    } else {
      state.recapSeason = seasonKeys.find(s => seasons[s]?.available_weeks?.length) || seasonKeys[0] || null;
    }
  }

  const seasonData = seasons[state.recapSeason];
  const available = seasonData?.available_weeks || [];
  if (!state.recapWeek || !available.includes(Number(state.recapWeek))) {
    state.recapWeek = available.length ? available[available.length - 1] : null;
  }
  return state.recapWeek != null ? seasonData?.weeks?.[String(state.recapWeek)] : null;
}

function recapControls() {
  const seasons = state.recap?.seasons || {};
  const seasonKeys = Object.keys(seasons).sort().reverse();
  const seasonData = state.recapSeason ? seasons[state.recapSeason] : null;
  const weeks = seasonData?.available_weeks || [];
  return `<div class="toolbar">
    <select id="recap-season">${seasonKeys.map(s => `<option value="${esc(s)}" ${s === state.recapSeason ? "selected" : ""}>${esc(s)} Season</option>`).join("")}</select>
    <select id="recap-week">${weeks.map(w => `<option value="${esc(w)}" ${Number(w) === Number(state.recapWeek) ? "selected" : ""}>Week ${esc(w)}</option>`).join("")}</select>
  </div>`;
}

function renderRecap() {
  const data = selectedRecap();
  const controls = recapControls();
  if (!data || data.status !== "live" || !data.week_data) {
    return `<div class="panel scope-panel"><div><h2>Weekly Replay</h2><div class="panel-sub">Browse imported league weeks</div></div>${controls}</div>
      <div class="notice-card"><div class="notice-icon">📰</div><div><h2>No completed week selected</h2><p>The 2025 regular season is available now; 2026 weeks will appear automatically as they complete.</p></div></div>`;
  }

  const week = data.week_data;
  return `
    <div class="panel scope-panel"><div><h2>${esc(data.season)} Week ${esc(data.week)} Replay</h2><div class="panel-sub">The official unofficial 715 weekly paper</div></div>${controls}</div>
    <div class="panel">
      <div class="panel-header"><div><h2>Weekly Awards</h2><div class="panel-sub">Generated from the selected historical week</div></div></div>
      <div class="award-grid">${(data.awards || []).map(a => `<article class="award-card">
        <div class="award-emoji">${esc(a.emoji)}</div>
        <div class="award-title">${esc(a.title)}</div>
        <div class="award-team">${esc(a.team_name || a.manager)}</div>
        <div class="award-detail">${esc(a.detail)}</div>
      </article>`).join("")}</div>
    </div>

    <div class="panel">
      <div class="panel-header"><div><h2>Scoreboard+</h2><div class="panel-sub">Actual vs reconstructed optimal lineup</div></div></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Team</th><th>Score</th><th>H2H</th><th>All-Play</th><th>Optimal</th><th>Efficiency</th><th>Bench Regret</th></tr></thead>
        <tbody>${(week.teams || []).map(t => {
          const star = t.lineup?.bench_star;
          return `<tr class="${isMe(t) ? "highlight-row" : ""}">
            <td><span class="player-name">${esc(t.team_name || t.manager)}</span></td>
            <td>${esc(t.score)}</td>
            <td>${esc(t.h2h?.result || "—")}</td>
            <td>${esc(t.all_play?.wins || 0)}-${esc(t.all_play?.losses || 0)}</td>
            <td>${t.lineup?.optimal_points == null ? "—" : esc(t.lineup.optimal_points)}</td>
            <td>${t.lineup?.efficiency == null ? "—" : `${esc(t.lineup.efficiency)}%`}</td>
            <td>${star ? `${esc(star.name)} (${esc(star.points)})` : "—"}</td>
          </tr>`;
        }).join("")}</tbody>
      </table></div>
      <div class="method-note">Historical optimal-lineup calculations depend on Sleeper retaining position metadata for the players used that season. Missing metadata is shown as unavailable rather than treated as 100% efficiency.</div>
    </div>`;
}

function pickCell(picks) {
  if (!picks?.length) return `<span class="empty-cell">—</span>`;
  return `<div class="pick-cell">${picks.map(p => `<span class="pick-pill ${p.own ? "own" : "acquired"}" title="${esc(p.own ? "Own pick" : `From ${p.original_manager || `Roster ${p.original_roster_id}`}`)}">R${esc(p.round)}${p.own ? "" : "*"}</span>`).join("")}</div>`;
}

function renderDraftCapital() {
  const data = state.draftCapital;
  if (!data?.teams?.length) return `<div class="loading-card">Draft-capital data is not ready.</div>`;
  return `
    <div class="panel">
      <div class="panel-header"><div><h2>Draft Capital Matrix</h2><div class="panel-sub">Current ownership · * = acquired pick · hover for original owner</div></div></div>
      <div class="table-wrap draft-wrap"><table class="draft-matrix">
        <thead><tr><th>Team</th>${(data.years || []).map(y => `<th>${esc(y)}</th>`).join("")}<th>1sts</th><th>1st+2nd</th></tr></thead>
        <tbody>${data.teams.map(t => `<tr class="${isMe(t) ? "highlight-row" : ""}">
          <td><span class="player-name">${esc(t.team_name || t.manager)}</span><div class="table-note">${esc(t.manager || "")}</div></td>
          ${(data.years || []).map(y => `<td>${pickCell(t.years?.[y])}</td>`).join("")}
          <td><strong>${esc(t.summary?.firsts ?? 0)}</strong></td>
          <td>${esc(t.summary?.early_picks ?? 0)}</td>
        </tr>`).join("")}</tbody>
      </table></div>
    </div>
    <div class="method-note">Draft Capital is intentionally current-only: it represents assets available to trade today, not historical pick ownership.</div>`;
}

function gameLabel(game) {
  if (!game) return "Waiting for games";
  const a = game.a, b = game.b;
  return `${a.manager} ${Number(a.points).toFixed(2)} – ${Number(b.points).toFixed(2)} ${b.manager}`;
}

function renderRecords() {
  const data = state.records;
  if (!data) return `<div class="loading-card">Record-book data is not ready.</div>`;
  const r = data.records || {};
  const seasons = data.seasons_loaded || [];
  const hasGames = !!r.highest_week;

  return `
    <div class="panel">
      <div class="panel-header"><div><h2>715 Record Book</h2><div class="panel-sub">All Time · ${seasons.map(x => esc(x.season)).join(", ") || "current season only"}</div></div></div>
      ${!hasGames ? `<div class="empty">No completed games are available yet.</div>` : `
      <div class="record-grid">
        <article class="record-card"><span>🔥 Highest Week</span><strong>${esc(r.highest_week?.points)}</strong><small>${esc(r.highest_week?.manager)} · ${esc(r.highest_week?.season)} W${esc(r.highest_week?.week)}</small></article>
        <article class="record-card"><span>🧊 Lowest Score</span><strong>${esc(r.lowest_nonzero_week?.points)}</strong><small>${esc(r.lowest_nonzero_week?.manager)} · ${esc(r.lowest_nonzero_week?.season)} W${esc(r.lowest_nonzero_week?.week)}</small></article>
        <article class="record-card"><span>🤏 Closest Game</span><strong>${esc(r.closest_game?.margin)}</strong><small>${esc(gameLabel(r.closest_game))}</small></article>
        <article class="record-card"><span>💥 Biggest Blowout</span><strong>${esc(r.biggest_blowout?.margin)}</strong><small>${esc(gameLabel(r.biggest_blowout))}</small></article>
      </div>`}
    </div>

    <div class="panel">
      <div class="panel-header"><div><h2>All-Time Manager Board</h2><div class="panel-sub">Regular-season head-to-head history</div></div></div>
      ${(data.manager_careers || []).length ? `<div class="table-wrap"><table>
        <thead><tr><th>Manager</th><th>W</th><th>L</th><th>T</th><th>Win%</th><th>Points</th><th>Avg</th><th>Seasons</th></tr></thead>
        <tbody>${data.manager_careers.map(m => `<tr class="${m.manager === "abewav" ? "highlight-row" : ""}">
          <td><span class="player-name">${esc(m.manager)}</span></td>
          <td>${esc(m.wins)}</td><td>${esc(m.losses)}</td><td>${esc(m.ties)}</td>
          <td>${(Number(m.win_pct || 0) * 100).toFixed(1)}%</td>
          <td>${esc(m.points_for)}</td><td>${esc(m.average_score)}</td>
          <td>${esc((m.seasons || []).join(", "))}</td>
        </tr>`).join("")}</tbody>
      </table></div>` : `<div class="empty">No historical regular-season games found.</div>`}
    </div>
    <div class="method-note">${esc(data.note || "")}</div>`;
}


function oddsClass(value) {
  const n = Number(value || 0);
  if (n >= 65) return "luck-good";
  if (n <= 25) return "luck-bad";
  return "muted";
}

function renderPlayoffSimulator() {
  const data = state.playoffs;
  if (!data?.teams?.length) return `<div class="loading-card">Playoff model is not ready.</div>`;
  const blend = data.model_blend || {};
  const leader = data.teams[0];
  const mine = data.teams.find(x => String(x.roster_id) === MY_ROSTER_ID);
  return `
    <div class="stats-grid">
      ${stat("Model", data.model_status === "preseason_prior" ? "2025 PRIOR" : data.model_status === "blended" ? "BLENDED" : "2026 LIVE", `${blend.historical_weight ?? 0}% history / ${blend.current_season_weight ?? 0}% 2026`)}
      ${stat("Favorite", leader?.team_name || leader?.manager || "—", `${leader?.playoff_odds ?? 0}% playoffs`)}
      ${stat("Bilge Rats", `${mine?.playoff_odds ?? 0}%`, `${mine?.title_odds ?? 0}% simulated title odds`)}
      ${stat("Playoff Cut", data.average_fourth_seed_standings_wins ?? "—", "Avg standings wins · H2H + median")}
    </div>
    <div class="panel">
      <div class="panel-header"><div><h2>10,000-Season Playoff Simulator</h2><div class="panel-sub">${esc(data.completed_weeks?.length || 0)} completed 2026 weeks · ${esc(data.playoff_teams)} playoff spots</div></div></div>
      <div class="model-blend"><div class="blend-history" style="width:${Number(blend.historical_weight || 0)}%"></div><div class="blend-current" style="width:${Number(blend.current_season_weight || 0)}%"></div></div>
      <div class="blend-labels"><span>Historical prior ${esc(blend.historical_weight ?? 0)}%</span><span>2026 results ${esc(blend.current_season_weight ?? 0)}%</span></div>
      <div class="table-wrap"><table>
        <thead><tr><th>Team</th><th>Playoffs</th><th>#1 Seed</th><th>Title</th><th>Proj Wins</th><th>Model Avg</th><th>Volatility</th></tr></thead>
        <tbody>${data.teams.map(t => `<tr class="${isMe(t) ? "highlight-row" : ""}">
          <td><span class="player-name">${esc(t.team_name || t.manager)}</span><div class="table-note">${esc(t.manager || "")}</div></td>
          <td class="${oddsClass(t.playoff_odds)}"><strong>${esc(t.playoff_odds)}%</strong></td>
          <td>${esc(t.one_seed_odds)}%</td>
          <td>${esc(t.title_odds)}%</td>
          <td>${esc(t.projected_standings_wins)}-${esc(t.projected_standings_losses)}</td>
          <td>${esc(t.model_mean)}</td>
          <td>±${esc(t.model_sd)}</td>
        </tr>`).join("")}</tbody>
      </table></div>
      <div class="method-note">${esc(data.methodology)}</div>
    </div>`;
}

function metricBar(label, value) {
  const n = Math.max(0, Math.min(100, Number(value || 0)));
  return `<div class="profile-metric"><div class="profile-metric-head"><span>${esc(label)}</span><strong>${n.toFixed(1)}</strong></div><div class="profile-bar"><span style="width:${n}%"></span></div></div>`;
}

function renderProfiles() {
  const data = state.profiles;
  if (!data?.teams?.length) return `<div class="loading-card">Team profiles are not ready.</div>`;
  if (!data.teams.some(x => String(x.roster_id) === String(state.profileRosterId))) state.profileRosterId = String(data.teams[0].roster_id);
  const team = data.teams.find(x => String(x.roster_id) === String(state.profileRosterId)) || data.teams[0];
  const m = team.metrics || {};
  return `
    <div class="panel scope-panel"><div><h2>Franchise Profiles</h2><div class="panel-sub">Current roster construction + ${esc(data.model_status === "preseason_prior" ? "2025 performance prior" : "blended performance model")}</div></div>
      <select id="profile-team">${data.teams.map(t => `<option value="${esc(t.roster_id)}" ${String(t.roster_id) === String(team.roster_id) ? "selected" : ""}>${esc(t.team_name || t.manager)}</option>`).join("")}</select>
    </div>
    <div class="profile-hero ${isMe(team) ? "mine-profile" : ""}">
      <div><div class="profile-kicker">${esc(team.window)}</div><h2>${esc(team.team_name || team.manager)}</h2><div class="muted">${esc(team.manager)} · Franchise Score ${esc(team.franchise_score)}</div></div>
      <div class="profile-odds"><strong>${esc(team.playoff_odds)}%</strong><span>playoff odds</span></div>
    </div>
    <div class="profile-layout">
      <div class="panel">
        <div class="panel-header"><div><h2>Profile</h2><div class="panel-sub">Relative 0–100 scores inside 715</div></div></div>
        ${metricBar("Performance Prior", m.performance_prior)}
        ${metricBar("Draft Capital", m.draft_capital)}
        ${metricBar("Youth", m.youth)}
        ${metricBar("Roster Balance", m.roster_balance)}
        ${metricBar("Lineup Management", m.lineup_management)}
        ${metricBar("Stability", m.stability)}
      </div>
      <div class="panel">
        <div class="panel-header"><div><h2>Snapshot</h2><div class="panel-sub">Practical franchise context</div></div></div>
        <div class="profile-facts">
          <div><span>Avg roster age</span><strong>${esc(team.average_roster_age ?? "—")}</strong></div>
          <div><span>Age ≤25</span><strong>${esc(team.young_player_share)}%</strong></div>
          <div><span>Future picks</span><strong>${esc(team.pick_count)}</strong></div>
          <div><span>Future 1sts</span><strong>${esc(team.first_round_picks)}</strong></div>
          <div><span>Title odds</span><strong>${esc(team.title_odds)}%</strong></div>
          <div><span>Scoring model</span><strong>${esc(team.model_mean)}</strong></div>
        </div>
        <div class="profile-notes"><div><span>Strengths</span><strong>${esc((team.strengths || []).join(" · ") || "No standout relative edge")}</strong></div><div><span>Risks</span><strong>${esc((team.risks || []).join(" · ") || "No major relative flag")}</strong></div></div>
      </div>
    </div>
    <div class="method-note">${esc(data.methodology)}</div>`;
}

function renderManagerTendencies() {
  const bundle = state.managerTendencies;
  const data = bundle?.scopes?.[state.analyticsScope];
  const managers = data?.managers || [];
  return `
    <div class="panel scope-panel"><div><h2>Manager Tendencies</h2><div class="panel-sub">Behavior from actual Sleeper transactions</div></div>${scopeToggle()}</div>
    ${state.analyticsScope === "all_time" && !(bundle?.historical_transaction_seasons_loaded || []).length ? `<div class="notice-card"><div class="notice-icon">📦</div><div><h2>Historical transactions need one import</h2><p>Run Sync Sleeper History once after installing Phase 4. Current 2026 tendencies are already available.</p></div></div>` : ""}
    <div class="panel">
      <div class="table-wrap"><table>
        <thead><tr><th>Manager</th><th>Style</th><th>Trades</th><th>Waivers</th><th>FAAB</th><th>Moves</th><th>Net 1sts</th><th>Waiver Hit%</th></tr></thead>
        <tbody>${managers.map(m => `<tr class="${m.manager === "abewav" ? "highlight-row" : ""}">
          <td><span class="player-name">${esc(m.manager)}</span><div class="table-note">${esc((m.tags || []).join(" · "))}</div></td>
          <td><span class="tendency-pill">${esc(m.primary_tendency)}</span></td>
          <td>${esc(m.trades)} <span class="table-note">(${esc(m.trades_initiated)} initiated)</span></td>
          <td>${esc(m.waiver_successes)}/${esc(m.waiver_attempts)}</td>
          <td>$${esc(m.faab_spent)}</td>
          <td>${esc(m.roster_moves)}</td>
          <td class="${Number(m.net_firsts) > 0 ? "luck-good" : Number(m.net_firsts) < 0 ? "luck-bad" : "muted"}">${Number(m.net_firsts) > 0 ? "+" : ""}${esc(m.net_firsts)}</td>
          <td>${m.waiver_success_rate == null ? "—" : `${esc(m.waiver_success_rate)}%`}</td>
        </tr>`).join("")}</tbody>
      </table></div>
      <div class="method-note">${esc(bundle?.methodology || "")}</div>
    </div>`;
}


function renderPlayerIntel() {
  const data = state.playerIntel;
  if (!data?.players?.length) {
    return `<div class="notice-card"><div class="notice-icon">📡</div><div><h2>Player Intelligence feed is waiting for its first sync</h2><p>Run <strong>Sync External Player Intelligence</strong> once. The rest of the dashboard continues to work without it.</p></div></div>`;
  }
  const c = data.coverage || {};
  return `
    <div class="stats-grid">
      ${stat("Market Coverage", c.market_values ?? 0, `${c.relevant_players ?? 0} relevant players`)}
      ${stat("Performance Samples", c.performance_samples ?? 0, "Current or prior-season nflverse")}
      ${stat("Market Source", "Dynasty Dealer", "Daily trade-derived values")}
      ${stat("Performance", "nflverse", "715 scoring + usage")}
    </div>
    <div class="panel">
      <div class="panel-header">
        <div><h2>Player Intelligence Feed</h2><div class="panel-sub">Market value + actual NFL usage and production</div></div>
        <div class="toolbar">
          <select id="intel-pos"><option value="ALL">All positions</option><option>QB</option><option>RB</option><option>WR</option><option>TE</option></select>
          <select id="intel-owner"><option value="ALL">All players</option><option value="ROSTERED">Rostered</option><option value="AVAILABLE">Available</option></select>
          <input id="intel-search" class="search" type="search" placeholder="Search player or NFL team" />
        </div>
      </div>
      <div id="intel-results"></div>
      ${sourceAttribution(true, true)}
    </div>`;
}

function filteredIntel() {
  const pos = document.querySelector("#intel-pos")?.value || "ALL";
  const owner = document.querySelector("#intel-owner")?.value || "ALL";
  const q = (document.querySelector("#intel-search")?.value || "").trim().toLowerCase();
  let rows = state.playerIntel?.players || [];
  if (pos !== "ALL") rows = rows.filter(x => x.position === pos);
  if (owner === "ROSTERED") rows = rows.filter(x => !!x.ownership);
  if (owner === "AVAILABLE") rows = rows.filter(x => !x.ownership);
  if (q) rows = rows.filter(x => `${x.name} ${x.team || ""} ${x.ownership?.manager || ""}`.toLowerCase().includes(q));
  return rows;
}

function updateIntel() {
  const target = document.querySelector("#intel-results");
  if (!target) return;
  const rows = filteredIntel().slice(0, 300);
  target.innerHTML = `<div class="table-wrap"><table>
    <thead><tr><th>Player</th><th>Owner</th><th>Market</th><th>Market Rank</th><th>715 PPG</th><th>Opp/G</th><th>Snap%</th><th>Basis</th></tr></thead>
    <tbody>${rows.map(x => {
      const p = x.performance || {};
      return `<tr class="${String(x.ownership?.roster_id) === MY_ROSTER_ID ? "highlight-row" : ""}">
        <td><span class="player-name">${esc(x.name)}</span><div class="table-note"><span class="position-tag pos-${esc(x.position || "OTHER")}">${esc(x.position || "—")}</span> ${esc(x.team || "FA")} · age ${esc(x.age ?? "—")}</div></td>
        <td>${esc(x.ownership?.team_name || x.ownership?.manager || "FREE AGENT")}</td>
        <td><strong>${x.market_value ? Number(x.market_value).toLocaleString() : "—"}</strong></td>
        <td>${x.market_rank ? `#${esc(x.market_rank)} · #${esc(x.market_position_rank)} ${esc(x.position)}` : "—"}</td>
        <td>${esc(p.ppg_715 ?? "—")}</td>
        <td>${esc(p.opportunities_per_game ?? "—")}</td>
        <td>${p.offense_snap_pct != null ? `${esc(p.offense_snap_pct)}%` : "—"}</td>
        <td>${p.basis ? `${esc(p.basis_label)} ${p.basis === "prior" ? "prior" : "current"}` : "—"}</td>
      </tr>`;
    }).join("")}</tbody>
  </table></div>`;
}


function rosterIntelList(items, fallback) {
  if (!items?.length) return `<div class="ri-unavailable">${esc(fallback)}</div>`;
  return `<ul class="ri-list">${items.map(item => `<li>${esc(item)}</li>`).join("")}</ul>`;
}

function rosterIntelMovement(movement) {
  if (!movement?.has_previous) return `<span class="ri-move flat">NEW BASELINE</span>`;
  const value = Number(movement.value_change || 0);
  const rank = Number(movement.position_rank_change || 0);
  const direction = value > 0 || rank > 0 ? "up" : value < 0 || rank < 0 ? "down" : "flat";
  const valueText = value ? `${value > 0 ? "+" : ""}${value.toLocaleString()} value` : "value flat";
  const rankText = rank ? ` · ${rank > 0 ? "▲" : "▼"}${Math.abs(rank)} roster rank` : "";
  const tierText = movement.tier_changed ? ` · T${esc(movement.tier_from)}→T${esc(movement.tier_to)}` : "";
  return `<span class="ri-move ${direction}">${esc(valueText)}${rankText}${tierText}</span>`;
}

function rosterIntelPlayerCard(player) {
  const value = player.current_fantasy_value || {};
  const projection = value.projection || {};
  const trends = player.trends || {};
  const outlook = player.speculative_outlook || {};
  const comparisons = player.app_data_comparisons || [];
  return `<details class="ri-player-card">
    <summary>
      <span class="ri-player-rank">${esc(player.position_rank_on_roster)}</span>
      <span class="ri-player-identity">
        <strong>${esc(player.name)}</strong>
        <small>${esc(player.team || "NFL FA")} · Age ${esc(player.age ?? "—")}${player.injury_status ? ` · <em>${esc(player.injury_status)}</em>` : ""}</small>
      </span>
      <span class="ri-player-value"><strong>${Number(value.market_value || 0).toLocaleString()}</strong><small>${esc(projection.points ?? "—")} proj</small></span>
      ${rosterIntelMovement(player.movement)}
      <span class="ri-expand" aria-hidden="true">＋</span>
    </summary>
    <div class="ri-player-body">
      <div class="ri-detail-grid">
        <section>
          <h4>Current fantasy value</h4>
          <div class="ri-value-line"><strong>${Number(value.market_value || 0).toLocaleString()}</strong><span>#${esc(value.market_position_rank ?? "—")} ${esc(player.position)} market · ${esc(projection.points ?? "—")} evidence pts</span></div>
          <p>${esc(projection.basis || "Projection basis unavailable.")} <span class="ri-confidence">${esc(projection.confidence || "low")} confidence</span></p>
        </section>
        <section>
          <h4>Speculative outlook</h4>
          <div class="ri-outlook-label">${esc(outlook.label || "Unrated")}</div>
          <p>${esc(outlook.summary || "No speculative outlook is available.")}</p>
        </section>
        <section>
          <h4>Trends</h4>
          <p>${esc(trends.summary || "Trend sample unavailable.")}</p>
          <div class="ri-deltas"><span>PPG ${trends.ppg_delta == null ? "—" : `${trends.ppg_delta > 0 ? "+" : ""}${esc(trends.ppg_delta)}`}</span><span>Opp/G ${trends.opportunity_delta == null ? "—" : `${trends.opportunity_delta > 0 ? "+" : ""}${esc(trends.opportunity_delta)}`}</span></div>
        </section>
        <section>
          <h4>App-data comparison</h4>
          <div class="ri-comparisons">${comparisons.map(row => `<div><span>${esc(row.source)} · ${esc(row.label)}</span><strong>${esc(row.value)}</strong></div>`).join("") || '<div class="ri-unavailable">No app comparison is available.</div>'}</div>
        </section>
      </div>
      <div class="ri-research-grid">
        <section><h4>Key evidence</h4>${rosterIntelList(player.key_evidence, "No supporting evidence is available.")}</section>
        <section><h4>News</h4>${rosterIntelList(player.news, "No verified player news is stored in this report.")}</section>
        <section><h4>Coach / beat-reporter information</h4>${rosterIntelList(player.coach_beat_reporter_information, "No verified coach or beat-reporter note is stored in this report.")}</section>
        <section><h4>Notable takeaways</h4>${rosterIntelList(player.notable_takeaways, "No additional takeaway is available.")}</section>
      </div>
    </div>
  </details>`;
}

function rosterIntelLineupColumn(title, subtitle, rows) {
  return `<section class="ri-lineup-column">
    <div class="ri-lineup-head"><h3>${esc(title)}</h3><span>${esc(subtitle)}</span></div>
    <div class="ri-lineup-list">${(rows || []).map(row => `<div class="ri-lineup-row">
      <span class="slot-badge">${esc(row.slot_label)}</span>
      <span><strong>${esc(row.name)}</strong><small>${esc(row.position || "—")} · ${esc(row.team || "NFL FA")} · ${esc(row.confidence || "low")} confidence</small></span>
      <strong class="ri-projection">${esc(row.projected_points ?? "—")}</strong>
    </div>`).join("")}</div>
  </section>`;
}

function renderRosterIntelligence() {
  const data = state.rosterIntelligence;
  if (!data) {
    return `<div class="notice-card"><div class="notice-icon">🧭</div><div><h2>Roster Intelligence is waiting for a report</h2><p>Run the derived-data build to create roster_intelligence.json. The rest of Dynasty HQ remains available.</p></div></div>`;
  }
  const coverage = data.coverage || {};
  const lineup = data.lineup || {};
  const changes = lineup.changes || [];
  const movers = (data.movement || []).filter(row => row.has_previous);
  const historyCount = state.rosterIntelligenceHistory?.entries?.length || 0;
  return `
    <div class="ri-report-strip">
      <span>REPORT ${esc(data.season || "—")} · WEEK ${esc(data.week ?? "—")}</span>
      <strong>${esc(data.roster?.team_name || data.roster?.manager || "My roster")}</strong>
      <small>${esc(fmtTime(data.generated_at))}</small>
    </div>
    <div class="stats-grid ri-stats">
      ${stat("Roster Coverage", `${coverage.roster_players ?? 0}/${data.roster?.player_count ?? 0}`, "Players on tier boards")}
      ${stat("Evidence Projection", lineup.optimized_projected_points ?? "—", `${lineup.projected_advantage > 0 ? "+" : ""}${lineup.projected_advantage ?? 0} vs current lineup`)}
      ${stat("Priority Actions", data.action_board?.length ?? 0, "Rated on a 1–10 scale")}
      ${stat("Research Coverage", `${coverage.news_players ?? 0} news · ${coverage.coach_beat_reporter_players ?? 0} coach`, coverage.research_status === "available" ? "Verified research loaded" : "Unavailable fields degrade safely")}
    </div>

    <div class="panel ri-lineup-panel">
      <div class="panel-header"><div><h2>Weekly Lineup Decision</h2><div class="panel-sub">Current submission beside the highest-scoring legal evidence lineup</div></div><div class="ri-advantage">${lineup.projected_advantage > 0 ? "+" : ""}${esc(lineup.projected_advantage ?? 0)}<small>projected advantage</small></div></div>
      <div class="ri-lineup-grid">
        ${rosterIntelLineupColumn("Current lineup", `${lineup.current_projected_points ?? "—"} evidence points`, lineup.current)}
        ${rosterIntelLineupColumn("Optimized lineup", `${lineup.optimized_projected_points ?? "—"} evidence points`, lineup.optimized)}
      </div>
      <div class="ri-lineup-reasons">${changes.length ? changes.map(change => `<div><strong>${esc(change.start)} over ${esc(change.sit)}</strong><span>${esc(change.explanation)} Projected edge: ${change.projected_advantage > 0 ? "+" : ""}${esc(change.projected_advantage)}.</span></div>`).join("") : '<div><strong>No swap indicated</strong><span>The submitted starters already match the optimized player set.</span></div>'}</div>
      <div class="method-note">${esc(lineup.methodology || "")}</div>
    </div>

    <div class="panel">
      <div class="panel-header"><div><h2>Positional Tier Boards</h2><div class="panel-sub">Every tracked roster player · expand any card for the full dossier</div></div></div>
      <div class="ri-position-grid">${(data.position_boards || []).map(board => `<section class="ri-position-board">
        <div class="ri-position-head"><span class="position-tag pos-${esc(board.position)}">${esc(board.position)}</span><strong>${esc(board.player_count)} players</strong></div>
        ${(board.tiers || []).map(tier => `<div class="ri-tier-group tier-${esc(tier.number)}"><div class="ri-tier-head"><span>TIER ${esc(tier.number)}</span><strong>${esc(tier.label)}</strong><small>${tier.players?.length || 0}</small></div>${(tier.players || []).map(rosterIntelPlayerCard).join("")}</div>`).join("")}
      </section>`).join("")}</div>
    </div>

    <div class="grid-2 even ri-bottom-grid">
      <div class="panel">
        <div class="panel-header"><div><h2>Action Board</h2><div class="panel-sub">Recommended roster decisions, highest priority first</div></div></div>
        <div class="ri-action-list">${(data.action_board || []).map(action => `<article class="ri-action-card priority-${Math.ceil(Number(action.priority || 0) / 3)}">
          <div class="ri-priority"><strong>${esc(action.priority)}</strong><span>/10</span></div>
          <div><small>${esc(action.category)}</small><h3>${esc(action.title)}</h3><p>${esc(action.recommendation)}</p><div>${esc(action.rationale || "No rationale available.")}</div></div>
        </article>`).join("") || '<div class="empty">No roster moves are recommended from the available evidence.</div>'}</div>
      </div>
      <div class="panel">
        <div class="panel-header"><div><h2>Report Movement</h2><div class="panel-sub">Current report compared with ${data.previous_report?.available ? fmtTime(data.previous_report.generated_at) : "the first captured baseline"} · ${esc(historyCount)} snapshots retained</div></div></div>
        <div class="ri-movement-list">${movers.length ? movers.map(row => `<div><span><strong>${esc(row.name)}</strong><small>${esc(row.position)}</small></span>${rosterIntelMovement(row)}</div>`).join("") : '<div class="empty">No previous report is available yet. This run establishes the baseline.</div>'}</div>
      </div>
    </div>
    <div class="source-line">${(data.source_notes || []).map(esc).join(" · ")}</div>`;
}


function renderTeam() {
  const me = state.teams?.[MY_ROSTER_ID];
  const profile = state.needs?.teams?.[MY_ROSTER_ID];
  if (!me) return `<div class="loading-card">Roster 3 was not found.</div>`;

  const signals = ["QB","RB","WR","TE"].map(pos => {
    const x = profile?.positions?.[pos];
    return `<div class="shape-card"><span>${pos}</span><strong>${x?.count ?? 0}</strong><small>${esc(x?.label || "")} · avg ${esc(x?.league_average ?? "—")}</small></div>`;
  }).join("");

  return `
    <div class="stats-grid">
      ${stat("Record", `${me.record?.wins ?? 0}-${me.record?.losses ?? 0}`, me.team_name || me.manager)}
      ${stat("FAAB", `$${me.waivers?.faab_remaining ?? "—"}`, `$${me.waivers?.faab_used ?? 0} used`)}
      ${stat("Rostered", me.players?.length ?? 0, "Players")}
      ${stat("Picks", me.picks?.length ?? 0, "Future draft assets")}
    </div>
    <div class="panel"><div class="panel-header"><div><h2>Roster Shape</h2><div class="panel-sub">Count vs league average; this does not grade player quality</div></div></div><div class="shape-grid">${signals}</div></div>
    <div class="grid-2">
      <div class="panel"><div class="panel-header"><div><h2>Roster</h2><div class="panel-sub">Starters highlighted</div></div></div>${rosterBoard(me)}</div>
      <div class="panel"><div class="panel-header"><div><h2>Draft Capital</h2><div class="panel-sub">Picks currently owned</div></div></div>${picksTable(me.picks)}</div>
    </div>`;
}

function partnerOptions() {
  const partners = state.tradePartners?.partners?.[MY_ROSTER_ID] || [];
  return partners.map(p => `<option value="${p.roster_id}" ${String(p.roster_id) === String(state.tradePartnerId) ? "selected" : ""}>${esc(p.team_name || p.manager)} — ${esc(p.fit_score)}/10 fit</option>`).join("");
}

function renderTradeFinder() {
  const partners = state.tradePartners?.partners?.[MY_ROSTER_ID] || [];
  if (!state.tradePartnerId && partners.length) state.tradePartnerId = String(partners[0].roster_id);
  const partner = partners.find(p => String(p.roster_id) === String(state.tradePartnerId));
  const me = state.teams?.[MY_ROSTER_ID];
  const them = partner ? state.teams?.[String(partner.roster_id)] : null;
  const myProfile = state.needs?.teams?.[MY_ROSTER_ID];
  const theirProfile = partner ? state.needs?.teams?.[String(partner.roster_id)] : null;

  if (!partner || !them) return `<div class="loading-card">Trade partner data is not ready.</div>`;

  const posRows = ["QB","RB","WR","TE"].map(pos => {
    const mine = myProfile?.positions?.[pos];
    const theirs = theirProfile?.positions?.[pos];
    return `<tr>
      <td><strong>${pos}</strong></td>
      <td>${mine?.count ?? 0} <span class="table-note">${esc(mine?.label || "")}</span></td>
      <td>${esc(mine?.league_average ?? "—")}</td>
      <td>${theirs?.count ?? 0} <span class="table-note">${esc(theirs?.label || "")}</span></td>
    </tr>`;
  }).join("");

  const prompt = `Analyze trade opportunities between my 715 Dynasty roster (abewav, roster 3) and ${partner.manager || partner.team_name}, roster ${partner.roster_id}. First read the latest GitHub league data. Identify realistic targets from their roster that fit my team, what they are likely to want from me, and give 3 realistic offer ladders. Verify current NFL news and dynasty market values before recommending a deal.`;

  return `
    <div class="panel trade-toolbar">
      <div><h2>Choose a manager</h2><div class="panel-sub">Fit score measures roster complementarity only—not fairness or KTC value.</div></div>
      <div class="toolbar">
        <select id="trade-partner">${partnerOptions()}</select>
        <button class="button" data-copy="${esc(prompt)}">Copy ChatGPT analysis prompt</button>
      </div>
    </div>

    <div class="stats-grid">
      ${stat("Partner Fit", `${partner.fit_score}/10`, "Roster/pick complementarity")}
      ${stat("Their 1sts", partner.pick_summary?.firsts ?? 0, `${partner.pick_summary?.early_picks ?? 0} total 1sts + 2nds`)}
      ${stat("Their Picks", them.picks?.length ?? 0, "Future draft assets")}
      ${stat("Their FAAB", `$${them.waivers?.faab_remaining ?? "—"}`, them.team_name || them.manager)}
    </div>

    <div class="grid-2 even">
      <div class="panel">
        <div class="panel-header"><div><h2>Why this fit</h2><div class="panel-sub">${esc(partner.team_name || partner.manager)}</div></div></div>
        <div class="reason-list">${(partner.reasons || []).map(r => `<div class="reason">${esc(r)}</div>`).join("")}</div>
      </div>
      <div class="panel">
        <div class="panel-header"><div><h2>Roster Shape Comparison</h2><div class="panel-sub">Counts, not talent grades</div></div></div>
        <div class="table-wrap"><table><thead><tr><th>Pos</th><th>Me</th><th>Lg Avg</th><th>Them</th></tr></thead><tbody>${posRows}</tbody></table></div>
      </div>
    </div>

    <div class="grid-2 even">
      <div class="panel"><div class="panel-header"><div><h2>Their Roster</h2><div class="panel-sub">Targets to research</div></div></div>${rosterBoard(them)}</div>
      <div class="panel"><div class="panel-header"><div><h2>Their Draft Capital</h2><div class="panel-sub">Current ownership</div></div></div>${picksTable(them.picks)}</div>
    </div>`;
}

function renderOpportunities() {
  return `
    <div class="panel">
      <div class="panel-header">
        <div><h2>Opportunity Scanner</h2><div class="panel-sub">Confirmed free agents ranked by asymmetric-upside signals; not a dynasty value ranking</div></div>
        <div class="toolbar">
          <select id="opp-pos"><option value="ALL">All</option><option value="RB" selected>RB</option><option value="WR">WR</option><option value="TE">TE</option><option value="QB">QB</option></select>
          <select id="opp-tier"><option value="ALL">All tiers</option><option>Priority</option><option>Strong stash</option><option>Watch</option><option>Deep</option></select>
          <input id="opp-search" class="search" type="search" placeholder="Search player or NFL team" />
          <button class="button" id="copy-opp">Copy top-opportunities prompt</button>
        </div>
      </div>
      <div class="method-note">${esc(state.opportunities?.methodology || "")}</div>
      <div id="opp-results"></div>
      <div class="attribution">Trending add/drop data provided by Sleeper.</div>
    </div>`;
}

function filteredOpportunities() {
  const pos = document.querySelector("#opp-pos")?.value || "RB";
  const tier = document.querySelector("#opp-tier")?.value || "ALL";
  const q = (document.querySelector("#opp-search")?.value || "").trim().toLowerCase();
  let players = state.opportunities?.players || [];
  if (pos !== "ALL") players = players.filter(p => p.position === pos);
  if (tier !== "ALL") players = players.filter(p => p.tier === tier);
  if (q) players = players.filter(p => `${p.name} ${p.team || ""}`.toLowerCase().includes(q));
  return players;
}

function updateOpportunities() {
  const target = document.querySelector("#opp-results");
  if (target) target.innerHTML = opportunityTable(filteredOpportunities(), 250);
}

function renderWaivers() {
  const all = state.waivers || {};
  return `
    <div class="panel">
      <div class="panel-header">
        <div><h2>Available Players</h2><div class="panel-sub">Raw confirmed availability; use Opportunities for the signal-ranked board</div></div>
        <div class="toolbar">
          <select id="pos-filter"><option>RB</option><option>WR</option><option>TE</option><option>QB</option></select>
          <input id="waiver-search" class="search" type="search" placeholder="Search player or NFL team" />
        </div>
      </div>
      <div id="waiver-results"></div>
    </div>`;
}

function updateWaivers() {
  const pos = document.querySelector("#pos-filter")?.value || "RB";
  const q = (document.querySelector("#waiver-search")?.value || "").trim().toLowerCase();
  let players = state.waivers?.[pos] || [];
  if (q) players = players.filter(p => `${p.name} ${p.team || ""}`.toLowerCase().includes(q));
  const target = document.querySelector("#waiver-results");
  if (target) target.innerHTML = playerTable(players.slice(0, 250));
}

function renderLeague() {
  return `<div class="panel"><div class="panel-header"><div><h2>League Assets</h2><div class="panel-sub">Roster construction, FAAB and pick inventory</div></div></div>
    <div class="team-grid">${Object.values(state.teams || {}).map(teamCard).join("")}</div>
  </div>`;
}

function renderChanges(changes) {
  if (!changes?.length) return `<div class="empty">No changes detected in the latest sync window.</div>`;
  return `<div class="change-list">${changes.map(c => {
    let text = c.type;
    if (c.type === "roster_add") text = `${c.manager || `Roster ${c.roster_id}`} added ${c.player?.name || "a player"}`;
    if (c.type === "roster_drop") text = `${c.manager || `Roster ${c.roster_id}`} dropped ${c.player?.name || "a player"}`;
    if (c.type === "starter_change") text = `${c.manager || `Roster ${c.roster_id}`} changed starters`;
    if (c.type === "pick_owner_change") text = `${c.season} R${c.round} pick moved to ${c.new_owner_manager || `Roster ${c.new_owner_roster_id}`}`;
    return `<div class="change"><div>${esc(text)}</div><div class="change-time">${esc(fmtTime(c.detected_at))}</div></div>`;
  }).join("")}</div>`;
}

function renderTransactions(items) {
  if (!items?.length) return `<div class="empty">No transactions found.</div>`;
  return `<div class="change-list">${items.map(tx => {
    const adds = (tx.adds || []).map(x => x.player?.name).filter(Boolean).join(", ");
    const drops = (tx.drops || []).map(x => x.player?.name).filter(Boolean).join(", ");
    const bits = [adds ? `+ ${adds}` : "", drops ? `− ${drops}` : ""].filter(Boolean).join(" · ");
    return `<div class="change"><div><strong>${esc(tx.type || "transaction")}</strong>${bits ? ` — ${esc(bits)}` : ""}</div><div class="change-time">Week ${esc(tx.week)} · ${esc(tx.status || "")}</div></div>`;
  }).join("")}</div>`;
}

function renderActivity() {
  return `<div class="grid-2">
    <div class="panel"><div class="panel-header"><div><h2>Recent Transactions</h2><div class="panel-sub">Sleeper transaction feed</div></div></div>${renderTransactions((state.transactions || []).slice(0, 50))}</div>
    <div class="panel"><div class="panel-header"><div><h2>Detected Asset Changes</h2><div class="panel-sub">Roster, starter and pick changes</div></div></div>${renderChanges((state.changes?.changes || []).slice().reverse())}</div>
  </div>`;
}

async function copyText(text, button) {
  try {
    await navigator.clipboard.writeText(text);
    const old = button.textContent;
    button.textContent = "Copied";
    setTimeout(() => button.textContent = old, 1300);
  } catch {
    window.prompt("Copy this prompt:", text);
  }
}

function wireViewControls() {
  document.querySelector("#profile-team")?.addEventListener("change", e => {
    state.profileRosterId = e.target.value;
    render();
  });
  document.querySelectorAll("[data-scope]").forEach(btn => btn.addEventListener("click", () => {
    state.analyticsScope = btn.dataset.scope;
    render();
  }));

  document.querySelector("#recap-season")?.addEventListener("change", e => {
    state.recapSeason = e.target.value;
    const available = state.recap?.seasons?.[state.recapSeason]?.available_weeks || [];
    state.recapWeek = available.length ? available[available.length - 1] : null;
    render();
  });

  document.querySelector("#recap-week")?.addEventListener("change", e => {
    state.recapWeek = Number(e.target.value);
    render();
  });

  document.querySelectorAll("[data-go]").forEach(btn => btn.addEventListener("click", () => {
    state.view = btn.dataset.go;
    setActiveNav();
    render();
  }));

  document.querySelectorAll(".partner-row").forEach(btn => btn.addEventListener("click", () => {
    state.tradePartnerId = btn.dataset.partner;
    state.view = "trades";
    setActiveNav();
    render();
  }));

  document.querySelector("#trade-partner")?.addEventListener("change", e => {
    state.tradePartnerId = e.target.value;
    render();
  });

  document.querySelectorAll("[data-copy]").forEach(btn => btn.addEventListener("click", () => copyText(btn.dataset.copy, btn)));

  if (state.view === "waivers") {
    document.querySelector("#pos-filter")?.addEventListener("change", updateWaivers);
    document.querySelector("#waiver-search")?.addEventListener("input", updateWaivers);
    updateWaivers();
  }

  if (state.view === "intel") {
    ["#intel-pos", "#intel-owner"].forEach(sel => document.querySelector(sel)?.addEventListener("change", updateIntel));
    document.querySelector("#intel-search")?.addEventListener("input", updateIntel);
    updateIntel();
  }

  if (state.view === "opportunities") {
    ["#opp-pos", "#opp-tier"].forEach(sel => document.querySelector(sel)?.addEventListener("change", updateOpportunities));
    document.querySelector("#opp-search")?.addEventListener("input", updateOpportunities);
    document.querySelector("#copy-opp")?.addEventListener("click", e => {
      const top = filteredOpportunities().slice(0, 10).map(p => `${p.name} (${p.position}, ${p.team || "NFL FA"})`).join(", ");
      const prompt = `Evaluate these currently available 715 Dynasty waiver/stash options using the latest GitHub league data and current web research: ${top}. Rank them specifically for my roster and competitive window, identify likely cuts, and flag any asymmetric upside.`;
      copyText(prompt, e.currentTarget);
    });
    updateOpportunities();
  }
}

function setActiveNav() {
  document.querySelectorAll(".nav-item").forEach(x => x.classList.toggle("active", x.dataset.view === state.view));
}

function render() {
  const app = document.querySelector("#app");
  const titles = {
    home: ["Overview", "Live 715 Dynasty league state"],
    team: ["My Team", "Baskerville Bilge Rats"],
    "roster-intelligence": ["Roster Intelligence", "Weekly tiers, lineup edge and roster actions"],
    trades: ["Trade Finder", "Find roster-construction matches before doing market research"],
    opportunities: ["Opportunities", "Signal-ranked, confirmed free agents"],
    power: ["Power Rankings", "Performance-based 715 Power Score"],
    recap: ["Weekly Recap", "Awards, lineup decisions and bench regret"],
    standings: ["Standings+", "All-play, median record and luck index"],
    lineups: ["Lineup Lab", "Optimal lineups and bench regret"],
    playoffs: ["Playoff Simulator", "10,000 simulated 715 seasons"],
    profiles: ["Team Profiles", "Franchise outlook and roster construction"],
    managers: ["Manager Tendencies", "How 715 managers actually behave"],
    draft: ["Draft Capital", "Future pick ownership across the league"],
    records: ["Records", "715 Dynasty history and all-time marks"],
    waivers: ["Waivers", "Confirmed available players"],
    league: ["League", "Roster and asset map"],
    activity: ["Activity", "Adds, drops, trades and detected changes"],
    intel: ["Player Intel", "Dynasty market + NFL performance feed"],
  };
  document.querySelector("#page-title").textContent = titles[state.view][0];
  document.querySelector("#page-subtitle").textContent = titles[state.view][1];

  if (state.view === "home") app.innerHTML = renderHome();
  if (state.view === "team") app.innerHTML = renderTeam();
  if (state.view === "roster-intelligence") app.innerHTML = renderRosterIntelligence();
  if (state.view === "trades") app.innerHTML = renderTradeFinder();
  if (state.view === "opportunities") app.innerHTML = renderOpportunities();
  if (state.view === "power") app.innerHTML = renderPower();
  if (state.view === "recap") app.innerHTML = renderRecap();
  if (state.view === "standings") app.innerHTML = renderStandingsPlus();
  if (state.view === "lineups") app.innerHTML = renderLineups();
  if (state.view === "playoffs") app.innerHTML = renderPlayoffSimulator();
  if (state.view === "profiles") app.innerHTML = renderProfiles();
  if (state.view === "managers") app.innerHTML = renderManagerTendencies();
  if (state.view === "draft") app.innerHTML = renderDraftCapital();
  if (state.view === "records") app.innerHTML = renderRecords();
  if (state.view === "waivers") app.innerHTML = renderWaivers();
  if (state.view === "league") app.innerHTML = renderLeague();
  if (state.view === "activity") app.innerHTML = renderActivity();
  if (state.view === "intel") app.innerHTML = renderPlayerIntel();

  wireViewControls();
}

async function boot() {
  try {
    const [summary, teams, waivers, changes, transactions, needs, tradePartners, opportunities, power, standings, lineups, recap, draftCapital, records, playoffs, profiles, managerTendencies, playerIntel, marketSummary, dataHealth, intelligenceHistory, rosterIntelligence, rosterIntelligenceHistory] = await Promise.all([
      getJson("league_summary.json"),
      getJson("team_assets.json"),
      getJson("free_agents_by_position.json"),
      getJson("league_changes.json"),
      getJson("recent_transactions.json"),
      getJson("team_needs.json"),
      getJson("trade_partners.json"),
      getJson("opportunity_scanner.json"),
      getJson("power_rankings.json"),
      getJson("standings_plus.json"),
      getJson("lineup_efficiency.json"),
      getJson("weekly_recap.json"),
      getJson("draft_capital_matrix.json"),
      getJson("record_book.json"),
      getJson("playoff_simulator.json"),
      getJson("team_profiles.json"),
      getJson("manager_tendencies.json"),
      getOptionalJson("player_intel.json", null),
      getOptionalJson("roster_market_values.json", null),
      getOptionalJson("data_health.json", null),
      getOptionalJson("intelligence_history.json", null),
      getOptionalJson("roster_intelligence.json", null),
      getOptionalJson("roster_intelligence_history.json", null),
    ]);
    Object.assign(state, { summary, teams, waivers, changes, transactions, needs, tradePartners, opportunities, power, standings, lineups, recap, draftCapital, records, playoffs, profiles, managerTendencies, playerIntel, marketSummary, dataHealth, intelligenceHistory, rosterIntelligence, rosterIntelligenceHistory });
    if (power?.scopes?.current?.status !== "live" && power?.scopes?.all_time?.status === "live") {
      state.analyticsScope = "all_time";
    }
    document.querySelector("#updated-at").textContent = `Derived data: ${fmtTime(summary.generated_at)}`;
    render();
  } catch (err) {
    document.querySelector("#app").innerHTML = `<div class="loading-card"><strong>Dashboard data is not ready yet.</strong><br><br>${esc(err.message)}<br><br>Run Sync Sleeper Players once after installing the Phase 2 scripts.</div>`;
    console.error(err);
  }
}

document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => {
    state.view = btn.dataset.view;
    setActiveNav();
    render();
  });
});

boot();
