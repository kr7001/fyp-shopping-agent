/* The project site's behaviour: switching pages, the theme, and every table and figure,
   built from window.SITE, which docs/build_site.py generates from the repository. No
   figure lives in this file. A placeholder whose figure is missing shows "?" rather than
   a stale number. */
(function () {
  'use strict';

  const S = window.SITE;
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const money = (x, d) => (x == null ? '' : '$' + Number(x).toFixed(d == null ? 3 : d));
  const pfmt = (p) => Number(p).toFixed(5).replace(/0+$/, '').replace(/\.$/, '');
  const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
  const sum = (xs) => xs.reduce((a, b) => a + b, 0);

  if (!S) {
    document.getElementById('main').innerHTML =
      '<div class="block"><h2>The data file is missing</h2><p>Run <code>make site</code> to build ' +
      '<code>docs/site-data.js</code>, then reload.</p></div>';
    return;
  }

  // ------------------------------------------------------------------ the clothing cells

  const C = S.clothing;
  const names = C.names;
  const nameOf = (label) => names.find((n) => C.info[n].label === label);
  const cell = (label) => C.cells[nameOf(label)];
  const info = (label) => C.info[nameOf(label)];
  let reading = 'menu';
  const right = (c) => (reading === 'menu' ? c.right : c.right_buyable);
  const opened = (c) => (reading === 'menu' ? c.opened : c.opened_buyable);
  const test = (a, b, measure, rd, distinct) =>
    C.tests.find((t) => t.a === a && t.b === b && t.measure === measure &&
      t.reading === (rd || 'menu') && t.distinct === !!distinct);
  const errorCount = (labels, kind) => sum(labels.map((l) =>
    ((C.errors[nameOf(l)] || []).find((e) => e[0] === kind) || [kind, []])[1].length));

  // Every inline figure, by name. Pages use <span data-f="name">.
  const F = {};
  function figures() {
    ['1', '2', '3', '5'].forEach((l) => {
      const c = cell(l);
      F['c' + l + '.runs'] = c.runs;
      F['c' + l + '.right'] = c.right;
      F['c' + l + '.right_b'] = c.right_buyable;
      F['c' + l + '.opened'] = c.opened;
      F['c' + l + '.opened_b'] = c.opened_buyable;
      F['c' + l + '.distinct'] = c.distinct;
      F['c' + l + '.cost'] = money(c.cost);
      F['c' + l + '.calls'] = Math.round(c.calls);
      F['c' + l + '.median'] = c.median_opened;
      F['c' + l + '.batch_cost'] = money(c.batch_cost, 2);
    });
    F['runs.cells'] = sum(names.map((n) => C.cells[n].runs));
    F['ratio51'] = (cell('5').cost / cell('1').cost).toFixed(1);
    F['p.correct.2v1'] = pfmt(test('2', '1', 'correct').p_question);
    F['p.correct.2v1.pooled'] = pfmt(test('2', '1', 'correct').p_pooled);
    F['p.opened.2v1'] = pfmt(test('2', '1', 'opened').p_question);
    F['p.correct.5v1'] = pfmt(test('5', '1', 'correct').p_question);
    F['p.correct.5v2'] = pfmt(test('5', '2', 'correct').p_question);
    F['p.opened.3v1'] = pfmt(test('3', '1', 'opened', 'menu', true).p_question);
    F['p.correct.5v1.b'] = pfmt(test('5', '1', 'correct', 'buyable').p_question);
    const refused = Object.values(C.refusal);
    F['refusal.c1.refused'] = C.refusal[nameOf('1')].refused;
    F['refusal.c1.wrong'] = C.refusal[nameOf('1')].wrong;
    F['refusal.right'] = sum(refused.map((r) => r.right));
    F['refusal.right_refused'] = sum(refused.map((r) => r.right_refused));
    F['err25.wrong'] = sum(['2', '5'].map((l) => cell(l).runs - cell(l).right));
    F['err25.offer'] = errorCount(['2', '5'], 'read "offer" as "can sell it now"');
    F['err25.steps'] = errorCount(['2', '5'], 'ran out of its 100 steps');
    F['err25.reveal'] = errorCount(['2', '5'], 'read the price before the page revealed it');
    F['err25.unopened'] = errorCount(['2', '5'], 'did not open what the answer needs');
    F['err1.unopened'] = errorCount(['1'], 'did not open what the answer needs');
    F['window.c5'] = C.agent_window[nameOf('5')].runs.length;
    F['window.c5.of'] = C.agent_window[nameOf('5')].of;
    F['experiments.batches'] = S.experiments.length;
    F['experiments.runs'] = sum(S.experiments.map((e) => e.runs));
    F['lessons'] = sum(S.lessons.groups.map((g) => g.rows.length));
    F['parked'] = S.parked.length;
    F['tests.unit'] = sum(S.tests.unit.map((f) => sum(f.classes.map((c) => c.tests.length))));
    F['tests.unit.files'] = S.tests.unit.length;
    F['tests.mod'] = S.tests.mod.length;
    F['tests.regression'] = S.tests.regression_questions;
    F['v.targeting'] = S.tests.versions.targeting;
    F['v.planner'] = S.tests.versions.planner;
    F['built.date'] = S.built ? S.built.date : '';
    F['built.commit'] = S.built ? S.built.commit : '';
    F['budget.left'] = money(S.budget.left, 2);
    const w = (m, a) => S.water.find((r) => r.market === m && r.arm_name === a);
    const cut = (a, b, k) => Math.round(100 * (1 - a[k] / b[k]));
    [['riv', 'Rivenhall', 'targeting+gate v2'], ['cal', 'Calderwood', 'targeting+gate v3']]
      .forEach(([key, market, arm]) => {
        const s = w(market, arm);
        const e = w(market, 'exhaustive');
        const u = w(market, 'unmodified');
        F['w.' + key + '.actions_cut'] = cut(s, e, 'actions');
        F['w.' + key + '.cost_cut'] = cut(s, e, 'cost');
        F['w.' + key + '.s'] = s.correct + ' of ' + s.runs + ' correct, ' + s.refused + ' refused, ' + s.other + ' wrong';
        F['w.' + key + '.e'] = e.correct + ' of ' + e.runs;
        F['w.' + key + '.u'] = u.correct + ' of ' + u.runs;
      });
  }

  function fill(root) {
    $$('[data-f]', root).forEach((el) => {
      const v = F[el.dataset.f];
      el.textContent = v == null ? '?' : v;
      if (v == null) console.warn('no figure named', el.dataset.f);
    });
    $$('[data-html]', root).forEach((el) => {
      const v = el.dataset.html.split('.').reduce((o, k) => (o ? o[k] : undefined), S);
      el.innerHTML = v == null ? '<p>?</p>' : v;
    });
  }

  // ------------------------------------------------------------------------ renderers

  const R = {};

  R.cellBars = (el) => {
    el.innerHTML = ['1', '2', '3', '5'].map((l) => {
      const c = cell(l);
      return '<div class="bar-row"><div class="who">' + esc(l + '. ' + info(l).title) +
        '<small>' + money(c.cost) + ' a run, ' + Math.round(c.calls) + ' tool calls</small></div>' +
        '<div class="bar-pair">' +
        '<div class="bar"><span>Opened what it needs</span><div class="track"><i style="width:' +
        pct(opened(c), c.runs) + '%"></i></div><span class="val">' + opened(c) + ' of ' + c.runs + '</span></div>' +
        '<div class="bar"><span>Correct</span><div class="track alt"><i style="width:' +
        pct(right(c), c.runs) + '%"></i></div><span class="val">' + right(c) + ' of ' + c.runs + '</span></div>' +
        '</div></div>';
    }).join('');
  };

  R.cellsTable = (el) => {
    const rows = ['1', '2', '3', '5'].map((l) => {
      const c = cell(l);
      return '<tr><td><b>' + esc(l + '. ' + info(l).title) + '</b><span class="sub">' + esc(info(l).change) + '</span></td>' +
        '<td class="num">' + right(c) + ' of ' + c.runs + '</td>' +
        '<td class="num">' + opened(c) + ' of ' + c.runs + '</td>' +
        '<td class="num">' + c.median_opened + '</td>' +
        '<td class="num">' + Math.round(c.calls) + '</td>' +
        '<td class="num">' + money(c.cost) + '</td>' +
        '<td class="num">' + c.distinct + ' of ' + c.runs + '</td></tr>';
    }).join('');
    el.innerHTML = '<div class="table-wrap"><table><thead><tr><th>Cell</th><th class="num">Correct</th>' +
      '<th class="num">Opened what it needs</th><th class="num">Median listings opened</th>' +
      '<th class="num">Tool calls a run</th><th class="num">Cost a run</th><th class="num">Distinct runs</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  };

  R.questionsTable = (el) => {
    const labels = ['1', '2', '3', '5'];
    const rows = C.questions_detail.map((q) => {
      const cols = labels.map((l) => {
        const c = cell(l);
        if (!q.gated) {
          return '<td class="num">' + (c.control ? c.control.correct + ' of ' + c.control.of : '<span class="sub">not asked</span>') + '</td>';
        }
        const p = c.per_question[q.id];
        return '<td class="num">' + p.correct + ' / ' + p.covered + ' of ' + p.of + '</td>';
      }).join('');
      return '<tr><td><b>' + esc(q.short) + '</b>' + (q.gated ? '' : ' <span class="chip">control</span>') +
        '<span class="sub">' + esc(q.question) + '</span></td><td>' + esc(q.answer) + '</td>' +
        '<td class="mono">' + esc(q.strategy) + '</td>' + cols + '</tr>';
    }).join('');
    el.innerHTML = '<div class="table-wrap"><table><thead><tr><th>Question</th><th>Answer key</th><th>Kind</th>' +
      labels.map((l) => '<th class="num">Cell ' + l + '</th>').join('') + '</tr></thead><tbody>' + rows +
      '</tbody></table></div>';
  };

  const strength = (p) => (p < 0.01 ? '<span class="chip good">p &lt; 0.01</span>'
    : p < 0.05 ? '<span class="chip warn">p &lt; 0.05</span>'
      : '<span class="chip">no clear difference</span>');

  R.testsTable = (el) => {
    const rows = C.tests.filter((t) => t.reading === reading).map((t) =>
      '<tr><td><b>' + t.a + ' vs ' + t.b + '</b><span class="sub">' + esc(info(t.a).title) + ' against ' +
      esc(info(t.b).title) + '</span></td><td>' + (t.measure === 'opened' ? 'opened what it needs' : 'correct') +
      '</td><td>' + esc(t.text) + '</td><td class="num">' + pfmt(t.p_question) + '</td><td class="num">' +
      pfmt(t.p_pooled) + '</td><td>' + (t.distinct ? 'distinct runs' : 'every run') + '</td><td>' +
      strength(t.p_question) + '</td></tr>').join('');
    el.innerHTML = '<div class="table-wrap"><table><thead><tr><th>Comparison</th><th>Measure</th><th>Counts</th>' +
      '<th class="num">p, by question</th><th class="num">p, pooled</th><th>Unit</th><th></th></tr></thead><tbody>' +
      rows + '</tbody></table></div>';
  };

  R.errorsTable = (el) => {
    const rows = ['1', '2', '3', '5'].map((l) => {
      const kinds = C.errors[nameOf(l)] || [];
      if (!kinds.length) return '';
      return kinds.map((k, i) => '<tr>' + (i === 0 ? '<td rowspan="' + kinds.length + '"><b>' +
        esc(l + '. ' + info(l).title) + '</b></td>' : '') + '<td>' + esc(k[0]) + '</td><td class="num">' +
        k[1].length + '</td><td class="mono">' + esc(k[1].join(', ')) + '</td></tr>').join('');
    }).join('');
    el.innerHTML = '<div class="table-wrap"><table><thead><tr><th>Cell</th><th>Kind of error</th>' +
      '<th class="num">Runs</th><th>Which</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  };

  R.refusalTable = (el) => {
    const rows = Object.entries(C.refusal).map(([n, r]) => '<tr><td><b>' + esc(C.info[n].label + '. ' +
      C.info[n].title) + '</b></td><td class="num">' + r.wrong + '</td><td class="num">' + r.refused +
      '</td><td class="num">' + r.right + '</td><td class="num">' + r.right_refused + '</td></tr>').join('');
    el.innerHTML = '<div class="table-wrap"><table><thead><tr><th>Cell</th><th class="num">Not correct</th>' +
      '<th class="num">Of those, refused</th><th class="num">Correct</th><th class="num">Of those, refused</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  };

  R.checksBlock = (el) => {
    const label = (b) => (C.silence.find((s) => s.batch === b) || {}).cell || '';
    const rescored = C.rescored.map((r) => '<li><code>' + esc(r.batch) + '</code> ' + esc(r.run) + ': ' +
      esc(r.from) + ' to ' + esc(r.to) + '. ' + esc(r.reason) + '</li>').join('');
    const silence = C.silence.map((s) => '<tr><td class="mono">' + esc(s.batch) + '</td><td>' + esc(s.cell) +
      '</td><td class="num">' + (s.longest_silence_s ? Math.round(s.longest_silence_s) + ' s'
        : '<span class="sub">no timestamps, longest run ' + Math.round(s.longest_run_s) + ' s</span>') +
      '</td><td>' + (s.suspended.length ? s.suspended.map((x) => esc(x[0]) + ' (' + Math.round(x[1]) + ' s)').join(', ')
        : 'none') + '</td></tr>').join('');
    const per = (key, fmt) => ['1', '2', '3', '5'].map((l) => '<tr><td>' + esc(l + '. ' + info(l).title) +
      '</td><td>' + fmt(C[key][nameOf(l)]) + '</td></tr>').join('');
    el.innerHTML =
      '<h4>Answers re-scored after a scorer fix</h4><ul>' + (rescored || '<li>none</li>') + '</ul>' +
      '<h4>Silence in each log, the suspended run rule</h4><div class="table-wrap"><table><thead><tr><th>Batch</th>' +
      '<th>Cell</th><th class="num">Longest silence</th><th>Suspended, void</th></tr></thead><tbody>' + silence +
      '</tbody></table></div>' +
      '<h4>Runs where the agent set the window limit itself</h4><div class="table-wrap"><table><tbody>' +
      per('agent_window', (w) => w.runs.length + ' of ' + w.of + (w.runs.length ? ': ' + esc(w.runs.join(', ')) : '')) +
      '</tbody></table></div>' +
      '<h4>Sizes chosen inside batched steps</h4><div class="table-wrap"><table><tbody>' +
      per('batch_selections', (n) => String(n)) + '</tbody></table></div>' +
      '<h4>Scripts that change a size and read the price in the same instant</h4><div class="table-wrap"><table><tbody>' +
      per('same_instant', (s) => s.runs.length + ' of ' + s.of + (s.runs.length ? ': ' +
        esc(s.runs.map((r) => r[0]).join(', ')) : '')) + '</tbody></table></div>';
    void label;
  };

  R.costTable = (el) => {
    const cellOf = {};
    names.forEach((n) => C.info[n].batches.forEach((b) => { cellOf[b] = C.info[n].label; }));
    const rows = C.cost.map((c) => '<tr><td class="mono">' + esc(c.batch) + '</td><td>' + (cellOf[c.batch] ||
      'pilot') + '</td><td class="num">' + money(c.charges, 4) + '</td><td class="num">' +
      (c.moved == null ? '<span class="sub">needs the live account</span>' : money(c.moved, 4)) +
      '</td><td class="num">' + (c.moved == null ? '' : (c.moved - c.charges >= 0 ? '+' : '') +
        (c.moved - c.charges).toFixed(4)) + '</td></tr>').join('');
    el.innerHTML = '<div class="table-wrap"><table><thead><tr><th>Batch</th><th>Cell</th>' +
      '<th class="num">Provider charges</th><th class="num">Account moved</th><th class="num">Difference</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  };

  R.waterTable = (el) => {
    const rows = S.water.map((w) => '<tr><td>' + esc(w.market) + '</td><td><b>' + esc(w.arm) + '</b></td>' +
      '<td class="num">' + w.runs + '</td><td class="num">' + w.correct + '</td><td class="num">' + w.refused +
      '</td><td class="num">' + w.other + '</td><td class="num">' + (w.actions == null ? '' : w.actions.toFixed(1)) +
      '</td><td class="num">' + money(w.cost) + '</td><td class="mono">' + esc(w.batches.join(', ')) + '</td></tr>').join('');
    el.innerHTML = '<div class="table-wrap"><table><thead><tr><th>Market</th><th>Arm</th><th class="num">Runs</th>' +
      '<th class="num">Correct</th><th class="num">Refused</th><th class="num">Wrong or no answer</th>' +
      '<th class="num">Actions a run</th><th class="num">Cost a run</th><th>Batches</th></tr></thead><tbody>' +
      rows + '</tbody></table></div>';
  };

  R.experimentsSummary = (el) => {
    const by = (k) => S.experiments.reduce((m, e) => { m[e[k] || 'not recorded'] = (m[e[k] || 'not recorded'] || 0) + e.runs; return m; }, {});
    const markets = by('market');
    el.innerHTML = '<div class="stats">' +
      '<div class="stat"><b>' + S.experiments.length + '</b><span>batches on disk</span></div>' +
      '<div class="stat"><b>' + sum(S.experiments.map((e) => e.runs)) + '</b><span>runs in them</span></div>' +
      Object.entries(markets).map(([m, n]) => '<div class="stat"><b>' + n + '</b><span>runs on ' + esc(m) +
        '</span></div>').join('') + '</div>';
  };

  R.experimentsTable = (el) => {
    const markets = [...new Set(S.experiments.map((e) => e.market || 'not recorded'))];
    const statuses = [...new Set(S.experiments.map((e) => e.status))];
    const agents = [...new Set(S.experiments.map((e) => e.scaffold))];
    const opt = (xs) => '<option value="">all</option>' + xs.map((x) => '<option>' + esc(x) + '</option>').join('');
    el.innerHTML = '<div class="toolbar"><label>Market <select data-x="market">' + opt(markets) + '</select></label>' +
      '<label>Agent <select data-x="scaffold">' + opt(agents) + '</select></label>' +
      '<label>Status <select data-x="status">' + opt(statuses) + '</select></label>' +
      '<input type="search" placeholder="Search batch, arm, file" data-x="q" aria-label="Search experiments">' +
      '<span data-x="count"></span></div><div class="table-wrap"><table><thead><tr><th>Date</th><th>Batch</th>' +
      '<th>Market</th><th>Questions</th><th>Model</th><th>Agent</th><th>Arm</th><th>Probe</th><th>Shop</th>' +
      '<th class="num">Runs</th><th class="num">Correct</th><th class="num">Refused</th><th class="num">Cost</th>' +
      '<th>Status</th></tr></thead><tbody></tbody></table></div>';
    const body = $('tbody', el);
    const draw = () => {
      const f = {};
      $$('[data-x]', el).forEach((x) => { f[x.dataset.x] = x.value; });
      const q = (f.q || '').toLowerCase();
      const shown = S.experiments.filter((e) => (!f.market || (e.market || 'not recorded') === f.market) &&
        (!f.scaffold || e.scaffold === f.scaffold) && (!f.status || e.status === f.status) &&
        (!q || [e.batch, e.arm, e.tasks, e.cell && 'cell ' + e.cell].join(' ').toLowerCase().includes(q)));
      body.innerHTML = shown.map((e) => {
        const chip = e.status === 'current' ? (e.cell ? '<span class="chip good">cell ' + esc(e.cell) + '</span>'
          : '<span class="chip">current</span>') : '<span class="chip ' + (e.status === 'void' ? 'bad' : 'warn') +
          '" title="' + esc(e.why) + '">' + esc(e.status) + '</span>' + (e.cell ? ' <span class="chip good">cell ' +
            esc(e.cell) + '</span>' : '');
        return '<tr' + (e.status === 'current' ? '' : ' class="muted"') + '><td class="mono">' + esc(e.date) +
          '</td><td class="mono">' + esc(e.batch) + '</td><td>' + esc(e.market || '') + '</td><td class="mono">' +
          esc(e.tasks || 'not recorded') + '</td><td>' + esc(e.model) + '</td><td>' + esc(e.scaffold) + '</td><td>' +
          esc(e.arm) + '</td><td>' + esc(e.probe) + '</td><td>' + esc(e.shop) + '</td><td class="num">' + e.runs +
          '</td><td class="num">' + e.correct + '</td><td class="num">' + e.refused + '</td><td class="num">' +
          money(e.cost, 2) + '</td><td>' + chip + (e.why ? '<span class="sub">' + esc(e.why) + '</span>' : '') +
          '</td></tr>';
      }).join('');
      $('[data-x="count"]', el).textContent = shown.length + ' of ' + S.experiments.length + ' batches';
    };
    $$('[data-x]', el).forEach((x) => x.addEventListener('input', draw));
    draw();
  };

  const variantText = (v) => v.option + ' ' + money(v.price, 2) + (v.qty === 0 ? ' (sold out)' : '');

  const instanceRows = (inst) => {
    const rows = [];
    const who = (x) => (x ? esc(x.seller) + (x.price != null ? ' at ' + money(x.price, 2)
      : x.from_price != null ? ', advertised ' + money(x.from_price, 2) : '') : '');
    if (inst.target_option) rows.push(['Size the questions ask about', esc(inst.target_option)]);
    if (inst.winner) rows.push(['Cheapest for that size', who(inst.winner)]);
    if (inst.cheapest_card) rows.push(['Lowest advertised price, the trap', who(inst.cheapest_card)]);
    if (inst.cheapest_sold_out) rows.push(['Cheapest listed price, sold out', who(inst.cheapest_sold_out)]);
    if (inst.best_per_litre) rows.push(['Best price per litre', esc(inst.best_per_litre.seller) + ', ' +
      esc(inst.best_per_litre.option) + ', ' + money(inst.best_per_litre.price_per_litre, 3) + ' a litre']);
    if (inst.listings_with_target != null) rows.push(['Listings offering that size', inst.listings_with_target +
      ' of ' + inst.listings + (inst.listings_target_buyable != null ? ', ' + inst.listings_target_buyable +
        ' buyable and ' + inst.listings_target_sold_out + ' sold out' : '')]);
    if (inst.oracle_min_opens != null) rows.push(['Fewest listings a sound answer must open', inst.oracle_min_opens]);
    if (inst.prunable_by_bound != null) rows.push(['Listings the advertised price rules out', inst.prunable_by_bound]);
    if (inst.from_price_range) rows.push(['Advertised prices', money(inst.from_price_range[0], 2) + ' to ' +
      money(inst.from_price_range[1], 2)]);
    return rows;
  };

  R.markets = (el) => {
    const mk = S.catalogues.markets;
    el.innerHTML = '<div class="tabs" data-tabs="mk" role="tablist">' + mk.map((m, i) => '<button class="tab" role="tab" ' +
      'data-tab="' + i + '" aria-selected="' + (i === 3) + '">' + esc(m.market) + '</button>').join('') + '</div>' +
      mk.map((m, i) => {
        const kv = [['File', '<code>env/fixtures/' + esc(m.file) + '</code>'], ['Listings', m.listings.length],
          ['Sizes', esc(m.options.join(', '))]];
        if (m.seed != null) kv.push(['Seed, accepted on draw', m.seed + ', draw ' + m.attempt]);
        kv.push(['Question files', esc(m.tasks.join(', '))]);
        const rows = kv.concat(instanceRows(m.instance));
        const rules = m.rules.length ? '<h4>The rules every draw had to pass</h4><div class="table-wrap"><table><tbody>' +
          m.rules.map((r) => '<tr><td class="num">' + r.n + '</td><td class="mono">' + esc(r.name) + '</td><td>' +
            esc(r.text) + '</td></tr>').join('') + '</tbody></table></div>' : '';
        const cmd = m.command ? '<h4>Regenerate it</h4><div class="cmd"><pre>' + esc(m.command) + '</pre></div>' +
          (m.tasks_command ? '<div class="cmd"><pre>' + esc(m.tasks_command) + '</pre></div>' : '') +
          '<p class="note">Both rewrite the committed files. <code>make test</code> checks they come out byte for byte the same.</p>' : '';
        const listing = '<details><summary>All ' + m.listings.length + ' listings</summary><div><div class="table-wrap">' +
          '<table><thead><tr><th>SKU</th><th>Seller</th><th class="num">Advertised</th><th>Sizes and prices</th></tr></thead><tbody>' +
          m.listings.map((l) => '<tr><td class="mono">' + esc(l.sku) + '</td><td>' + esc(l.seller || l.name) +
            '</td><td class="num">' + money(l.from, 2) + '</td><td>' + esc(l.variants.map(variantText).join(' · ')) +
            '</td></tr>').join('') + '</tbody></table></div></div></details>';
        return '<div class="panel' + (i === 3 ? ' on' : '') + '" data-panel="mk:' + i + '"><div class="prose">' +
          '<p>' + esc(m.how) + '</p></div><dl class="kv">' + rows.map((r) => '<dt>' + r[0] + '</dt><dd>' + r[1] +
            '</dd>').join('') + '</dl>' + rules + cmd + listing + '</div>';
      }).join('');
    tabs(el);
  };

  R.ledger = (el) => {
    el.innerHTML = '<div class="table-wrap"><table><thead><tr><th>Market</th><th>Listings</th><th>Status</th>' +
      '<th>What it may still be used for</th></tr></thead><tbody>' + S.catalogues.ledger.map((r) => '<tr><td><b>' +
      r.market + '</b></td><td>' + esc(r.listings) + '</td><td>' + r.status + '</td><td>' + r.use + '</td></tr>').join('') +
      '</tbody></table></div>';
  };

  R.taskFiles = (el) => {
    el.innerHTML = '<div class="table-wrap"><table><thead><tr><th>File</th><th class="num">Questions</th>' +
      '<th class="num">Gated</th><th>Where it came from</th></tr></thead><tbody>' + S.catalogues.tasks.map((t) =>
      '<tr><td class="mono">' + esc(t.file) + '</td><td class="num">' + t.questions + '</td><td class="num">' + t.gated +
      '</td><td>' + esc(t.how) + '</td></tr>').join('') + '</tbody></table></div>';
  };

  R.lessons = (el) => {
    const who = { C: 'coder', V: 'verifier', I: 'insights', G: 'guard', M: 'main' };
    el.innerHTML = '<div class="toolbar"><label>Group <select data-l="group"><option value="">all</option>' +
      S.lessons.groups.map((g) => '<option>' + esc(g.group) + '</option>').join('') + '</select></label>' +
      '<label>Enforced by <select data-l="who"><option value="">anyone</option>' + Object.entries(who).map(([k, v]) =>
        '<option value="' + k + '">' + v + '</option>').join('') + '</select></label>' +
      '<input type="search" placeholder="Search the lessons" data-l="q" aria-label="Search the lessons"></div>' +
      '<div class="table-wrap"><table><thead><tr><th class="num">#</th><th>What happened</th><th>The rule now</th>' +
      '<th>Enforced by</th></tr></thead><tbody></tbody></table></div>';
    const body = $('tbody', el);
    const draw = () => {
      const g = $('[data-l="group"]', el).value;
      const w = $('[data-l="who"]', el).value;
      const q = $('[data-l="q"]', el).value.toLowerCase();
      body.innerHTML = S.lessons.groups.filter((x) => !g || x.group === g).map((x) =>
        x.rows.filter((r) => (!w || r.who.includes(w)) && (!q || (r.what + r.rule).toLowerCase().includes(q)))
          .map((r) => '<tr><td class="num">' + r.n + '</td><td>' + r.what + '<span class="sub">' + esc(x.group) +
            '</span></td><td>' + r.rule + '</td><td>' + r.who.map((k) => '<span class="chip">' + (who[k] || k) +
              '</span>').join(' ') + '</td></tr>').join('')).join('');
    };
    $$('[data-l]', el).forEach((x) => x.addEventListener('input', draw));
    draw();
  };

  R.parked = (el) => {
    el.innerHTML = '<div class="table-wrap"><table><thead><tr><th>Parked on</th><th>Idea</th></tr></thead><tbody>' +
      S.parked.map((p) => '<tr><td class="mono">' + esc(p.date) + '</td><td>' + p.text + '</td></tr>').join('') +
      '</tbody></table></div>';
  };

  R.openProblems = (el) => {
    el.innerHTML = S.open.sections.map((s) => '<div class="block prose"><h2>' + esc(s.title) + '</h2>' + s.html +
      '</div>').join('');
  };

  R.unitTests = (el) => {
    el.innerHTML = S.tests.unit.map((f) => '<details><summary>' + esc(f.file) + ', ' +
      sum(f.classes.map((c) => c.tests.length)) + ' tests</summary><div><p class="note">' + esc(f.doc) + '</p>' +
      f.classes.map((c) => '<h4>' + esc(c.name) + '</h4>' + (c.doc ? '<p class="note">' + esc(c.doc) + '</p>' : '') +
        '<ul>' + c.tests.map((t) => '<li>' + esc(t) + '</li>').join('') + '</ul>').join('') + '</div></details>').join('');
  };

  R.modTests = (el) => {
    el.innerHTML = '<details><summary>' + S.tests.mod.length + ' tests of the workbench mod</summary><div><ul>' +
      S.tests.mod.map((t) => '<li>' + esc(t) + '</li>').join('') + '</ul></div></details>';
  };

  R.weeks = (el) => {
    const counts = (S.built && S.built.commits_by_week) || {};
    el.innerHTML = '<div class="timeline">' + S.weeks.sections.map((w) => {
      const n = w.monday ? counts[w.monday] || 0 : null;
      const empty = /No commits, notes or updates/.test(w.html);
      return '<div class="week' + (empty ? ' empty' : '') + '"><div class="head"><h3>' + esc(w.title) + '</h3>' +
        (n == null ? '' : '<span class="chip' + (n ? ' info' : '') + '">' + n + ' commit' + (n === 1 ? '' : 's') +
          '</span>') + '</div><div class="body">' + w.html + '</div></div>';
    }).join('') + '</div>';
  };

  R.planSections = (el) => {
    el.innerHTML = S.plan.sections.filter((s) => s.title !== 'Budget').map((s) => '<div class="block prose"><h2>' +
      esc(s.title) + '</h2>' + s.html + '</div>').join('');
  };

  R.budget = (el) => {
    const c1 = cell('1').cost;
    const c5 = cell('5').cost;
    const rows = [
      ['Week 2: the box on Thornwood', 'box only, 6 questions, 3 repeats', 18, 18 * c1, 18 * c5],
      ['Week 3: the claim run on a fresh market', '3 arms, 6 questions, 3 repeats', 54, 36 * c1 + 18 * c5, 18 * c1 + 36 * c5],
    ];
    const lo = sum(rows.map((r) => r[3]));
    const hi = sum(rows.map((r) => r[4]));
    const plan = (S.plan.sections.find((s) => s.title === 'Budget') || {}).html || '';
    el.innerHTML = '<div class="prose">' + plan + '</div><div class="table-wrap"><table><thead><tr><th>Step</th>' +
      '<th>Runs</th><th class="num">Count</th><th class="num">Low</th><th class="num">High</th></tr></thead><tbody>' +
      rows.map((r) => '<tr><td><b>' + r[0] + '</b></td><td>' + r[1] + '</td><td class="num">' + r[2] +
        '</td><td class="num">' + money(r[3], 2) + '</td><td class="num">' + money(r[4], 2) + '</td></tr>').join('') +
      '<tr><td><b>Both</b></td><td></td><td class="num">72</td><td class="num">' + money(lo, 2) + '</td><td class="num">' +
      money(hi, 2) + '</td></tr><tr><td><b>Left afterwards</b></td><td>' + esc(S.budget.source) + ': ' +
      money(S.budget.left, 2) + ' of ' + money(S.budget.of, 0) + '</td><td></td><td class="num">' +
      money(S.budget.left - lo, 2) + '</td><td class="num">' + money(S.budget.left - hi, 2) + '</td></tr></tbody></table></div>' +
      '<p class="note">Low assumes the box costs what the shipped agent costs, ' + money(c1) + ' a run. High assumes it ' +
      'costs what opening everything costs, ' + money(c5) + ' a run. Run counts are this plan\'s assumptions.</p>';
  };

  R.code = (el) => {
    const x = S.code[el.dataset.code];
    if (!x) { el.innerHTML = '<p class="note">?</p>'; return; }
    const b = S.built || {};
    let href = '';
    if (x.file.startsWith('agent/agent-core/') && b.agent_core) {
      href = 'https://github.com/openJiuwen-ai/agent-core/blob/' + b.agent_core + '/' +
        x.file.slice('agent/agent-core/'.length) + '#L' + x.start + '-L' + x.end;
    } else if (b.repo) {
      href = b.repo + '/blob/' + (b.dirty ? b.branch : b.commit) + '/' + x.file + '#L' + x.start + '-L' + x.end;
    }
    const lines = x.code.split('\n').map((line, i) => '<span class="ln">' + (x.start + i) + '</span>' +
      esc(line)).join('\n');
    el.innerHTML = '<div class="code"><div class="code-head"><span>' + (href ? '<a href="' + esc(href) +
      '" target="_blank" rel="noopener">' + esc(x.file) + '</a>' : esc(x.file)) + ', lines ' + x.start + ' to ' + x.end +
      '</span><button class="copy" type="button">Copy</button></div><pre>' + lines + '</pre></div>';
    el.querySelector('.copy').dataset.text = x.code;
  };

  // --------------------------------------------------------------------- behaviour

  function tabs(root) {
    $$('[data-tabs]', root).forEach((bar) => {
      if (bar.dataset.ready) return;
      bar.dataset.ready = '1';
      const group = bar.dataset.tabs;
      bar.addEventListener('click', (ev) => {
        const btn = ev.target.closest('[data-tab]');
        if (!btn) return;
        $$('[data-tab]', bar).forEach((b) => b.setAttribute('aria-selected', String(b === btn)));
        $$('[data-panel^="' + group + ':"]').forEach((p) =>
          p.classList.toggle('on', p.dataset.panel === group + ':' + btn.dataset.tab));
      });
    });
  }

  function renderAll() {
    $$('[data-render]').forEach((el) => {
      const fn = R[el.dataset.render];
      if (fn) fn(el); else console.warn('no renderer', el.dataset.render);
    });
    $$('[data-code]').forEach((el) => R.code(el));
  }

  function setReading(value) {
    reading = value;
    $$('[data-reading]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.reading === value)));
    ['cellBars', 'cellsTable', 'testsTable'].forEach((name) =>
      $$('[data-render="' + name + '"]').forEach((el) => R[name](el)));
  }

  function show() {
    const [page, anchor] = (location.hash.slice(1) || 'overview').split('/');
    const target = document.getElementById('p-' + page) || document.getElementById('p-overview');
    $$('.page').forEach((p) => p.classList.toggle('on', p === target));
    $$('.side a').forEach((a) => {
      if (a.getAttribute('href') === '#' + target.id.slice(2)) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    $('#where').textContent = target.dataset.title || '';
    document.title = (target.id === 'p-overview' ? '' : (target.dataset.title + ' · ')) + 'Ambiguity Without Adversary';
    $('#side').classList.remove('open');
    const spot = anchor && document.getElementById(anchor);
    if (spot) spot.scrollIntoView(); else window.scrollTo(0, 0);
  }

  const THEMES = ['system', 'light', 'dark'];
  function applyTheme(mode) {
    if (mode === 'light' || mode === 'dark') document.documentElement.dataset.theme = mode;
    else delete document.documentElement.dataset.theme;
    $('#theme').textContent = { system: 'Auto theme', light: 'Light', dark: 'Dark' }[mode];
    $('#theme').setAttribute('aria-label', 'Theme: ' + mode + '. Click to change.');
  }
  function storedTheme() {
    try { return localStorage.getItem('igr-theme') || 'system'; } catch (e) { return 'system'; }
  }

  document.addEventListener('click', (ev) => {
    const copy = ev.target.closest('.copy');
    if (copy) {
      const text = copy.dataset.text || (copy.parentElement.querySelector('pre') || {}).textContent || '';
      const done = () => { copy.textContent = 'Copied'; copy.classList.add('done');
        setTimeout(() => { copy.textContent = 'Copy'; copy.classList.remove('done'); }, 1400); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, () => { copy.textContent = 'Select and copy'; });
      } else {
        copy.textContent = 'Select and copy';
      }
      return;
    }
    const rd = ev.target.closest('[data-reading]');
    if (rd) setReading(rd.dataset.reading);
  });

  // Every command box gets a copy button.
  $$('.cmd').forEach((box) => {
    if (box.querySelector('.copy')) return;
    const b = document.createElement('button');
    b.className = 'copy';
    b.type = 'button';
    b.textContent = 'Copy';
    box.appendChild(b);
  });

  $('#theme').addEventListener('click', () => {
    const next = THEMES[(THEMES.indexOf(storedTheme()) + 1) % THEMES.length];
    try { localStorage.setItem('igr-theme', next); } catch (e) { /* the choice lasts this visit only */ }
    applyTheme(next);
  });
  $('#menu').addEventListener('click', () => {
    const side = $('#side');
    side.classList.toggle('open');
    $('#menu').setAttribute('aria-expanded', String(side.classList.contains('open')));
  });

  figures();
  renderAll();
  fill(document);
  // Renderers that build markup containing [data-cmd] boxes need copy buttons too.
  $$('.cmd').forEach((box) => {
    if (box.querySelector('.copy')) return;
    const b = document.createElement('button');
    b.className = 'copy';
    b.type = 'button';
    b.textContent = 'Copy';
    box.appendChild(b);
  });
  tabs(document);
  applyTheme(storedTheme());
  if (S.built) {
    $('#built').textContent = 'Built ' + S.built.date + ' from ' + S.built.commit + (S.built.dirty ? ' with changes' : '');
  }
  window.addEventListener('hashchange', show);
  show();
})();
