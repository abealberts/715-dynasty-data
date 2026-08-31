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
  view: "home",
  tradePartnerId: null,
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
      <td>${esc(p.depth ?? p.depth_chart_order ?? "—")}</td>
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
      <div class="panel"><div class="panel-header"><div><h2>Roster</h2><div class="panel-sub">Starters highlighted</div></div></div>${playerTable(me.players)}</div>
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
      <div class="panel"><div class="panel-header"><div><h2>Their Roster</h2><div class="panel-sub">Targets to research</div></div></div>${playerTable(them.players)}</div>
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
    trades: ["Trade Finder", "Find roster-construction matches before doing market research"],
    opportunities: ["Opportunities", "Signal-ranked, confirmed free agents"],
    waivers: ["Waivers", "Confirmed available players"],
    league: ["League", "Roster and asset map"],
    activity: ["Activity", "Adds, drops, trades and detected changes"],
  };
  document.querySelector("#page-title").textContent = titles[state.view][0];
  document.querySelector("#page-subtitle").textContent = titles[state.view][1];

  if (state.view === "home") app.innerHTML = renderHome();
  if (state.view === "team") app.innerHTML = renderTeam();
  if (state.view === "trades") app.innerHTML = renderTradeFinder();
  if (state.view === "opportunities") app.innerHTML = renderOpportunities();
  if (state.view === "waivers") app.innerHTML = renderWaivers();
  if (state.view === "league") app.innerHTML = renderLeague();
  if (state.view === "activity") app.innerHTML = renderActivity();

  wireViewControls();
}

async function boot() {
  try {
    const [summary, teams, waivers, changes, transactions, needs, tradePartners, opportunities] = await Promise.all([
      getJson("league_summary.json"),
      getJson("team_assets.json"),
      getJson("free_agents_by_position.json"),
      getJson("league_changes.json"),
      getJson("recent_transactions.json"),
      getJson("team_needs.json"),
      getJson("trade_partners.json"),
      getJson("opportunity_scanner.json"),
    ]);
    Object.assign(state, { summary, teams, waivers, changes, transactions, needs, tradePartners, opportunities });
    document.querySelector("#updated-at").textContent = `Derived data: ${fmtTime(summary.generated_at)}`;
    render();
  } catch (err) {
    document.querySelector("#app").innerHTML = `<div class="loading-card"><strong>Phase 2 data is not ready yet.</strong><br><br>${esc(err.message)}<br><br>Run Sync Sleeper Players once after installing the Phase 2 scripts.</div>`;
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
