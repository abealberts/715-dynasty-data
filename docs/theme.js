
/* ==========================================================================
   715 DYNASTY HQ — PHASE 4.5 VISUAL ENHANCEMENTS
   Pure presentation layer. Reads existing `state`; does not alter analytics.
   ========================================================================== */

(() => {
  const COLORS = {
    // Muted ink palette: intentionally closer to vintage scorecards,
    // pennants and newspaper spot-color printing than neon UI colors.
    lime: "#7c8250",
    cyan: "#52758a",
    coral: "#a34b3e",
    violet: "#76657d",
    amber: "#b48a3e",
    mint: "#647b60",
    slate: "#6c7374",
    paper: "#e4dac0",
    ink: "#1b1914",
  };

  const q = (sel, root = document) => root.querySelector(sel);
  const qa = (sel, root = document) => [...root.querySelectorAll(sel)];
  const escapeHtml = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function shortName(row) {
    const full = row?.team_name || row?.manager || `Roster ${row?.roster_id ?? "?"}`;
    return full.length > 23 ? `${full.slice(0, 21)}…` : full;
  }

  function toneStatCards() {
    const tones = ["lime", "cyan", "violet", "amber", "coral", "mint"];
    qa(".stat-card").forEach((card, i) => {
      tones.forEach(t => card.classList.remove(`tone-${t}`));
      const label = q(".stat-label", card)?.textContent?.toLowerCase() || "";
      let tone = tones[i % tones.length];

      if (/(luck|risk|cursed|loss|injury|regret)/.test(label)) tone = "coral";
      else if (/(faab|waiver|opportun)/.test(label)) tone = "amber";
      else if (/(pick|capital|future)/.test(label)) tone = "violet";
      else if (/(power|score|record|week|playoff)/.test(label)) tone = "cyan";
      else if (/(title|favorite|best|efficiency)/.test(label)) tone = "lime";

      card.classList.add(`tone-${tone}`);
    });
  }

  function semanticPanels() {
    qa(".panel").forEach(panel => {
      const title = q("h2", panel)?.textContent?.toLowerCase() || "";
      panel.classList.remove(
        "semantic-panel","accent-lime","accent-cyan","accent-coral",
        "accent-violet","accent-amber","accent-mint"
      );
      let tone = null;
      if (/(waiver|opportun)/.test(title)) tone = "amber";
      else if (/(draft|capital|pick)/.test(title)) tone = "violet";
      else if (/(power|standings|score|lineup|playoff)/.test(title)) tone = "cyan";
      else if (/(record|award|recap)/.test(title)) tone = "coral";
      else if (/(trade|profile|roster)/.test(title)) tone = "lime";
      if (tone) panel.classList.add("semantic-panel", `accent-${tone}`);
    });
  }

  function renderPulse() {
    const host = q("#league-pulse");
    if (!host || typeof state === "undefined" || !state.summary) return;

    const me = state.teams?.["3"];
    const topPower = state.power?.scopes?.all_time?.rankings?.[0];
    const myPlayoff = state.playoffs?.teams?.find(x => String(x.roster_id) === "3");
    const topOpp = state.opportunities?.players?.[0];
    const myProfile = state.profiles?.teams?.find(x => String(x.roster_id) === "3");

    const items = [
      `<span class="pulse-item cyan">POWER LEADER <strong>${escapeHtml(shortName(topPower))}</strong></span>`,
      `<span class="pulse-item violet">MY FUTURE PICKS <strong>${escapeHtml(me?.picks?.length ?? "—")}</strong></span>`,
      `<span class="pulse-item amber">TOP FA SIGNAL <strong>${escapeHtml(topOpp?.name || "—")}</strong></span>`,
      `<span class="pulse-item cyan">BILGE RAT PLAYOFF ODDS <strong>${escapeHtml(myPlayoff?.playoff_odds ?? "—")}%</strong></span>`,
      `<span class="pulse-item violet">FRANCHISE SCORE <strong>${escapeHtml(myProfile?.franchise_score ?? "—")}</strong></span>`,
      `<span class="pulse-item">FORMAT <strong>12T SF / FULL PPR / MEDIAN</strong></span>`,
    ];

    host.innerHTML = `<div class="pulse-inner"><div class="pulse-label">LEAGUE PULSE</div><div class="pulse-items">${items.join("")}</div></div>`;
  }

  function barChart(rows, {
    label = r => shortName(r),
    value = r => Number(r.value || 0),
    suffix = "",
    color = COLORS.cyan,
    max = null
  } = {}) {
    const vals = rows.map(value);
    const ceiling = max ?? Math.max(1, ...vals);
    return `<div class="bar-chart">${rows.map((row, i) => {
      const v = value(row);
      const pct = Math.max(0, Math.min(100, (v / ceiling) * 100));
      const rowColor = String(row?.roster_id) === "3" ? COLORS.lime : color;
      return `<div class="bar-row">
        <div class="bar-label" title="${escapeHtml(label(row))}">${escapeHtml(label(row))}</div>
        <div class="bar-track"><div class="bar-fill" style="--bar:${pct.toFixed(1)}%;--bar-color:${rowColor};animation-delay:${i*22}ms"></div></div>
        <div class="bar-value">${escapeHtml(v.toFixed ? v.toFixed(1) : v)}${suffix}</div>
      </div>`;
    }).join("")}</div>`;
  }

  function vizPanel(title, kicker, body, color = COLORS.cyan) {
    return `<section class="viz-panel" style="--viz-accent:${color}">
      <div class="viz-title-row"><div class="viz-title">${escapeHtml(title)}</div><div class="viz-kicker">${escapeHtml(kicker)}</div></div>
      ${body}
    </section>`;
  }

  function insertAfter(target, html, marker) {
    if (!target || q(`[data-viz="${marker}"]`)) return;
    const wrap = document.createElement("div");
    wrap.dataset.viz = marker;
    wrap.innerHTML = html;
    target.insertAdjacentElement("afterend", wrap);
  }

  function powerCharts() {
    if (state.view !== "power") return;
    const data = state.power?.scopes?.[state.analyticsScope];
    if (!data?.rankings?.length) return;
    const rows = data.rankings;

    const chart = barChart(rows, {
      value: r => Number(r.power_score || 0),
      suffix: "",
      color: COLORS.cyan,
      max: 100
    });

    const my = rows.find(r => String(r.roster_id) === "3");
    const donut = `<div class="donut-wrap">
      <div class="donut" style="--pct:${Number(my?.power_score || 0)};--donut-color:${COLORS.lime}">
        <div class="donut-center"><strong>${escapeHtml(my?.power_score ?? "—")}</strong><span>Bilge Rat Power</span></div>
      </div>
      <div class="chart-legend">
        <span class="legend-key" style="--legend-color:${COLORS.lime}">Your team</span>
        <span class="legend-key" style="--legend-color:${COLORS.cyan}">League field</span>
      </div>
    </div>`;

    const anchor = qa(".panel")[0];
    insertAfter(anchor,
      `<div class="viz-grid">${vizPanel("Power Score Field", "0–100 composite", chart, COLORS.cyan)}${vizPanel("Your Position", state.analyticsScope === "all_time" ? "career model" : "current season", donut, COLORS.lime)}</div>`,
      "power"
    );
  }

  function standingsScatter() {
    if (state.view !== "standings") return;
    const data = state.standings?.scopes?.[state.analyticsScope];
    const teams = data?.teams || [];
    if (!teams.length) return;

    const xs = teams.map(t => Number(t.average_score || 0));
    const ys = teams.map(t => Number(t.luck_index || 0));
    const xMin = Math.min(...xs) - 2;
    const xMax = Math.max(...xs) + 2;
    const yAbs = Math.max(10, ...ys.map(Math.abs));

    const dots = teams.map(t => {
      const x = Number(t.average_score || 0);
      const y = Number(t.luck_index || 0);
      const left = ((x - xMin) / Math.max(1, xMax - xMin)) * 100;
      const bottom = ((y + yAbs) / (yAbs * 2)) * 100;
      const cls = String(t.roster_id) === "3" ? " mine" : "";
      const color = y > 4 ? COLORS.mint : y < -4 ? COLORS.coral : COLORS.cyan;
      return `<span class="scatter-dot${cls}" title="${escapeHtml(shortName(t))}: ${x.toFixed(1)} avg, ${y > 0 ? "+" : ""}${y.toFixed(1)} luck" style="left:${left.toFixed(2)}%;bottom:${bottom.toFixed(2)}%;--dot-color:${color}"></span>`;
    }).join("");

    const scatter = `<div class="scatter-wrap">
      <span class="axis-label y">LUCK ↑</span>
      <span class="axis-label x">AVG SCORE →</span>
      ${dots}
    </div>
    <div class="chart-legend">
      <span class="legend-key" style="--legend-color:${COLORS.mint}">Lucky</span>
      <span class="legend-key" style="--legend-color:${COLORS.coral}">Cursed</span>
      <span class="legend-key" style="--legend-color:${COLORS.lime}">You</span>
    </div>`;

    const anchor = qa(".stats-grid")[0] || qa(".panel")[0];
    insertAfter(anchor, vizPanel("Luck vs. Scoring", "who earned it?", scatter, COLORS.coral), "standings");
  }

  function playoffCharts() {
    if (state.view !== "playoffs") return;
    const teams = state.playoffs?.teams || [];
    if (!teams.length) return;

    const playoff = barChart(teams, {
      value: t => Number(t.playoff_odds || 0),
      suffix: "%",
      color: COLORS.cyan,
      max: 100
    });

    const title = barChart([...teams].sort((a,b)=>Number(b.title_odds)-Number(a.title_odds)), {
      value: t => Number(t.title_odds || 0),
      suffix: "%",
      color: COLORS.violet,
      max: Math.max(1, ...teams.map(t => Number(t.title_odds || 0)))
    });

    const anchor = qa(".stats-grid")[0];
    insertAfter(anchor,
      `<div class="viz-grid">${vizPanel("Make Playoffs", "10,000 simulations", playoff, COLORS.cyan)}${vizPanel("Win The League", "simulated title share", title, COLORS.violet)}</div>`,
      "playoffs"
    );
  }

  function profileCharts() {
    if (state.view !== "profiles") return;
    const team = state.profiles?.teams?.find(x => String(x.roster_id) === String(state.profileRosterId));
    if (!team) return;

    const metrics = team.metrics || {};
    const metricRows = [
      ["Performance", metrics.performance_prior, COLORS.cyan],
      ["Market Value", metrics.market_value, COLORS.violet],
      ["Draft Capital", metrics.draft_capital, COLORS.amber],
      ["Youth", metrics.youth, COLORS.mint],
      ["Roster Balance", metrics.roster_balance, COLORS.lime],
      ["Management", metrics.lineup_management, COLORS.amber],
      ["Stability", metrics.stability, COLORS.coral],
    ];

    const strips = `<div class="metric-strips">${metricRows.map(([name,val,color]) =>
      `<div class="metric-strip"><span>${escapeHtml(name)}</span><div class="metric-strip-track"><div class="metric-strip-fill" style="width:${Math.max(0,Math.min(100,Number(val||0)))}%;--metric-color:${color}"></div></div><strong>${Number(val||0).toFixed(0)}</strong></div>`
    ).join("")}</div>`;

    const donut = `<div class="donut-wrap">
      <div class="donut" style="--pct:${Number(team.franchise_score || 0)};--donut-color:${COLORS.violet}">
        <div class="donut-center"><strong>${escapeHtml(team.franchise_score)}</strong><span>Franchise Score</span></div>
      </div>
      <div class="fun-badge" style="--badge-color:${team.window === "Contender" ? COLORS.lime : team.window === "Rebuilder" ? COLORS.violet : COLORS.cyan}">${escapeHtml(team.window)}</div>
    </div>`;

    const anchor = q(".profile-hero");
    insertAfter(anchor,
      `<div class="viz-grid">${vizPanel("Franchise Shape", "relative to 715", strips, COLORS.violet)}${vizPanel("Composite Grade", "current assets + performance", donut, COLORS.violet)}</div>`,
      "profiles"
    );
  }

  function draftCharts() {
    if (state.view !== "draft") return;
    const teams = state.draftCapital?.teams || [];
    if (!teams.length) return;

    const firsts = [...teams].sort((a,b)=>(b.summary?.firsts||0)-(a.summary?.firsts||0));
    const early = [...teams].sort((a,b)=>(b.summary?.early_picks||0)-(a.summary?.early_picks||0));

    const left = barChart(firsts, {
      value: t => Number(t.summary?.firsts || 0),
      color: COLORS.violet,
      max: Math.max(1, ...firsts.map(t=>Number(t.summary?.firsts||0)))
    });
    const right = barChart(early, {
      value: t => Number(t.summary?.early_picks || 0),
      color: COLORS.amber,
      max: Math.max(1, ...early.map(t=>Number(t.summary?.early_picks||0)))
    });

    const anchor = qa(".panel")[0];
    insertAfter(anchor,
      `<div class="viz-grid">${vizPanel("Future Firsts", "trade liquidity", left, COLORS.violet)}${vizPanel("1st + 2nd Inventory", "early capital", right, COLORS.amber)}</div>`,
      "draft"
    );
  }

  function managerCharts() {
    if (state.view !== "managers") return;
    const managers = state.managerTendencies?.scopes?.[state.analyticsScope]?.managers || [];
    if (!managers.length) return;

    const trades = [...managers].sort((a,b)=>b.trades-a.trades);
    const moves = [...managers].sort((a,b)=>b.roster_moves-a.roster_moves);

    const left = barChart(trades, {
      label: m => m.manager,
      value: m => Number(m.trades || 0),
      color: COLORS.lime,
      max: Math.max(1, ...trades.map(m=>Number(m.trades||0)))
    });
    const right = barChart(moves, {
      label: m => m.manager,
      value: m => Number(m.roster_moves || 0),
      color: COLORS.amber,
      max: Math.max(1, ...moves.map(m=>Number(m.roster_moves||0)))
    });

    const anchor = qa(".panel")[0];
    insertAfter(anchor,
      `<div class="viz-grid">${vizPanel("Trade Activity", "completed deals", left, COLORS.lime)}${vizPanel("Roster Churn", "waivers + free agents", right, COLORS.amber)}</div>`,
      "managers"
    );
  }


  function posColor(pos) {
    return ({
      QB: COLORS.cyan,
      RB: COLORS.coral,
      WR: COLORS.violet,
      TE: COLORS.amber,
    })[pos] || COLORS.slate;
  }

  function fmtValue(value) {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return "—";
    return Math.round(n).toLocaleString();
  }

  function installPressControls() {
    const host = q(".topbar-right");
    if (!host || q(".press-controls")) return;
    const wrap = document.createElement("div");
    wrap.className = "press-controls";
    wrap.innerHTML = `
      <div class="press-edition"><span>VOL. II</span><strong>715 • 2026</strong></div>
      <button type="button" class="print-board" data-print-board title="Print the current dashboard view">PRINT BOARD</button>
    `;
    host.prepend(wrap);
  }

  function scatterPlot(rows, options = {}) {
    const {
      x = r => Number(r.x || 0),
      y = r => Number(r.y || 0),
      xLabel = "X →",
      yLabel = "Y ↑",
      name = r => r.name || shortName(r),
      color = r => posColor(r.position),
      mine = r => String(r?.ownership?.roster_id ?? r?.roster_id) === "3",
      available = r => r.available === true,
      clickable = false,
      maxPoints = 220,
      xFloor = null,
      yFloor = null,
      size = () => 10,
    } = options;

    let clean = rows
      .filter(r => Number.isFinite(x(r)) && Number.isFinite(y(r)))
      .slice(0, maxPoints);

    if (!clean.length) return `<div class="empty">Not enough matched data for this chart yet.</div>`;

    const xs = clean.map(x);
    const ys = clean.map(y);
    let xMin = xFloor == null ? Math.min(...xs) : xFloor;
    let yMin = yFloor == null ? Math.min(...ys) : yFloor;
    let xMax = Math.max(...xs);
    let yMax = Math.max(...ys);

    if (Math.abs(xMax - xMin) < 0.001) xMax = xMin + 1;
    if (Math.abs(yMax - yMin) < 0.001) yMax = yMin + 1;

    const xPad = (xMax - xMin) * .04;
    const yPad = (yMax - yMin) * .06;
    xMin -= xPad; xMax += xPad;
    yMin -= yPad; yMax += yPad;

    const dots = clean.map(r => {
      const xv = x(r), yv = y(r);
      const left = ((xv - xMin) / (xMax - xMin)) * 100;
      const bottom = ((yv - yMin) / (yMax - yMin)) * 100;
      const px = Math.max(8, Math.min(18, Number(size(r) || 10)));
      const classes = [
        "intel-dot",
        mine(r) ? "mine" : "",
        available(r) ? "available" : "",
        clickable ? "clickable" : "",
      ].filter(Boolean).join(" ");
      const perf = r.performance || {};
      const title = [
        name(r),
        r.position || "",
        `Market ${fmtValue(r.market_value ?? r.current_value ?? 0)}`,
        perf.ppg_715 != null ? `${perf.ppg_715} PPG` : "",
        perf.opportunities_per_game != null ? `${perf.opportunities_per_game} opp/g` : "",
      ].filter(Boolean).join(" · ");
      return `<button type="button" class="${classes}"
        ${clickable && r.player_id ? `data-intel-player="${escapeHtml(r.player_id)}"` : ""}
        aria-label="${escapeHtml(title)}"
        title="${escapeHtml(title)}"
        style="left:${left.toFixed(2)}%;bottom:${bottom.toFixed(2)}%;--dot-color:${color(r)};--dot-size:${px}px"></button>`;
    }).join("");

    return `<div class="intel-scatter">
      <span class="axis-label y">${escapeHtml(yLabel)}</span>
      <span class="axis-label x">${escapeHtml(xLabel)}</span>
      ${dots}
    </div>`;
  }

  function playerDossier(player) {
    if (!player) return `<div class="player-dossier empty-dossier">Select a point to inspect a player.</div>`;
    const perf = player.performance || {};
    const owner = player.ownership?.team_name || player.ownership?.manager || "FREE AGENT";
    const basis = perf.basis ? `${perf.basis_label} ${perf.basis === "prior" ? "PRIOR" : "CURRENT"}` : "NO PERF SAMPLE";
    return `<div class="player-dossier" data-player-dossier>
      <div class="dossier-topline">
        <span class="dossier-stamp">${escapeHtml(player.available ? "FREE AGENT" : owner)}</span>
        <span class="dossier-basis">${escapeHtml(basis)}</span>
      </div>
      <div class="dossier-name">${escapeHtml(player.name)}</div>
      <div class="dossier-meta">
        <span class="position-tag pos-${escapeHtml(player.position || "OTHER")}">${escapeHtml(player.position || "—")}</span>
        <span>${escapeHtml(player.team || "FA")}</span>
        <span>Age ${escapeHtml(player.age ?? "—")}</span>
      </div>
      <div class="dossier-grid">
        <div><span>MARKET</span><strong>${player.market_value ? fmtValue(player.market_value) : "—"}</strong><small>${player.market_position_rank ? `#${escapeHtml(player.market_position_rank)} ${escapeHtml(player.position)}` : ""}</small></div>
        <div><span>715 PPG</span><strong>${escapeHtml(perf.ppg_715 ?? "—")}</strong><small>${escapeHtml(perf.games ?? "—")} games</small></div>
        <div><span>OPP / G</span><strong>${escapeHtml(perf.opportunities_per_game ?? "—")}</strong><small>last 3: ${escapeHtml(perf.last3_opportunities_per_game ?? "—")}</small></div>
        <div><span>SNAP %</span><strong>${perf.offense_snap_pct != null ? `${escapeHtml(perf.offense_snap_pct)}%` : "—"}</strong><small>offensive</small></div>
      </div>
    </div>`;
  }

  function updateDossier(playerId) {
    if (!playerId || !state.playerIntel?.players) return;
    const player = state.playerIntel.players.find(x => String(x.player_id) === String(playerId));
    const host = q("[data-player-dossier-host]");
    if (!host || !player) return;
    state._intelSelectedId = String(playerId);
    host.innerHTML = playerDossier(player);
    qa(".intel-dot[data-intel-player]").forEach(dot => {
      dot.classList.toggle("selected", dot.dataset.intelPlayer === String(playerId));
    });
  }

  function intelCharts() {
    if (state.view !== "intel") return;
    const rows = state.playerIntel?.players || [];
    if (!rows.length) return;

    const matched = rows
      .filter(p => Number(p.market_value || 0) > 0 && p.performance?.ppg_715 != null)
      .sort((a,b) => Number(b.market_value || 0) - Number(a.market_value || 0));

    const skill = matched
      .filter(p => ["RB","WR","TE"].includes(p.position) && p.performance?.opportunities_per_game != null);

    const selected =
      rows.find(x => String(x.player_id) === String(state._intelSelectedId || "")) ||
      matched.find(x => x.available) ||
      matched[0];

    const production = scatterPlot(matched, {
      x: p => Number(p.market_value || 0),
      y: p => Number(p.performance?.ppg_715 || 0),
      xLabel: "DYNASTY MARKET VALUE →",
      yLabel: "715 PPG ↑",
      clickable: true,
      maxPoints: 240,
      xFloor: 0,
      yFloor: 0,
      size: p => 8 + Math.min(8, Number(p.performance?.opportunities_per_game || 0) / 3),
    });

    const usage = scatterPlot(skill, {
      x: p => Number(p.performance?.opportunities_per_game || 0),
      y: p => Number(p.market_value || 0),
      xLabel: "OPPORTUNITIES / GAME →",
      yLabel: "MARKET VALUE ↑",
      clickable: true,
      maxPoints: 220,
      xFloor: 0,
      yFloor: 0,
      size: p => 8 + Math.min(8, Number(p.performance?.offense_snap_pct || 0) / 15),
    });

    const html = `<div class="intel-chart-grid">
      ${vizPanel("Market vs Production", "dot size ≈ opportunity volume", production, COLORS.cyan)}
      ${vizPanel("Skill Usage vs Market", "RB / WR / TE · dot size ≈ snap share", usage, COLORS.violet)}
    </div>
    <div data-player-dossier-host>${playerDossier(selected)}</div>
    <div class="chart-legend vintage-legend">
      <span class="legend-key pos-legend-qb">QB</span>
      <span class="legend-key pos-legend-rb">RB</span>
      <span class="legend-key pos-legend-wr">WR</span>
      <span class="legend-key pos-legend-te">TE</span>
      <span class="legend-note">Ring = free agent · large outlined dot = your roster</span>
    </div>`;

    const anchor = qa(".stats-grid")[0];
    insertAfter(anchor, html, "intel-markets");
    if (selected) setTimeout(() => updateDossier(selected.player_id), 0);
  }

  function opportunityIntelScatter() {
    if (state.view !== "opportunities") return;
    const rows = (state.opportunities?.players || [])
      .filter(p => Number(p.market_value || 0) > 0)
      .sort((a,b) => Number(b.opportunity_score || 0) - Number(a.opportunity_score || 0));

    if (!rows.length) return;
    const scatter = scatterPlot(rows, {
      x: p => Number(p.market_value || 0),
      y: p => Number(p.opportunity_score || 0),
      xLabel: "DYNASTY MARKET VALUE →",
      yLabel: "715 OPPORTUNITY SCORE ↑",
      name: p => p.name,
      color: p => posColor(p.position),
      available: () => true,
      maxPoints: 110,
      xFloor: 0,
      yFloor: 0,
      size: p => 9 + Math.min(7, Number(p.performance?.opportunities_per_game || 0) / 3),
    });
    const anchor = qa(".panel")[0];
    insertAfter(anchor, vizPanel(
      "Waiver Value Quadrant",
      "upper-left = cheap signal · upper-right = market-backed signal",
      scatter,
      COLORS.amber
    ), "opportunity-market");
  }

  function marketCompositionChart(teams) {
    if (!teams.length) return "";
    const maxTotal = Math.max(1, ...teams.map(t => Number(t.total_market_value || 0)));
    return `<div class="market-stack-chart">${teams.map(t => {
      const values = t.position_values || {};
      const total = Math.max(1, Number(t.total_market_value || 0));
      const width = (total / maxTotal) * 100;
      return `<div class="market-stack-row">
        <div class="market-stack-label" title="${escapeHtml(shortName(t))}">${escapeHtml(shortName(t))}</div>
        <div class="market-stack-track">
          <div class="market-stack-total" style="width:${width.toFixed(1)}%">
            ${["QB","RB","WR","TE"].map(pos => {
              const val = Number(values[pos] || 0);
              return `<span class="market-segment market-${pos}" style="width:${((val/total)*100).toFixed(1)}%" title="${pos}: ${fmtValue(val)}"></span>`;
            }).join("")}
          </div>
        </div>
        <div class="market-stack-value">${fmtValue(total)}</div>
      </div>`;
    }).join("")}</div>`;
  }

  function starterDepthChart(teams) {
    if (!teams.length) return "";
    const maxTotal = Math.max(1, ...teams.map(t => Number(t.total_market_value || 0)));
    return `<div class="market-stack-chart">${teams.map(t => {
      const starter = Number(t.optimal_starter_market_value || 0);
      const depth = Number(t.depth_market_value || 0);
      const total = Math.max(1, starter + depth);
      const width = (total / maxTotal) * 100;
      return `<div class="market-stack-row">
        <div class="market-stack-label" title="${escapeHtml(shortName(t))}">${escapeHtml(shortName(t))}</div>
        <div class="market-stack-track">
          <div class="market-stack-total" style="width:${width.toFixed(1)}%">
            <span class="market-segment starter-segment" style="width:${((starter/total)*100).toFixed(1)}%" title="Optimal starters: ${fmtValue(starter)}"></span>
            <span class="market-segment depth-segment" style="width:${((depth/total)*100).toFixed(1)}%" title="Depth: ${fmtValue(depth)}"></span>
          </div>
        </div>
        <div class="market-stack-value">${fmtValue(total)}</div>
      </div>`;
    }).join("")}</div>`;
  }

  function leagueMarketCharts() {
    if (state.view !== "league") return;
    const teams = [...(state.marketSummary?.teams || [])]
      .sort((a,b) => Number(b.total_market_value || 0) - Number(a.total_market_value || 0));
    if (!teams.length) return;

    const composition = marketCompositionChart(teams);
    const depth = starterDepthChart(
      [...teams].sort((a,b) => Number(b.optimal_starter_market_value || 0) - Number(a.optimal_starter_market_value || 0))
    );

    const anchor = qa(".stats-grid")[0] || qa(".panel")[0];
    insertAfter(anchor, `<div class="viz-grid">
      ${vizPanel("Roster Market Composition", "QB / RB / WR / TE · total bar length = roster value", composition, COLORS.violet)}
      ${vizPanel("Starter vs Depth Capital", "optimal legal starter value vs remaining roster", depth, COLORS.amber)}
    </div>
    <div class="chart-legend vintage-legend">
      <span class="legend-key pos-legend-qb">QB</span><span class="legend-key pos-legend-rb">RB</span>
      <span class="legend-key pos-legend-wr">WR</span><span class="legend-key pos-legend-te">TE</span>
      <span class="legend-key starter-legend">STARTERS</span><span class="legend-key depth-legend">DEPTH</span>
    </div>`, "league-market");
  }

  function myTeamMarketCharts() {
    if (state.view !== "team") return;
    const me = state.teams?.["3"];
    const players = [...(me?.players || [])]
      .filter(p => Number(p.market_value || 0) > 0)
      .sort((a,b) => Number(b.market_value || 0) - Number(a.market_value || 0))
      .slice(0, 14);
    if (!players.length) return;

    const assets = barChart(players, {
      label: p => p.name,
      value: p => Number(p.market_value || 0),
      color: COLORS.violet,
      max: Math.max(1, ...players.map(p => Number(p.market_value || 0))),
    });

    const matched = players.filter(p => p.performance?.ppg_715 != null);
    const scatter = scatterPlot(matched, {
      x: p => Number(p.market_value || 0),
      y: p => Number(p.performance?.ppg_715 || 0),
      xLabel: "MARKET VALUE →",
      yLabel: "715 PPG ↑",
      name: p => p.name,
      color: p => posColor(p.position),
      mine: () => true,
      xFloor: 0,
      yFloor: 0,
      maxPoints: 30,
      size: p => 10 + Math.min(5, Number(p.performance?.opportunities_per_game || 0) / 4),
    });

    const anchor = qa(".stats-grid")[0];
    insertAfter(anchor, `<div class="viz-grid">
      ${vizPanel("Bilge Rat Asset Ledger", "top dynasty market values", assets, COLORS.violet)}
      ${vizPanel("Market vs Prior Production", "2025 prior until 2026 data exists", scatter, COLORS.cyan)}
    </div>`, "team-intel");
  }

  function profileLeagueQuadrant() {
    if (state.view !== "profiles") return;
    const teams = state.profiles?.teams || [];
    if (!teams.length || !teams.some(t => t.metrics?.market_value != null)) return;

    const scatter = scatterPlot(teams, {
      x: t => Number(t.metrics?.market_value || 0),
      y: t => Number(t.metrics?.performance_prior || 0),
      xLabel: "CURRENT MARKET STRENGTH →",
      yLabel: "PERFORMANCE MODEL ↑",
      name: t => shortName(t),
      color: t => String(t.roster_id) === "3" ? COLORS.lime : COLORS.cyan,
      mine: t => String(t.roster_id) === "3",
      available: () => false,
      maxPoints: 20,
      xFloor: 0,
      yFloor: 0,
      size: t => 9 + Math.min(8, Number(t.playoff_odds || 0) / 15),
    });

    const labels = `<div class="quadrant-key">
      <span><strong>UPPER RIGHT</strong> proven + expensive</span>
      <span><strong>UPPER LEFT</strong> productive discount</span>
      <span><strong>LOWER RIGHT</strong> market betting forward</span>
      <span><strong>LOWER LEFT</strong> rebuild / retool</span>
    </div>`;

    const anchor = q('[data-viz="profiles"]') || q(".profile-hero");
    insertAfter(anchor, vizPanel(
      "715 Franchise Market Map",
      "bubble size ≈ playoff odds",
      scatter + labels,
      COLORS.cyan
    ), "profile-league-market");
  }

  function powerInputLedger() {
    if (state.view !== "power" || state.analyticsScope !== "current") return;
    const rows = state.power?.scopes?.current?.rankings || [];
    if (!rows.length || rows[0]?.market_strength == null) return;

    const body = `<div class="power-input-ledger">${rows.map(r => {
      const prior = Number(r.historical_prior_score || 0);
      const market = Number(r.market_strength || 0);
      const live = r.live_performance_score == null ? null : Number(r.live_performance_score);
      return `<div class="power-input-row ${String(r.roster_id)==="3" ? "mine" : ""}">
        <div class="power-input-team">${escapeHtml(shortName(r))}</div>
        <div class="power-input-bars">
          <span class="input-bar prior" style="width:${Math.max(0,Math.min(100,prior))}%" title="Historical prior ${prior}"></span>
          <span class="input-bar market" style="width:${Math.max(0,Math.min(100,market))}%" title="Market ${market}"></span>
          ${live == null ? "" : `<span class="input-bar live" style="width:${Math.max(0,Math.min(100,live))}%" title="2026 performance ${live}"></span>`}
        </div>
        <div class="power-input-score">${escapeHtml(r.power_score)}</div>
      </div>`;
    }).join("")}</div>
    <div class="chart-legend vintage-legend">
      <span class="legend-key prior-legend">HISTORICAL PRIOR</span>
      <span class="legend-key market-legend">CURRENT MARKET</span>
      <span class="legend-key live-legend">2026 PERFORMANCE</span>
    </div>`;

    const existing = q('[data-viz="power"]');
    insertAfter(existing || qa(".panel")[0], vizPanel(
      "Current Power Inputs",
      "preseason = 30% prior / 70% market",
      body,
      COLORS.violet
    ), "power-inputs");
  }

  function playoffModelTicket() {
    if (state.view !== "playoffs") return;
    const data = state.playoffs;
    const sample = data?.teams?.[0];
    if (!data || !sample) return;

    const hist = Number(data.model_blend?.historical_weight ?? 0);
    const current = Number(data.model_blend?.current_season_weight ?? 0);
    const market = Number(sample.market_weight ?? 0) * 100;

    const ticket = `<div class="model-ticket">
      <div class="ticket-number">715 / SIM MODEL / ${escapeHtml(data.current_season || "2026")}</div>
      <div class="ticket-columns">
        <div><span>PERFORMANCE ENGINE</span><strong>${hist.toFixed(0)}% HIST / ${current.toFixed(0)}% 2026</strong><small>Historical/current scoring distribution</small></div>
        <div><span>ROSTER OVERLAY</span><strong>${market.toFixed(0)}% MARKET</strong><small>Adjustment inside scoring expectation</small></div>
        <div><span>SIMULATIONS</span><strong>${Number(data.simulations || 0).toLocaleString()}</strong><small>H2H + league median each week</small></div>
      </div>
      <div class="ticket-note">The market overlay is applied inside the scoring expectation; it is separate from the historical/current performance blend and should not be added to those percentages.</div>
    </div>`;

    const anchor = qa(".stats-grid")[0];
    insertAfter(anchor, ticket, "playoff-model-ticket");
  }

  function opportunityTopStrip() {
    if (state.view !== "opportunities") return;
    const players = (state.opportunities?.players || []).slice(0, 10);
    if (!players.length) return;
    const chart = barChart(players, {
      label: p => p.name,
      value: p => Number(p.opportunity_score || 0),
      color: COLORS.amber,
      max: 100
    });
    const anchor = qa(".panel")[0];
    insertAfter(anchor, vizPanel("Top Signal Board", "scanner score ≠ dynasty value", chart, COLORS.amber), "opportunities");
  }


  function registerPwa() {
    if (!("serviceWorker" in navigator)) return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("./service-worker.js").catch(() => {});
    }, { once: true });
  }

  function sparkline(values, color = COLORS.cyan) {
    const nums = values.map(Number).filter(Number.isFinite);
    if (nums.length < 2) return `<span class="trend-waiting">Tracking starts with Phase 4.8</span>`;
    const w = 150, h = 34, pad = 3;
    let lo = Math.min(...nums), hi = Math.max(...nums);
    if (Math.abs(hi - lo) < .001) { lo -= 1; hi += 1; }
    const pts = nums.map((v, i) => {
      const x = pad + (i / (nums.length - 1)) * (w - pad * 2);
      const y = h - pad - ((v - lo) / (hi - lo)) * (h - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    return `<svg class="micro-spark" viewBox="0 0 ${w} ${h}" role="img" aria-label="Trend over ${nums.length} tracked days"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function healthBadge(label, status, detail = "") {
    const cls = status === "ok" || status === "healthy" ? "ok" : status === "expected_preseason" ? "expected" : status === "stale" ? "expected" : "warn";
    return `<div class="health-source ${cls}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(status || "unknown").replaceAll("_", " "))}</strong>${detail ? `<small>${escapeHtml(detail)}</small>` : ""}</div>`;
  }

  function healthAndTrends() {
    if (state.view !== "home") return;
    const health = state.dataHealth;
    const history = state.intelligenceHistory?.entries || [];
    if (!health && !history.length) return;

    const mySeries = history.map(day => (day.teams || []).find(t => String(t.roster_id) === "3")).filter(Boolean);
    const market = mySeries.map(x => x.market_score).filter(x => x != null);
    const power = mySeries.map(x => x.power_score).filter(x => x != null);
    const playoffs = mySeries.map(x => x.playoff_odds).filter(x => x != null);

    const nfl = health?.nflverse || {};
    const html = `<div class="final-ops-grid">
      <section class="ops-card">
        <div class="ops-head"><span>DATA HEALTH</span><strong class="overall-health ${escapeHtml(health?.overall || "unknown")}">${escapeHtml(health?.overall || "unknown")}</strong></div>
        <div class="health-grid">
          ${healthBadge("Sleeper", health?.sleeper?.status, "authoritative league state")}
          ${healthBadge("Dynasty Dealer", health?.dynasty_dealer?.status, health?.dynasty_dealer?.players ? `${health.dynasty_dealer.players} players` : "market feed")}
          ${healthBadge("nflverse Stats", nfl.current_season_stats, health?.latest_completed_week == null ? "prior-season fallback is expected" : "current season")}
          ${healthBadge("nflverse Snaps", nfl.current_season_snaps, health?.latest_completed_week == null ? "prior-season fallback is expected" : "current season")}
        </div>
      </section>
      <section class="ops-card">
        <div class="ops-head"><span>BILGE RAT TREND TAPE</span><strong>${history.length} DAY${history.length === 1 ? "" : "S"}</strong></div>
        <div class="trend-grid">
          <div><span>MARKET STRENGTH</span>${sparkline(market, COLORS.violet)}<strong>${market.length ? market[market.length-1] : "—"}</strong></div>
          <div><span>CURRENT POWER</span>${sparkline(power, COLORS.cyan)}<strong>${power.length ? power[power.length-1] : "—"}</strong></div>
          <div><span>PLAYOFF ODDS</span>${sparkline(playoffs, COLORS.lime)}<strong>${playoffs.length ? `${playoffs[playoffs.length-1]}%` : "—"}</strong></div>
        </div>
      </section>
    </div>`;
    const anchor = q('[data-viz="home"]') || q("#app .stats-grid");
    insertAfter(anchor, html, "health-trends");
  }

  function homeFun() {
    if (state.view !== "home") return;
    const myPlayoff = state.playoffs?.teams?.find(x => String(x.roster_id) === "3");
    const profile = state.profiles?.teams?.find(x => String(x.roster_id) === "3");
    const myPower = state.power?.scopes?.all_time?.rankings?.find(x => String(x.roster_id) === "3");

    const hero = `<section class="viz-panel" style="--viz-accent:${COLORS.lime}">
      <div class="viz-title-row"><div class="viz-title">Bilge Rat Command Readout</div><div class="viz-kicker">PRESEASON 2026</div></div>
      <div class="profile-facts">
        <div><span>All-Time Power</span><strong style="color:${COLORS.cyan}">#${escapeHtml(myPower?.rank ?? "—")}</strong></div>
        <div><span>Playoff Odds</span><strong style="color:${COLORS.lime}">${escapeHtml(myPlayoff?.playoff_odds ?? "—")}%</strong></div>
        <div><span>Title Odds</span><strong style="color:${COLORS.violet}">${escapeHtml(myPlayoff?.title_odds ?? "—")}%</strong></div>
        <div><span>Window</span><strong style="color:${COLORS.amber}">${escapeHtml(profile?.window ?? "—")}</strong></div>
      </div>
      <div class="data-footnote">Historical baseline will hand off to 2026 results over the first six completed weeks.</div>
    </section>`;

    const content = q("#app");
    if (content && !q('[data-viz="home"]')) {
      const wrap = document.createElement("div");
      wrap.dataset.viz = "home";
      wrap.innerHTML = hero;
      content.prepend(wrap);
    }
  }

  function decorate() {
    if (typeof state === "undefined") return;
    renderPulse();
    toneStatCards();
    semanticPanels();

    installPressControls();
    homeFun();
    healthAndTrends();
    powerCharts();
    powerInputLedger();
    standingsScatter();
    playoffCharts();
    playoffModelTicket();
    profileCharts();
    profileLeagueQuadrant();
    draftCharts();
    managerCharts();
    opportunityTopStrip();
    opportunityIntelScatter();
    intelCharts();
    leagueMarketCharts();
    myTeamMarketCharts();
  }

  let scheduled = false;
  function scheduleDecorate() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      decorate();
    });
  }

  registerPwa();

  const app = q("#app");
  if (app) {
    new MutationObserver(scheduleDecorate).observe(app, { childList: true, subtree: true });
  }

  document.addEventListener("click", evt => {
    const printButton = evt.target.closest("[data-print-board]");
    if (printButton) {
      window.print();
      return;
    }

    const playerDot = evt.target.closest("[data-intel-player]");
    if (playerDot) {
      updateDossier(playerDot.dataset.intelPlayer);
      return;
    }

    if (evt.target.closest(".nav-item, [data-scope], #profile-team")) {
      setTimeout(scheduleDecorate, 0);
    }
  });
  document.addEventListener("change", scheduleDecorate);

  window.addEventListener("load", () => {
    setTimeout(scheduleDecorate, 120);
    setTimeout(scheduleDecorate, 650);
  });
})();
