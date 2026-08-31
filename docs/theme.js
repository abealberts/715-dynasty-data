
/* ==========================================================================
   715 DYNASTY HQ — PHASE 4.5 VISUAL ENHANCEMENTS
   Pure presentation layer. Reads existing `state`; does not alter analytics.
   ========================================================================== */

(() => {
  const COLORS = {
    lime: "#d7ff47",
    cyan: "#42d9ff",
    coral: "#ff6b57",
    violet: "#a987ff",
    amber: "#ffc857",
    mint: "#70e3aa",
    slate: "#708090",
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
      ["Draft Capital", metrics.draft_capital, COLORS.violet],
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

    homeFun();
    powerCharts();
    standingsScatter();
    playoffCharts();
    profileCharts();
    draftCharts();
    managerCharts();
    opportunityTopStrip();
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

  const app = q("#app");
  if (app) {
    new MutationObserver(scheduleDecorate).observe(app, { childList: true, subtree: true });
  }

  document.addEventListener("click", evt => {
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
