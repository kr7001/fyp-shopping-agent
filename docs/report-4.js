/* Progress report 4. Every figure comes from site-data.js, built from the run files by
   docs/build_site.py; nothing numeric is typed here. */
(function () {
  'use strict';
  const S = window.SITE;
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (x) => String(x == null ? '' : x).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const money = (x, d) => (x == null ? '' : '$' + Number(x).toFixed(d == null ? 2 : d));
  const pfmt = (p) => Number(p).toFixed(5).replace(/0+$/, '').replace(/\.$/, '');
  const sum = (xs) => xs.reduce((a, b) => a + b, 0);
  if (!S) { $('#main').innerHTML = '<p>Run <code>make site</code> first.</p>'; return; }

  const C = S.clothing;
  const names = C.names;
  const label = (n) => C.info[n].label;
  const byLabel = (l) => names.find((n) => label(n) === l);
  // The student's test numbers, as used in the meeting, against the project's cell names.
  const TEST = { '1': 'Test 1', '2': 'Test 2', '3': 'Test 3', '5': 'Test 4' };
  let reading = 'menu';
  const right = (c) => (reading === 'menu' ? c.right : c.right_buyable);
  const opened = (c) => (reading === 'menu' ? c.opened : c.opened_buyable);

  function cellsTable() {
    const rows = ['1', '2', '3', '5'].map((l) => {
      const c = C.cells[byLabel(l)];
      return '<tr><td><b>' + TEST[l] + '</b><span class="sub">' + esc(C.info[byLabel(l)].title) + '. ' + esc(C.info[byLabel(l)].change) + '</span></td>' +
        '<td class="num">' + right(c) + ' of ' + c.runs + '</td><td class="num">' + opened(c) + ' of ' + c.runs + '</td>' +
        '<td class="num">' + c.median_opened + '</td><td class="num">' + Math.round(c.calls) + '</td><td class="num">' + money(c.cost, 3) + '</td>' +
        '<td class="num">' + c.distinct + '</td></tr>';
    }).join('');
    const p = S.pilot;
    const pilotRow = '<tr><td><b>Test 5</b><span class="sub">The box, version 1: the plan handed to openJiuwen as shipped. Two runs, one per question, 14 October.</span></td>' +
      '<td class="num">' + p.filter((r) => r.verdict === 'correct').length + ' of ' + p.length + '</td><td class="num">' + p.length + ' of ' + p.length + '</td>' +
      '<td class="num">' + p.map((r) => r.opened).sort((a, b) => a - b).join(', ') + '</td><td class="num">' + Math.round(sum(p.map((r) => r.tool_calls)) / p.length) + '</td>' +
      '<td class="num">' + money(sum(p.map((r) => r.cost)) / p.length, 3) + '</td><td class="num">' + p.length + '</td></tr>';
    $('#cells').innerHTML = '<div class="table-wrap"><table><thead><tr><th>Test</th><th class="num">Correct</th><th class="num">Opened what it needs</th>' +
      '<th class="num">Median listings opened</th><th class="num">Tool calls a run</th><th class="num">Cost a run</th><th class="num">Distinct runs</th></tr></thead><tbody>' +
      rows + pilotRow + '</tbody></table></div>';
  }

  function questionsTable() {
    const labels = ['1', '2', '3', '5'];
    const rows = C.questions_detail.filter((q) => q.gated).map((q) => '<tr><td><b>' + esc(q.short) + '</b><span class="sub">' + esc(q.question) + '</span></td>' +
      '<td>' + esc(q.answer) + '</td>' + labels.map((l) => { const p = C.cells[byLabel(l)].per_question[q.id]; return '<td class="num">' + p.correct + ' / ' + p.covered + '</td>'; }).join('') +
      '<td class="num">' + (S.pilot.find((r) => r.task === q.id) ? (S.pilot.find((r) => r.task === q.id).verdict === 'correct' ? '1 / 1' : '0 / 1') : '<span class="sub">not run</span>') + '</td></tr>').join('');
    $('#questions').innerHTML = '<div class="table-wrap"><table><thead><tr><th>Question</th><th>Answer key</th>' + labels.map((l) => '<th class="num">' + TEST[l] + '</th>').join('') +
      '<th class="num">Test 5</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function errorsTable() {
    const rows = ['1', '2', '3', '5'].map((l) => {
      const kinds = C.errors[byLabel(l)] || [];
      return kinds.map((k, i) => '<tr>' + (i === 0 ? '<td rowspan="' + kinds.length + '"><b>' + TEST[l] + '</b></td>' : '') + '<td>' + esc(k[0]) + '</td><td class="num">' + k[1].length + '</td><td class="mono">' + esc(k[1].join(', ')) + '</td></tr>').join('');
    }).join('');
    $('#errors').innerHTML = '<div class="table-wrap"><table><thead><tr><th>Test</th><th>Kind of error</th><th class="num">Runs</th><th>Which</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function testsTable() {
    const t = (a, b, m, rd, d) => C.tests.find((x) => x.a === a && x.b === b && x.measure === m && x.reading === rd && x.distinct === !!d);
    const show = [['2', '1', 'correct', false], ['2', '1', 'opened', false], ['3', '1', 'opened', true], ['3', '1', 'correct', true], ['5', '1', 'correct', false], ['5', '2', 'correct', false]];
    const rows = show.map(([a, b, m, d]) => { const x = t(a, b, m, reading, d); return '<tr><td>' + TEST[a] + ' against ' + TEST[b] + '</td><td>' + (m === 'opened' ? 'opened what it needs' : 'correct') + '</td><td>' + esc(x.text) + '</td><td class="num">' + pfmt(x.p_question) + '</td><td>' + (d ? 'distinct runs' : 'every run') + '</td></tr>'; }).join('');
    $('#tests').innerHTML = '<div class="table-wrap"><table><thead><tr><th>Comparison</th><th>Measure</th><th>Counts</th><th class="num">p, by question</th><th>Unit</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function setReading(v) {
    reading = v;
    $$('[data-reading]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.reading === v)));
    cellsTable(); testsTable();
  }

  function pilotPanels() {
    const el = $('#pilot');
    el.innerHTML = '<div class="tabs" role="tablist">' + S.pilot.map((r, i) => '<button class="tab" role="tab" data-tab="' + i + '" aria-selected="' + (i === 0) + '">' + esc(r.task.replace('apparel-', '')) + '</button>').join('') + '</div>' +
      S.pilot.map((r, i) => '<div class="panel' + (i === 0 ? ' on' : '') + '" data-panel="' + i + '">' +
        '<dl class="kv"><dt>Verdict</dt><dd>' + esc(r.verdict) + ' (' + esc(r.why) + ')</dd><dt>Listings opened</dt><dd>' + r.opened + ' of ' + r.population + (r.floor ? ', floor from the page ' + r.floor : '') + '</dd>' +
        '<dt>Tool calls</dt><dd>' + r.tool_calls + '</dd><dt>Cost</dt><dd>' + money(r.cost, 3) + '</dd><dt>Time</dt><dd>' + Math.round(r.elapsed_s) + ' s</dd><dt>Strategy kind</dt><dd><code>' + esc(r.kind) + '</code></dd></dl>' +
        '<h4>The agent\'s answer</h4><blockquote>' + esc(r.answer) + '</blockquote>' +
        '<h4>The exact text the box handed the agent</h4><div class="code"><div class="code-head"><span>experiments/results/' + esc(S.pilot === undefined ? '' : '20261014T084322') + '/' + esc(r.task) + '-1.json, the box record\'s query</span></div><pre class="wrap">' + esc(r.query) + '</pre></div></div>').join('');
    el.querySelector('.tabs').addEventListener('click', (ev) => {
      const b = ev.target.closest('[data-tab]'); if (!b) return;
      $$('[data-tab]', el).forEach((x) => x.setAttribute('aria-selected', String(x === b)));
      $$('.panel', el).forEach((p) => p.classList.toggle('on', p.dataset.panel === b.dataset.tab));
    });
  }

  function censusBlock() {
    const c = S.census;
    const fails = Object.entries(c.model_failures).map(([k, v]) => esc(k) + ' (' + v + ')').join(', ');
    $('#census').innerHTML = '<div class="stats">' +
      '<div class="stat"><b>' + c.same_quantifier + ' of ' + c.calls + '</b><span>same quantifier, the field that picks the strategy</span></div>' +
      '<div class="stat"><b>' + c.same_quantifier_objective + ' of ' + c.calls + '</b><span>same quantifier and objective</span></div>' +
      '<div class="stat"><b>' + c.same_with_population + ' of ' + c.calls + '</b><span>and the same population</span></div>' +
      '<div class="stat"><b>' + c.same_every_field + ' of ' + c.calls + '</b><span>same on every field</span></div>' +
      '<div class="stat"><b>' + money(c.charged, 3) + '</b><span>charged for ' + c.calls + ' calls, ' + esc(c.model) + ', temperature ' + c.temperature + '</span></div></div>' +
      '<p class="note">Model forms failing the soundness check: ' + fails + '. The four questions where the model and the rules chose a different quantifier or objective:</p>' +
      '<div class="table-wrap"><table><thead><tr><th>Question</th><th>Rules</th><th>Model</th></tr></thead><tbody>' +
      c.disagreements.map((d) => '<tr><td>' + esc(d.question) + '</td><td class="mono">' + esc(d.rules.quantifier + ' ' + d.rules.objective + ' over ' + d.rules.population) + '</td><td class="mono">' + esc(d.model.quantifier + ' ' + d.model.objective + ' over ' + d.model.population) + '</td></tr>').join('') + '</tbody></table></div>';
  }

  function scenarioTable() {
    const P = S.patterns;
    const rows = [
      ['Answered on the results page', 'results_page', P.targeting.RESULTS_PAGE, 'read the page, open nothing', 'none'],
      ['Reviews', 'depth_search', P.targeting.REVIEWS, 'page through the reviews', 'Depth'],
      ['Does every listing have it', 'refutation', P.targeting.UNIVERSAL, 'one counterexample settles it', 'Counterexample'],
      ['Best per unit', 'rate_bound', P.targeting.UNIT_RATE, 'advertised price over the largest pack bounds the rate', 'BoundPrune'],
      ['Cheapest that can be bought', 'availability_bound', P.targeting.CHEAPEST + '  and  ' + P.targeting.BUYABLE, 'ascending advertised price, choose the size, look again, check it is buyable, skip at or above the best', 'BoundPrune'],
      ['Cheapest', 'total_bound', P.targeting.CHEAPEST, 'ascending advertised price, skip at or above the best', 'BoundPrune'],
      ['Is there any (with a price ceiling)', 'exists_price', P.form.EXISTS + '  with  ' + P.form.CEILING, 'cheapest first, stop at the first buyable one under the limit', 'Witness'],
      ['The k cheapest', 'topk_price', P.form.TOPK + '  or  ' + P.form.TOPK_COUNT, 'bound to the k-th best', 'BoundPrune'],
      ['Most expensive', 'argmax_price', P.form.ARGMAX, 'the advertised price bounds from below, so open everything', 'BoundPrune'],
      ['A named listing, or two to compare', 'named_lookup', P.form.URL + '  or  ' + P.form.NAMED_PAIR, 'open exactly those', 'Lookup'],
      ['How many, or anything else with a shopping signal', 'survey', 'fallback, with ' + P.form.MARKET_WORDS.slice(0, 80) + '…', 'open every listing', 'Exhaust'],
      ['No shopping signal at all', 'bypass', 'none of: a URL, a market word, a price word, a variant word, an availability word, a review word, a filter', 'the agent gets the question unchanged, counted', 'none'],
    ];
    const asks = [
      ['Facet ambiguity, ask back', P.ambiguity.VERB + '  within six words of  ' + P.ambiguity.GOVERNED + '  and none of  ' + P.ambiguity.CLEAR.slice(0, 120) + '…', 'listed in the menu, or can sell it now'],
      ['Missing threshold, ask back', P.form.VAGUE_PRICE + '  with no figure in the question', 'what price counts as cheap'],
      ['Attribute the shop does not show, push back', 'objective or filter not in: ' + S.patterns.listing_page_shows.join(', ') + ' (listing page) or ' + S.patterns.review_page_shows.join(', ') + ' (reviews) or the results page\'s seller, title, advertised price, URL', 'says what the shop does not show'],
    ];
    $('#scenarios').innerHTML = '<div class="table-wrap"><table><thead><tr><th>Question kind</th><th>Kind name</th><th>What the rules key on (regular expressions from the code)</th><th>Stop rule</th><th>Primitive</th></tr></thead><tbody>' +
      rows.map((r) => '<tr><td><b>' + esc(r[0]) + '</b></td><td class="mono">' + esc(r[1]) + '</td><td class="mono small">' + esc(r[2]) + '</td><td>' + esc(r[3]) + '</td><td class="mono">' + esc(r[4]) + '</td></tr>').join('') + '</tbody></table></div>' +
      '<h4>When the box asks or pushes back instead of planning</h4><div class="table-wrap"><table><thead><tr><th>Case</th><th>What the rules key on</th><th>What the user is asked</th></tr></thead><tbody>' +
      asks.map((r) => '<tr><td><b>' + esc(r[0]) + '</b></td><td class="mono small">' + esc(r[1]) + '</td><td>' + esc(r[2]) + '</td></tr>').join('') + '</tbody></table></div>' +
      '<p class="note">Versions in the code today: box ' + S.patterns.versions.box + ', form ' + S.patterns.versions.form + ', primitives ' + S.patterns.versions.primitives + ', strategy text ' + S.patterns.versions.targeting + ', planner ' + S.patterns.versions.planner + '.</p>';
  }

  function unitTests() {
    $('#unit').innerHTML = S.tests.unit.map((f) => '<details><summary>' + esc(f.file.replace('experiments/tests/', '')) + ', ' + sum(f.classes.map((c) => c.tests.length)) + ' tests</summary><div><p class="note">' + esc(f.doc) + '</p>' +
      f.classes.map((c) => '<h4>' + esc(c.name) + '</h4>' + (c.doc ? '<p class="note">' + esc(c.doc) + '</p>' : '') + '<ul>' + c.tests.map((t) => '<li>' + esc(t) + '</li>').join('') + '</ul>').join('') + '</div></details>').join('');
  }

  function architecture() {
    const steps = [
      ['Results page', 'The box fetches the first results page over HTTP with the same user agent the agent\'s browser uses, and parses the sellers, advertised prices and URLs. Checked: the same 15 prices in the same order as the agent\'s own whole-page probe.', 'page.fetch, page.parse'],
      ['Logical form', 'The question becomes a record: quantifier (lookup, exists, every, cheapest, top-k, count), the attribute compared, the filters (size M, buyable, under $20), the population. Rules write it; a model can too, and the two are compared.', 'form.from_rules, form.from_model'],
      ['Verify', 'Five properties. A bound only over an enumerated population. Nothing derived from a bound reported as a price. A universal claim needs a counterexample or everything. The best of a population needs coverage of what the bound cannot rule out. Every attribute the form needs is shown on this shop.', 'form.verify'],
      ['Ask, push back, or bypass', 'Ambiguous verb about a variant: ask which reading. A price word with no figure: ask the threshold. An attribute the shop does not show: say so, run nothing. No shopping signal at all: hand the question to the agent unchanged and count it.', 'ambiguity.ask, form.refusal, box.decide'],
      ['Compose', 'The primitive for the quantifier: Lookup, Witness, Counterexample, BoundPrune, Exhaust, Depth, with filters inside. Candidates ordered by advertised price for price questions.', 'primitives.compose'],
      ['Render', 'The exact text: the listing count, the listings by advertised price with URLs, then the strategy with its stop rule and what must never be reported. Same bytes every time for the same question and page.', 'primitives.Plan, targeting.BODIES'],
      ['openJiuwen', 'The unmodified agent runs with that text as its task. Browser confined to the shop. Same model, budget, window and clock as every earlier test.', 'suite.run_once'],
      ['Check the answer', 'From the page, not the answer key: a cheapest answer must have opened every listing advertised at or below its price; a count all of them; a No one counterexample; a Yes its witness. An unsupported answer is refused, not reported.', 'box.check, policy.gate_from_page'],
    ];
    const el = $('#arch');
    el.innerHTML = '<div class="flow">' + steps.map((s, i) => '<button type="button" class="node ours arch-node" data-step="' + i + '" aria-pressed="' + (i === 0) + '"><b>' + (i + 1) + '. ' + esc(s[0]) + '</b><span><code>' + esc(s[2]) + '</code></span></button>' + (i < steps.length - 1 ? '<div class="arrow"></div>' : '')).join('') + '</div>' +
      '<div class="block arch-detail" id="arch-detail"></div>';
    const show = (i) => { $('#arch-detail').innerHTML = '<h3>' + (i + 1) + '. ' + esc(steps[i][0]) + '</h3><p>' + esc(steps[i][1]) + '</p><p class="note">Code: <code>' + esc(steps[i][2]) + '</code>. Click any step above.</p>'; $$('.arch-node', el).forEach((n) => n.setAttribute('aria-pressed', String(Number(n.dataset.step) === i))); };
    el.addEventListener('click', (ev) => { const n = ev.target.closest('.arch-node'); if (n) show(Number(n.dataset.step)); });
    show(0);
  }

  function figures() {
    const c1 = C.cells[byLabel('1')], c2 = C.cells[byLabel('2')], c3 = C.cells[byLabel('3')], c5 = C.cells[byLabel('5')];
    const F = {
      'c1.opened': c1.opened, 'c2.opened': c2.opened, 'c3.opened': c3.opened, 'c3.opened_b': c3.opened_buyable, 'c5.opened': c5.opened,
      'c1.right': c1.right, 'c2.right': c2.right, 'c3.right': c3.right, 'c3.right_b': c3.right_buyable, 'c5.right': c5.right, 'c5.right_b': c5.right_buyable,
      'c3.distinct': c3.distinct, 'c1.cost': money(c1.cost, 3), 'c3.cost': money(c3.cost, 3), 'c5.cost': money(c5.cost, 3), 'c3.calls': Math.round(c3.calls), 'c5.calls': Math.round(c5.calls),
      'ratio51': (c5.cost / c1.cost).toFixed(1),
      'p.opened.2v1': pfmt(C.tests.find((t) => t.a === '2' && t.b === '1' && t.measure === 'opened' && t.reading === 'menu' && !t.distinct).p_question),
      'p.correct.2v1': pfmt(C.tests.find((t) => t.a === '2' && t.b === '1' && t.measure === 'correct' && t.reading === 'menu' && !t.distinct).p_question),
      'p.opened.3v1': pfmt(C.tests.find((t) => t.a === '3' && t.b === '1' && t.measure === 'opened' && t.reading === 'menu' && t.distinct).p_question),
      'p.correct.5v2': pfmt(C.tests.find((t) => t.a === '5' && t.b === '2' && t.measure === 'correct' && t.reading === 'menu' && !t.distinct).p_question),
      'c5.errors.offer': (C.errors[byLabel('5')].find((e) => e[0] === 'read "offer" as "can sell it now"') || [0, []])[1].length,
      'c5.errors.total': c5.runs - c5.right,
      'c3.err.offer': (C.errors[byLabel('3')].find((e) => e[0] === 'read "offer" as "can sell it now"') || [0, []])[1].length,
      'c3.err.reveal': (C.errors[byLabel('3')].find((e) => e[0] === 'read the price before the page revealed it') || [0, []])[1].length,
      'pilot.cost': money(sum(S.pilot.map((r) => r.cost)), 2),
      'pilot.cheapest.cost': money(S.pilot.find((r) => r.task === 'apparel-cheapest-target').cost, 2),
      'pilot.cheapest.opened': S.pilot.find((r) => r.task === 'apparel-cheapest-target').opened,
      'pilot.count.cost': money(S.pilot.find((r) => r.task === 'apparel-count-buyable').cost, 2),
      'census.q': S.census.same_quantifier, 'census.qo': S.census.same_quantifier_objective, 'census.all': S.census.same_every_field, 'census.n': S.census.calls, 'census.cost': money(S.census.charged, 3),
      'refusal.c1.refused': C.refusal[byLabel('1')].refused, 'refusal.c1.wrong': C.refusal[byLabel('1')].wrong,
      'tests.unit': sum(S.tests.unit.map((f) => sum(f.classes.map((c) => c.tests.length)))), 'tests.mod': S.tests.mod.length, 'tests.regression': S.tests.regression_questions,
      'lessons': sum(S.lessons.groups.map((g) => g.rows.length)), 'built': S.built ? S.built.date + ' from ' + S.built.commit : '',
      'w.cal.s': (() => { const w = S.water.find((r) => r.market === 'Calderwood' && r.arm_name === 'targeting+gate v3'); return w.correct + ' of ' + w.runs + ' correct, ' + w.refused + ' refused'; })(),
    };
    $$('[data-f]').forEach((el) => { const v = F[el.dataset.f]; el.textContent = v == null ? '?' : v; if (v == null) console.warn('no figure', el.dataset.f); });
  }

  document.addEventListener('click', (ev) => { const b = ev.target.closest('[data-reading]'); if (b) setReading(b.dataset.reading); });
  cellsTable(); questionsTable(); errorsTable(); testsTable(); pilotPanels(); censusBlock(); scenarioTable(); unitTests(); architecture(); figures();
})();
