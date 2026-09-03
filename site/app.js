/* Plain-JS viewer. All numbers come precomputed in the embedded JSON; this file only renders. */
(function () {
  'use strict';

  const DATA = JSON.parse(document.getElementById('data').textContent);
  const CFG = DATA.config;
  const PLAYER_NAMES = Object.keys(DATA.players).sort((a, b) => a.localeCompare(b));
  const MATCH_BY_ID = {};
  DATA.matches.forEach(m => { MATCH_BY_ID[m.id] = m; });

  const $app = document.getElementById('app');

  /* ---------- strings ---------- */
  function fill(s, vars) {
    return s.replace(/\{(\w+)\}/g, (m, k) => (vars && vars[k] != null) ? vars[k] : m);
  }
  function t(key, vars) {
    const s = I18N.en[key];
    return s == null ? key : fill(s, vars);
  }
  function tTh(key, vars) {
    const s = I18N.th[key];
    return s == null ? '' : fill(s, vars);
  }
  function applyStatic() {
    document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
    document.title = t('title');
  }

  /* ---------- helpers ---------- */
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pct = x => (x == null ? t('none') : Math.round(x * 100) + '%');
  const signed = (x, d) => (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toFixed(d == null ? 1 : d);
  const signedCls = x => (x > 0 ? 'pos' : x < 0 ? 'neg' : '');
  const hashFor = name => '#' + encodeURIComponent(name);
  const link = name => `<a href="${hashFor(name)}">${esc(name)}</a>`;
  const tip = (key, vars) => `<button type="button" class="tip" data-en="${esc(t(key, vars))}" data-th="${esc(tTh(key, vars))}" aria-label="info">ⓘ</button>`;
  const provisionalBadge = () => `<span class="badge">${esc(t('provisional'))}</span>`;

  /* ---------- tooltips: tap to toggle, tap anywhere else to close.
     Each popup shows the English explanation and the Thai version underneath. ---------- */
  const pop = document.createElement('div');
  pop.className = 'tip-pop';
  pop.hidden = true;
  document.body.appendChild(pop);
  let openTip = null;

  function closeTip() { pop.hidden = true; openTip = null; }
  function showTip(btn) {
    pop.innerHTML = `<div class="en">${esc(btn.dataset.en)}</div>` +
      (btn.dataset.th ? `<div class="th">${esc(btn.dataset.th)}</div>` : '');
    pop.hidden = false;
    const r = btn.getBoundingClientRect();
    let left = r.left;
    const w = pop.offsetWidth;
    if (left + w > window.innerWidth - 8) left = window.innerWidth - 8 - w;
    pop.style.left = Math.max(8, left) + 'px';
    pop.style.top = (r.bottom + 6) + 'px';
    openTip = btn;
  }
  document.addEventListener('click', e => {
    const btn = e.target.closest('.tip');
    if (btn && btn !== openTip) { e.preventDefault(); showTip(btn); return; }
    closeTip();
  });
  window.addEventListener('scroll', closeTip, { passive: true });

  /* ---------- charts ---------- */
  function noPlotly(id) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="empty">Charts need an internet connection.</div>';
  }
  const BASE_LAYOUT = {
    margin: { l: 44, r: 12, t: 8, b: 40 },
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: '#fff',
    font: { size: 12, family: 'system-ui, sans-serif' },
    hovermode: 'closest',
  };
  const PLOT_CFG = { responsive: true, displayModeBar: false };

  function lineChart(id, hist, color) {
    if (!window.Plotly) return noPlotly(id);
    const el = document.getElementById(id);
    if (!el) return;
    if (!hist.length) { el.innerHTML = `<div class="empty">${esc(t('never_played'))}</div>`; return; }
    Plotly.newPlot(el, [{
      x: hist.map(h => h.date), y: hist.map(h => h.value),
      mode: 'lines+markers', line: { color, width: 2 }, marker: { size: 5 },
      hovertemplate: '%{x}<br>%{y}<extra></extra>',
    }], Object.assign({}, BASE_LAYOUT, { xaxis: { type: 'date' }, yaxis: { zeroline: true } }), PLOT_CFG);
  }

  function scatterChart(id) {
    if (!window.Plotly) return noPlotly(id);
    const el = document.getElementById(id);
    if (!el) return;
    const pts = DATA.scatter;
    Plotly.newPlot(el, [{
      x: pts.map(p => p.matches), y: pts.map(p => p.win_rate * 100),
      text: pts.map(p => p.name), mode: 'markers',
      marker: { size: 10, opacity: 0.85, color: pts.map(p => p.provisional ? '#c9a227' : '#1f6feb') },
      hovertemplate: '<b>%{text}</b><br>%{x} ' + esc(t('matches_played')).toLowerCase() + '<br>%{y:.0f}% ' + esc(t('win_rate')).toLowerCase() + '<extra></extra>',
    }], Object.assign({}, BASE_LAYOUT, {
      xaxis: { title: { text: t('matches_played') }, rangemode: 'tozero' },
      yaxis: { title: { text: t('win_rate') + ' %' }, range: [-5, 105] },
    }), PLOT_CFG);
    el.on('plotly_click', d => { if (d.points && d.points[0]) location.hash = hashFor(d.points[0].text); });
  }

  const RACE_COLORS = ['#1f6feb', '#d1373b', '#1a8f4c', '#c9a227', '#7c3aed', '#0891b2', '#ea580c'];
  function pointsRaceChart(id) {
    if (!window.Plotly) return noPlotly(id);
    const el = document.getElementById(id);
    if (!el) return;
    const names = DATA.leaderboard_points.slice(0, CFG.top_points_chart);
    if (!names.length) { el.innerHTML = `<div class="empty">${esc(t('none_yet'))}</div>`; return; }
    const traces = names.map((name, i) => {
      const h = DATA.players[name].points_history;
      return {
        name, x: h.map(p => p.date), y: h.map(p => p.value),
        mode: 'lines', line: { color: RACE_COLORS[i % RACE_COLORS.length], width: 2, shape: 'hv' },
        hovertemplate: '<b>' + esc(name) + '</b><br>%{x}<br>%{y} pts<extra></extra>',
      };
    });
    Plotly.newPlot(el, traces, Object.assign({}, BASE_LAYOUT, {
      margin: { l: 36, r: 12, t: 8, b: 40 },
      xaxis: { type: 'date' }, yaxis: { zeroline: true, title: { text: t('points') } },
      legend: { orientation: 'h', y: -0.25, x: 0, font: { size: 12 } },
      hovermode: 'closest',
    }), PLOT_CFG);
  }

  /* ---------- match card ---------- */
  function matchCard(m, focus, chanceNow) {
    const won = team => (team === m.winner);
    const teamHtml = (names, side) => `
      <div class="team ${side} ${won(side === 'left' ? 'A' : 'B') ? 'won' : ''}">
        ${names.map(n => `<span>${n === focus ? `<b>${esc(n)}</b>` : link(n)} <small class="${signedCls(m.deltas[n])}">${signed(m.deltas[n])}</small></span>`).join('')}
      </div>`;
    const score = (m.score_a == null) ? `<span class="score" style="font-size:14px;color:var(--muted)">vs</span>`
      : `<span class="score">${m.score_a}–${m.score_b}</span>`;
    // For a focused player show *their* team's pre-match chance; otherwise the winners' chance.
    // chanceNow (0-1) = chance recomputed with today's ratings, used by hardest wins / easiest losses.
    const chance = chanceNow != null ? chanceNow : focus ? (m.a.includes(focus) ? m.p_a : 1 - m.p_a) : m.winner_prob;
    const chanceLabel = chanceNow != null ? t('win_chance_now') : t('win_chance');
    return `
      <div class="match">
        <div class="head"><span>${esc(m.date)}</span><span>#${m.id}</span></div>
        <div class="teams">${teamHtml(m.a, 'left')}${score}${teamHtml(m.b, 'right')}</div>
        <div class="meta"><span>${esc(chanceLabel)} ${pct(chance)}</span><span>Elo ${tip('tip_delta')}</span></div>
      </div>`;
  }

  /* ---------- views ---------- */
  function streakList(rows, cls) {
    if (!rows.length) return `<div class="empty">${esc(t('none_yet'))}</div>`;
    return rows.map(r => `<div class="streak-row"><span class="who">${link(r.name)}</span><span class="len ${cls}">${esc(t('streak_n', { n: r.len }))}</span></div>`).join('');
  }
  function formList(rows) {
    if (!rows.length) return `<div class="empty">${esc(t('none_yet'))}</div>`;
    return rows.map(r => `<div class="streak-row"><span class="who">${link(r.name)} <small style="color:var(--muted)">${r.matches}${r.matches === 1 ? ' match' : ' matches'}</small></span><span class="len ${signedCls(r.delta)}">${signed(r.delta, 0)}</span></div>`).join('');
  }
  function rankGapList(rows) {
    if (!rows.length) return `<div class="empty">${esc(t('none_yet'))}</div>`;
    return rows.map(r => `<div class="streak-row"><span class="who">${link(r.name)}</span><span class="len" style="font-weight:500;color:var(--muted);font-size:13px">${esc(t('rank_pair', { e: r.rank_elo, p: r.rank_points }))}</span></div>`).join('');
  }
  function twoCol(leftTitle, leftTip, leftBody, rightTitle, rightTip, rightBody) {
    return `<div class="two-col">
        <div><h2>${esc(leftTitle)}${leftTip}</h2><div class="card">${leftBody}</div></div>
        <div><h2>${esc(rightTitle)}${rightTip}</h2><div class="card">${rightBody}</div></div>
      </div>`;
  }

  function renderHome() {
    const rows = DATA.leaderboard_points.map(name => {
      const p = DATA.players[name];
      const eloRank = p.rank_elo != null ? p.rank_elo : provisionalBadge();
      return `<tr class="row-link" data-player="${esc(name)}">
        <td class="num">${p.rank_points}</td>
        <td class="sticky-col"><b>${esc(name)}</b></td>
        <td class="num"><b>${p.points > 0 ? '+' : ''}${p.points}</b></td>
        <td class="num">${p.wins}-${p.losses}</td>
        <td class="num">${Math.round(p.elo)}</td>
        <td class="num">${eloRank}</td></tr>`;
    }).join('');

    const upsets = DATA.upsets.slice(0, CFG.home_upsets).map(u => `
      <div class="match">
        <div class="head"><span>${esc(u.date)}</span><span>${esc(t('win_chance'))} <b>${pct(u.winner_prob)}</b> ${u.provisional ? provisionalBadge() : ''}</span></div>
        <div style="margin-top:4px">${u.winners.map(link).join(' & ')} <span style="color:var(--muted)">${esc(t('beat'))}</span> ${u.losers.map(link).join(' & ')}</div>
      </div>`).join('');

    $app.innerHTML = `
      <h1>${esc(t('leaderboard'))}</h1>
      <p class="sub">${esc(t('leaderboard_sub'))} <b>${esc(t('leaderboard_tap'))}</b><br>${esc(tTh('leaderboard_sub'))}</p>
      <div class="table-wrap"><table>
        <thead><tr><th class="num">${esc(t('rank'))}</th><th class="sticky-col">${esc(t('player'))}</th>
          <th class="num">${esc(t('points'))}${tip('tip_points')}</th>
          <th class="num">${esc(t('record'))}${tip('tip_record')}</th>
          <th class="num">${esc(t('elo'))}${tip('tip_elo', { start: CFG.start_rating })}</th>
          <th class="num">${esc(t('elo_rank'))}${tip('tip_elo_rank', { n: CFG.provisional_until })}</th></tr></thead>
        <tbody>${rows || `<tr><td colspan="6" class="empty">${esc(t('no_matches'))}</td></tr>`}</tbody>
      </table></div>

      <h2>${esc(t('upsets'))}${tip('tip_upsets')}</h2>
      <p class="sub">${esc(t('upsets_sub'))}</p>
      ${upsets || `<div class="empty">${esc(t('no_matches'))}</div>`}

      ${twoCol(t('form_up'), tip('tip_form_up', { n: CFG.form_global_matches }), formList(DATA.form_up),
               t('form_down'), tip('tip_form_down', { n: CFG.form_global_matches }), formList(DATA.form_down))}
      <p class="sub">${esc(t('form_sub', { n: DATA.form_span.matches, from: DATA.form_span.from, to: DATA.form_span.to }))}</p>

      ${twoCol(t('streaks_win'), tip('tip_streaks_win'), streakList(DATA.streaks_win, 'pos'),
               t('streaks_loss'), tip('tip_streaks_loss'), streakList(DATA.streaks_loss, 'neg'))}

      ${twoCol(t('elo_over_points'), tip('tip_elo_over_points'), rankGapList(DATA.elo_over_points),
               t('points_over_elo'), tip('tip_points_over_elo'), rankGapList(DATA.points_over_elo))}
      <p class="sub">${esc(t('rank_gap_sub', { n: CFG.min_rank_gap_matches }))}</p>

      <h2>${esc(t('scatter'))}${tip('tip_scatter')}</h2>
      <p class="sub">${esc(t('scatter_sub'))}</p>
      <div class="card"><div id="scatter" class="chart"></div></div>

      <h2>${esc(t('points_race'))}${tip('tip_points_race')}</h2>
      <p class="sub">${esc(t('points_race_sub', { n: CFG.top_points_chart }))}</p>
      <div class="card"><div id="points-race" class="chart tall"></div></div>`;

    $app.querySelectorAll('tr.row-link').forEach(tr => {
      tr.addEventListener('click', e => { if (!e.target.closest('.tip')) location.hash = hashFor(tr.dataset.player); });
    });
    scatterChart('scatter');
    pointsRaceChart('points-race');
  }

  function renderPlayers(notFound) {
    const list = PLAYER_NAMES.map(name => {
      const p = DATA.players[name];
      const sub = p.matches ? `${Math.round(p.elo)} · ${p.wins}-${p.losses}` : esc(t('never_played'));
      return `<a href="${hashFor(name)}" data-name="${esc(name.toLowerCase())}">${esc(name)}<small>${sub}</small></a>`;
    }).join('');
    $app.innerHTML = `
      <p><a href="#home">${esc(t('back_home'))}</a></p>
      <h1>${esc(t('pick_player'))}</h1>
      ${notFound ? `<div class="card" style="background:var(--warn-bg);color:var(--warn-ink)">${esc(t('player_not_found', { name: notFound }))}</div>` : ''}
      <input id="search" class="search" type="search" autocomplete="off" placeholder="${esc(t('search_placeholder'))}">
      <div class="picker" id="picker">${list}</div>
      <div class="empty" id="no-results" hidden>${esc(t('no_results'))}</div>`;
    const input = document.getElementById('search');
    const items = Array.from(document.querySelectorAll('#picker a'));
    input.addEventListener('input', () => {
      const q = input.value.trim().toLowerCase();
      let shown = 0;
      items.forEach(a => { const hit = !q || a.dataset.name.includes(q); a.hidden = !hit; shown += hit; });
      document.getElementById('no-results').hidden = shown > 0;
    });
    if (!notFound) input.focus({ preventScroll: true });
  }

  function statCard(label, value, opts) {
    opts = opts || {};
    return `<div class="stat ${opts.cls || ''}"><div class="label">${esc(label)}${opts.tip || ''}</div><div class="value">${value}</div></div>`;
  }

  function renderPlayer(name) {
    const p = DATA.players[name];
    const streak = p.streak_current.type
      ? `<span class="${p.streak_current.type === 'W' ? 'pos' : 'neg'}">${p.streak_current.len}${p.streak_current.type}</span>` : t('none');
    const form = p.form.length ? `<div class="form">${p.form.map(r => `<span class="pill ${r}">${r}</span>`).join('')}</div>` : t('none');
    const eloVal = `${Math.round(p.elo)} <small>${p.rank_elo != null ? '#' + p.rank_elo : esc(t('unranked'))}</small>`;
    const pointsVal = `${p.points > 0 ? '+' : ''}${p.points} <small>${p.rank_points != null ? '#' + p.rank_points : ''}</small>`;

    const partners = p.partners.map(x => `<tr>
        <td class="sticky-col">${link(x.name)}</td><td class="num">${x.matches}</td><td class="num">${x.wins}</td>
        <td class="num">${pct(x.win_rate)}</td><td class="num">${x.expected_wins.toFixed(1)}</td>
        <td class="num ${signedCls(x.diff)}">${signed(x.diff)}</td></tr>`).join('');

    const oppCard = (label, key, o) => statCard(label,
      o ? `${link(o.name)} <small>${o.wins}-${o.losses}</small>` : `<small>${esc(t('none'))}</small>`,
      { tip: tip(key, { n: CFG.min_opponent_matches }) });

    const cards = items => items.map(x => matchCard(MATCH_BY_ID[x.match_id], name, x.p_now)).join('') || `<div class="card empty">${esc(t('none_yet'))}</div>`;
    const recent = DATA.matches.filter(m => m.a.includes(name) || m.b.includes(name)).slice(-3).reverse();

    $app.innerHTML = `
      <p><a href="#home">${esc(t('back_home'))}</a></p>
      <h1>${esc(name)} ${p.provisional ? provisionalBadge() : ''}</h1>
      <div class="stats">
        ${statCard(t('matches'), p.matches)}
        ${statCard(t('record'), `${p.wins}-${p.losses}`, { tip: tip('tip_record') })}
        ${statCard(t('win_rate'), pct(p.win_rate), { tip: tip('tip_win_rate') })}
        ${statCard(t('points'), pointsVal, { tip: tip('tip_points') })}
        ${statCard(t('elo_rating'), eloVal, { tip: tip('tip_elo', { start: CFG.start_rating }) })}
        ${statCard(t('current_streak'), streak, { tip: tip('tip_streak') })}
        ${statCard(t('longest_win'), p.longest_win, { cls: 'win' })}
        ${statCard(t('longest_loss'), p.longest_loss, { cls: 'loss' })}
        ${statCard(t('last_played'), p.last_played ? esc(p.last_played) : t('none'))}
        ${statCard(t('form_delta', { n: CFG.form_window }), p.form_delta == null ? t('none') : `<span class="${signedCls(p.form_delta)}">${signed(p.form_delta, 0)}</span>`, { tip: tip('tip_form_delta', { n: CFG.form_window }) })}
        ${statCard(t('peak_elo'), p.peak_elo ? `${Math.round(p.peak_elo.value)} <small>${esc(p.peak_elo.date)}</small>` : t('none'), { tip: tip('tip_peak_elo') })}
        ${statCard(t('low_elo'), p.low_elo ? `${Math.round(p.low_elo.value)} <small>${esc(p.low_elo.date)}</small>` : t('none'), { tip: tip('tip_low_elo') })}
        ${statCard(t('avg_opponent'), p.avg_opponent_elo == null ? t('none') : Math.round(p.avg_opponent_elo), { tip: tip('tip_avg_opponent') })}
        ${statCard(t('avg_partner'), p.avg_partner_elo == null ? t('none') : Math.round(p.avg_partner_elo), { tip: tip('tip_avg_partner') })}
      </div>
      <div class="card"><div class="label" style="font-size:12px;color:var(--muted)">${esc(t('form', { n: CFG.form_length }))}${tip('tip_form', { n: CFG.form_length })}</div>${form}</div>

      <h2>${esc(t('elo_chart'))}</h2>
      <div class="card"><div id="elo-chart" class="chart"></div></div>
      <h2>${esc(t('points_chart'))}</h2>
      <div class="card"><div id="points-chart" class="chart"></div></div>

      <h2>${esc(t('partners'))}</h2>
      ${partners ? `<div class="table-wrap"><table>
        <thead><tr><th class="sticky-col">${esc(t('partner'))}</th><th class="num">${esc(t('matches_short'))}</th><th class="num">${esc(t('wins_short'))}</th>
          <th class="num">${esc(t('win_rate'))}</th><th class="num">${esc(t('expected'))}${tip('tip_expected')}</th><th class="num">${esc(t('diff'))}${tip('tip_diff')}</th></tr></thead>
        <tbody>${partners}</tbody></table></div>`
        : `<div class="card empty">${esc(t('no_partners'))}</div>`}

      <h2>${esc(t('opponents'))}</h2>
      <div class="stats">
        ${oppCard(t('most_faced'), 'tip_most_faced', p.most_faced)}
        ${oppCard(t('nemesis'), 'tip_nemesis', p.nemesis)}
        ${oppCard(t('victim'), 'tip_victim', p.victim)}
      </div>

      <h2>${esc(t('hardest_wins'))}${tip('tip_hardest_wins')}</h2>
      ${cards(p.hardest_wins)}
      <h2>${esc(t('easiest_losses'))}${tip('tip_easiest_losses')}</h2>
      ${cards(p.easiest_losses)}

      <h2>${esc(t('recent_matches'))}</h2>
      ${recent.map(m => matchCard(m, name)).join('') || `<div class="card empty">${esc(t('none_yet'))}</div>`}
      `;

    lineChart('elo-chart', p.elo_history, '#1f6feb');
    lineChart('points-chart', p.points_history, '#1a8f4c');
  }

  /* ---------- router ---------- */
  let lastPath = null;
  function route(keepScroll) {
    closeTip();
    const raw = location.hash.slice(1);
    const qIdx = raw.indexOf('?');
    const pathRaw = qIdx >= 0 ? raw.slice(0, qIdx) : raw;
    const q = new URLSearchParams(qIdx >= 0 ? raw.slice(qIdx + 1) : '');
    let path;
    try { path = decodeURIComponent(pathRaw); } catch (e) { path = pathRaw; }
    if (!path) path = 'home';

    let tab;
    if (path === 'home') { tab = 'home'; renderHome(); }
    else if (path === 'players') { tab = 'players'; renderPlayers(null); }
    else if (DATA.players[path]) { tab = 'players'; renderPlayer(path); }
    else { tab = 'players'; renderPlayers(path); }

    if (!keepScroll && path !== lastPath) window.scrollTo(0, 0);
    lastPath = path;
  }

  window.addEventListener('hashchange', () => route(false));
  document.getElementById('generated-at').textContent = DATA.generated_at;
  applyStatic();
  route(false);
})();
