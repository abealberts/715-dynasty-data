const REPO = "abealberts/715-dynasty-data";
const RAW = `https://raw.githubusercontent.com/${REPO}/main/data/derived`;
const MY_ROSTER_ID = "3";

const state = {
  summary: null,
  teams: null,
  waivers: null,
  changes: null,
  transactions: null,
  view: "home",
};

async function getJson(name) {
  const res = await fetch(`${RAW}/${name}?t=${Date.now()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${name}: ${res.status}`);
  return res.json();
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

function playerTable(players) {
  if (!players?.length) return `<div class="empty">No players found.</div>`;
  return `<div class="table-wrap"><table>
    <thead><tr><th>Player</th><th>Pos</th><th>NFL</th><th>Age</th><th>Depth</th><th>Status</th></tr></thead>
    <tbody>${players.map(p => `<tr>
      <td><span class="player-name">${esc(p.name)}</span> ${p.starter ? '<span class="starter-badge">START</span>' : ''}</td>
      <td>${esc(p.position || "—")}</td>
      <td>${esc(p.team || "FA")}</td>
      <td>${esc(p.age ?? "—")}</td>
      <td>${esc(p.depth_chart_order ?? "—")}</td>
      <td class="${p.injury_status ? 'injury' : 'muted'}">${esc(p.injury_status || p.status || "—")}</td>
    </tr>`).join("")}</tbody>
  </table></div>`;
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
  return `<article class="team-card ${mine ? 'mine' : ''}">
    <div class="team-name">${esc(team.team_name || team.manager || `Roster ${team.roster_id}`)}</div>
    <div class="team-meta">${esc(team.manager || "Unknown manager")} · ${team.record?.wins ?? 0}-${team.record?.losses ?? 0}</div>
    <div class="position-line">
      ${["QB","RB","WR","TE"].map(pos => `<span class="chip">${pos} ${counts[pos] || 0}</span>`).join("")}
      <span class="chip accent">${team.picks?.length || 0} picks</span>
      <span class="chip">$${team.waivers?.faab_remaining ?? "—"} FAAB</span>
    </div>
  </article>`;
}

function renderHome() {
  const s = state.summary;
  const me = state.teams?.[MY_ROSTER_ID];
  const recentChanges = state.changes?.changes || [];
  const tx = state.transactions || [];
  return `
    <div class="stats-grid">
      ${stat("Format", s.superflex ? "Superflex" : "1QB", s.full_ppr ? "Full PPR" : "Custom scoring")}
      ${stat("My FAAB", `$${me?.waivers?.faab_remaining ?? "—"}`, `Waiver priority ${me?.waivers?.waiver_position ?? "—"}`)}
      ${stat("My Picks", me?.picks?.length ?? 0, "Current future picks")}
      ${stat("League Median", s.league_median_match ? "ON" : "OFF", "Extra weekly matchup")}
    </div>
    <div class="grid-2">
      <div class="panel">
        <div class="panel-header"><div><h2>League Snapshot</h2><div class="panel-sub">All 12 teams at a glance</div></div></div>
        <div class="team-grid">${Object.values(state.teams || {}).map(teamCard).join("")}</div>
      </div>
      <div>
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

function renderTeam() {
  const me = state.teams?.[MY_ROSTER_ID];
  if (!me) return `<div class="loading-card">Roster 3 was not found.</div>`;
  return `
    <div class="stats-grid">
      ${stat("Record", `${me.record?.wins ?? 0}-${me.record?.losses ?? 0}`, me.team_name || me.manager)}
      ${stat("FAAB", `$${me.waivers?.faab_remaining ?? "—"}`, `$${me.waivers?.faab_used ?? 0} used`)}
      ${stat("Rostered", me.players?.length ?? 0, "Players")}
      ${stat("Picks", me.picks?.length ?? 0, "Future draft assets")}
    </div>
    <div class="grid-2">
      <div class="panel"><div class="panel-header"><div><h2>Roster</h2><div class="panel-sub">Starters highlighted</div></div></div>${playerTable(me.players)}</div>
      <div class="panel"><div class="panel-header"><div><h2>Draft Capital</h2><div class="panel-sub">Picks currently owned</div></div></div>${picksTable(me.picks)}</div>
    </div>`;
}

function renderWaivers() {
  const all = state.waivers || {};
  return `
    <div class="panel">
      <div class="panel-header">
        <div><h2>Available Players</h2><div class="panel-sub">Confirmed free agents from Sleeper; browse order favors NFL roster + depth-chart proximity</div></div>
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

function render() {
  const app = document.querySelector("#app");
  const titles = {
    home: ["Overview", "Live 715 Dynasty league state"],
    team: ["My Team", "Baskerville Bilge Rats"],
    waivers: ["Waivers", "Confirmed available players"],
    league: ["League", "Roster and asset map"],
    activity: ["Activity", "Adds, drops, trades and detected changes"],
  };
  document.querySelector("#page-title").textContent = titles[state.view][0];
  document.querySelector("#page-subtitle").textContent = titles[state.view][1];

  if (state.view === "home") app.innerHTML = renderHome();
  if (state.view === "team") app.innerHTML = renderTeam();
  if (state.view === "waivers") {
    app.innerHTML = renderWaivers();
    document.querySelector("#pos-filter")?.addEventListener("change", updateWaivers);
    document.querySelector("#waiver-search")?.addEventListener("input", updateWaivers);
    updateWaivers();
  }
  if (state.view === "league") app.innerHTML = renderLeague();
  if (state.view === "activity") app.innerHTML = renderActivity();
}

async function boot() {
  try {
    const [summary, teams, waivers, changes, transactions] = await Promise.all([
      getJson("league_summary.json"),
      getJson("team_assets.json"),
      getJson("free_agents_by_position.json"),
      getJson("league_changes.json"),
      getJson("recent_transactions.json"),
    ]);
    Object.assign(state, { summary, teams, waivers, changes, transactions });
    document.querySelector("#updated-at").textContent = `Derived data: ${fmtTime(summary.generated_at)}`;
    render();
  } catch (err) {
    document.querySelector("#app").innerHTML = `<div class="loading-card"><strong>Dashboard data is not ready yet.</strong><br><br>${esc(err.message)}<br><br>Run the updated Sleeper workflow once so data/derived is generated.</div>`;
    console.error(err);
  }
}

document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(x => x.classList.remove("active"));
    btn.classList.add("active");
    state.view = btn.dataset.view;
    render();
  });
});

boot();
