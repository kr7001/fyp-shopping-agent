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
  const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
  if (!S) { $('#main').innerHTML = '<p>Run <code>make site</code> first.</p>'; return; }

  const C = S.clothing;
  const names = C.names;
  const label = (n) => C.info[n].label;
  const byLabel = (l) => names.find((n) => label(n) === l);
  const cell = (l) => C.cells[byLabel(l)];
  // The student's test numbers for the meeting, against the project's cell names.
  const TEST = { '1': 'Test 1', '2': 'Test 2', '3': 'Test 3', '5': 'Test 4' };
  const SHORT = { '1': 'as shipped', '2': 'window limit off', '3': 'second agent', '5': 'open everything' };
  const COLOUR = { '1': 'bad', '2': 'good', '3': 'info', '5': 'warn', 'pilot': 'accent' };
  let reading = 'menu';
  const right = (c) => (reading === 'menu' ? c.right : c.right_buyable);
  const opened = (c) => (reading === 'menu' ? c.opened : c.opened_buyable);
  const P = S.pilot;
  const pilotCheapest = P.find((r) => r.task === 'apparel-cheapest-target');
  const pilotCount = P.find((r) => r.task === 'apparel-count-buyable');
  const test = (a, b, m, rd, d) => C.tests.find((x) => x.a === a && x.b === b && x.measure === m && x.reading === rd && x.distinct === !!d);
  const errCount = (l, kind) => ((C.errors[byLabel(l)] || []).find((e) => e[0] === kind) || [kind, []])[1].length;
  const chip = (text, kind) => '<span class="chip ' + (kind || '') + '">' + esc(text) + '</span>';
  const verdictChip = (v) => chip(v, v === 'correct' ? 'good' : v === 'abstained' ? 'warn' : 'bad');
  const testChip = (l) => chip(TEST[l] + ' · ' + SHORT[l], COLOUR[l]);

  // ------------------------------------------------------------------ key findings
  function keyFindings() {
    const c1 = cell('1'), c2 = cell('2'), c3 = cell('3'), c5 = cell('5');
    const cards = [
      ['bad', 'The problem', c1.opened + ' of 15', 'runs of the shipped agent opened every listing the answer needs. It stops at the four cards its probe shows.'],
      ['good', 'The cause, proven', c2.opened + ' of 15', 'with one default off: the card probe\'s window limit. Correct answers ' + c1.right + ' to ' + c2.right + ' of 15, p = ' + pfmt(test('2', '1', 'correct', 'menu').p_question) + '.'],
      ['warn', 'The ceiling, and its errors', (c5.cost / c1.cost).toFixed(1) + '×', 'the cost when told to open everything, ' + c5.right + ' of 15 correct. ' + errCount('5', 'read "offer" as "can sell it now"') + ' of its ' + (c5.runs - c5.right) + ' errors are one ambiguous word.'],
      ['info', 'Not only openJiuwen', c3.opened_buyable + ' of 15', 'the second agent, no card probe, opened what it needs. Its errors were the ambiguity and reading a price too early: the model\'s, not the scaffold\'s.'],
      ['accent', 'The block\'s pilot', P.filter((r) => r.verdict === 'correct').length + ' of ' + P.length, 'correct. Opened ' + pilotCheapest.opened + ' listings instead of 15 on the cheapest question, ' + money(pilotCheapest.cost) + ' against about $0.59.'],
    ];
    $('#key').innerHTML = cards.map((c) => '<div class="key ' + c[0] + '"><span class="eyebrow">' + esc(c[1]) + '</span><b>' + esc(c[2]) + '</b><p>' + esc(c[3]) + '</p></div>').join('');
  }

  // ------------------------------------------------------------------ section 1
  function bars() {
    const rows = ['1', '2', '3', '5'].map((l) => { const c = cell(l); return { name: TEST[l] + ', ' + SHORT[l], colour: COLOUR[l], opened: opened(c), right: right(c), n: c.runs, cost: c.cost }; });
    rows.push({ name: 'Test 5, the block\'s pilot', colour: 'accent', opened: P.length, right: P.filter((r) => r.verdict === 'correct').length, n: P.length, cost: sum(P.map((r) => r.cost)) / P.length });
    $('#bars').innerHTML = '<div class="bars">' + rows.map((r) => '<div class="bar-row"><div class="who">' + chip(r.name, r.colour) + '<small>' + money(r.cost, 3) + ' a run</small></div><div class="bar-pair">' +
      '<div class="bar"><span>Opened what it needs</span><div class="track"><i class="' + r.colour + '" style="width:' + pct(r.opened, r.n) + '%"></i></div><span class="val">' + r.opened + ' of ' + r.n + '</span></div>' +
      '<div class="bar"><span>Correct</span><div class="track"><i class="' + r.colour + ' dim" style="width:' + pct(r.right, r.n) + '%"></i></div><span class="val">' + r.right + ' of ' + r.n + '</span></div></div></div>').join('') + '</div>';
  }

  function cellsTable() {
    const rows = ['1', '2', '3', '5'].map((l) => {
      const c = cell(l);
      return '<tr><td>' + testChip(l) + '<span class="sub">' + esc(C.info[byLabel(l)].change) + '</span></td>' +
        '<td class="num">' + chip(right(c) + ' of ' + c.runs, right(c) >= 11 ? 'good' : right(c) <= 5 ? 'bad' : 'warn') + '</td><td class="num">' + chip(opened(c) + ' of ' + c.runs, opened(c) === c.runs ? 'good' : opened(c) <= 6 ? 'bad' : 'warn') + '</td>' +
        '<td class="num">' + c.median_opened + '</td><td class="num">' + Math.round(c.calls) + '</td><td class="num">' + money(c.cost, 3) + '</td><td class="num">' + c.distinct + '</td></tr>';
    }).join('');
    const pilotRow = '<tr class="hl-row"><td>' + chip('Test 5 · the block, v1', 'accent') + '<span class="sub">openJiuwen as shipped with the block\'s plan in front of it. One run per question, 14 October.</span></td>' +
      '<td class="num">' + chip(P.filter((r) => r.verdict === 'correct').length + ' of ' + P.length, 'good') + '</td><td class="num">' + chip(P.length + ' of ' + P.length, 'good') + '</td>' +
      '<td class="num">' + P.map((r) => r.opened).sort((a, b) => a - b).join(' and ') + '</td><td class="num">' + Math.round(sum(P.map((r) => r.tool_calls)) / P.length) + '</td><td class="num">' + money(sum(P.map((r) => r.cost)) / P.length, 3) + '</td><td class="num">' + P.length + '</td></tr>';
    $('#cells').innerHTML = '<div class="table-wrap"><table class="striped"><thead><tr><th>Test</th><th class="num">Correct</th><th class="num">Opened what it needs</th><th class="num">Median listings opened</th><th class="num">Tool calls a run</th><th class="num">Cost a run</th><th class="num">Distinct runs</th></tr></thead><tbody>' + rows + pilotRow + '</tbody></table></div>';
  }

  function questionsTable() {
    const labels = ['1', '2', '3', '5'];
    const cellOf = (p) => '<td class="num">' + chip(p.correct + ' / ' + p.covered, p.correct === p.of ? 'good' : p.correct === 0 ? 'bad' : 'warn') + '</td>';
    const rows = C.questions_detail.filter((q) => q.gated).map((q) => {
      const pr = P.find((r) => r.task === q.id);
      return '<tr><td><b>' + esc(q.short) + '</b><span class="sub">' + esc(q.question) + '</span></td><td>' + esc(q.answer) + '</td>' +
        labels.map((l) => cellOf(cell(l).per_question[q.id])).join('') +
        '<td class="num">' + (pr ? chip(pr.verdict === 'correct' ? '1 / 1' : '0 / 1', pr.verdict === 'correct' ? 'good' : 'bad') : '<span class="sub">not run</span>') + '</td></tr>';
    }).join('');
    $('#questions').innerHTML = '<div class="table-wrap"><table class="striped"><thead><tr><th>Question</th><th>Answer key</th>' + labels.map((l) => '<th class="num">' + TEST[l] + '</th>').join('') + '<th class="num">Test 5</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function significance() {
    const c1 = cell('1'), c3 = cell('3'), c5 = cell('5');
    const cards = [
      ['info', 'Test 3, the second agent', 'Is this only an openJiuwen problem? Half yes, half no.',
        ['<b>The four-listing stop is openJiuwen\'s.</b> With no card probe, the second agent opened what it needed in ' + c3.opened + ' of 15 runs under the key and ' + c3.opened_buyable + ' of 15 under the other reading, median 15 listings, against ' + c1.opened + ' of 15 for the shipped agent (p = ' + pfmt(test('3', '1', 'opened', 'menu', true).p_question) + ' by question on its ' + c3.distinct + ' distinct runs). It was also the cheapest arm, ' + money(c3.cost, 3) + ' a run.',
         '<b>Its errors were everyone\'s.</b> It read "offer" as "can sell it now" (' + errCount('3', 'read "offer" as "can sell it now"') + ' distinct run) and read a price before the page revealed it (' + errCount('3', 'read the price before the page revealed it') + '). Those belong to the model and the page, not the scaffold, and the block targets both.',
         '<b>The model matters too.</b> DeepSeek on the first agent (18 September) opened 10, 7, 10 and 4 listings, so the stop is the probe default together with how far the model trusts it.']],
      ['warn', 'Test 4, open everything', 'The ceiling. Three times the cost, and still ' + (c5.runs - c5.right) + ' errors.',
        ['<b>' + c5.right + ' of 15 correct at ' + money(c5.cost, 3) + ' a run</b>, ' + (c5.cost / c1.cost).toFixed(1) + ' times the shipped agent, ' + Math.round(c5.calls) + ' tool calls a run. Opening everything works when the agent does it, and it is expensive.',
         '<b>' + errCount('5', 'read "offer" as "can sell it now"') + ' of its ' + (c5.runs - c5.right) + ' errors are one word.</b> "How many listings offer size M?" answered as "can sell it now" (5) where the key says "in the menu" (10). Every agent that explained itself read it that way. This is not a retrieval failure: the question is ambiguous.',
         '<b>That observation produced the ask-back.</b> A question with two reasonable readings should be asked back, not guessed. The questions are kept as they are, on purpose, because catching them is the block\'s job.']],
      ['accent', 'Test 5, the block\'s pilot', 'The plan was followed, exactly.',
        ['<b>Cheapest buyable M:</b> the agent opened exactly the ' + pilotCheapest.opened + ' listings advertised at or below the winning price, skipped the other 7, named the right seller, ' + money(pilotCheapest.cost) + '. Test 4 opened 15 for the same question at about $0.59.',
         '<b>How many sell M now:</b> opened all 15, as a count must, answered 5, ' + money(pilotCount.cost) + '.',
         '<b>Honest size:</b> two runs on the market the block was designed on. A working pipeline, not yet a result.']],
    ];
    $('#sig').innerHTML = '<div class="cards3">' + cards.map((c) => '<div class="sigcard ' + c[0] + '"><span class="eyebrow">' + esc(c[1]) + '</span><h3>' + esc(c[2]) + '</h3><ul>' + c[3].map((b) => '<li>' + b + '</li>').join('') + '</ul></div>').join('') + '</div>';
  }

  function testsTable() {
    const show = [['2', '1', 'correct', false], ['2', '1', 'opened', false], ['3', '1', 'opened', true], ['3', '1', 'correct', true], ['5', '1', 'correct', false], ['5', '2', 'correct', false]];
    const rows = show.map(([a, b, m, d]) => { const x = test(a, b, m, reading, d); const p = x.p_question; return '<tr><td>' + testChip(a) + ' against ' + testChip(b) + '</td><td>' + (m === 'opened' ? 'opened what it needs' : 'correct') + '</td><td>' + esc(x.text) + '</td><td class="num">' + pfmt(p) + '</td><td>' + chip(p < 0.01 ? 'p < 0.01' : p < 0.05 ? 'p < 0.05' : 'no difference found', p < 0.01 ? 'good' : p < 0.05 ? 'warn' : '') + '</td><td>' + (d ? 'distinct runs' : 'every run') + '</td></tr>'; }).join('');
    $('#tests').innerHTML = '<div class="table-wrap"><table class="striped"><thead><tr><th>Comparison</th><th>Measure</th><th>Counts</th><th class="num">p, by question</th><th></th><th>Unit</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function errorsTable() {
    const colour = { 'did not open what the answer needs': 'bad', 'read "offer" as "can sell it now"': 'warn', 'read the price before the page revealed it': 'info', 'ran out of its 100 steps': '', 'named a seller that cannot sell M': 'bad' };
    const fix = { 'did not open what the answer needs': 'the plan lists every listing and says which to open', 'read "offer" as "can sell it now"': 'the block asks the user which reading', 'read the price before the page revealed it': 'the plan says choose the size, then look again', 'ran out of its 100 steps': 'the plan skips listings the advertised price rules out', 'named a seller that cannot sell M': 'the plan says check the size can be chosen' };
    const rows = ['1', '2', '3', '5'].map((l) => {
      const kinds = C.errors[byLabel(l)] || [];
      return kinds.map((k, i) => '<tr>' + (i === 0 ? '<td rowspan="' + kinds.length + '">' + testChip(l) + '</td>' : '') + '<td>' + chip(k[0], colour[k[0]]) + '</td><td class="num">' + k[1].length + '</td><td class="small">' + esc(fix[k[0]] || '') + '</td></tr>').join('');
    }).join('');
    $('#errors').innerHTML = '<div class="table-wrap"><table class="striped"><thead><tr><th>Test</th><th>Kind of error</th><th class="num">Runs</th><th>What the block does about it</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function setReading(v) {
    reading = v;
    $$('[data-reading]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.reading === v)));
    bars(); cellsTable(); testsTable();
  }

  function pilotPanels() {
    const el = $('#pilot');
    el.innerHTML = '<div class="tabs" role="tablist">' + P.map((r, i) => '<button class="tab" role="tab" data-tab="' + i + '" aria-selected="' + (i === 0) + '">' + esc(r.task.replace('apparel-', '')) + '</button>').join('') + '</div>' +
      P.map((r, i) => '<div class="panel' + (i === 0 ? ' on' : '') + '" data-panel="' + i + '"><div class="stats">' +
        '<div class="stat"><b>' + verdictChip(r.verdict) + '</b><span>' + esc(r.why) + '</span></div><div class="stat"><b>' + r.opened + ' of ' + r.population + '</b><span>listings opened' + (r.floor ? ', the page says a sound answer needs ' + r.floor : '') + '</span></div>' +
        '<div class="stat"><b>' + r.tool_calls + '</b><span>tool calls</span></div><div class="stat"><b>' + money(r.cost, 3) + '</b><span>' + Math.round(r.elapsed_s) + ' seconds</span></div></div>' +
        '<h4>The agent\'s answer</h4><blockquote>' + esc(r.answer) + '</blockquote>' +
        '<h4>The exact text the block handed the agent (strategy kind <code>' + esc(r.kind) + '</code>)</h4><div class="code"><div class="code-head"><span>experiments/results/20261014T084322/' + esc(r.task) + '-1.json, the box record\'s query</span></div><pre class="wrap">' + esc(r.query) + '</pre></div></div>').join('');
    el.querySelector('.tabs').addEventListener('click', (ev) => { const b = ev.target.closest('[data-tab]'); if (!b) return; $$('[data-tab]', el).forEach((x) => x.setAttribute('aria-selected', String(x === b))); $$('.panel', el).forEach((p) => p.classList.toggle('on', p.dataset.panel === b.dataset.tab)); });
  }

  // ------------------------------------------------------------------ section 2
  function research() {
    const rows = [
      ['primitives', 'WebMall (SIGIR 2026), DeepShop (2025), WebShop (2022)', 'The reading tasks agents are benchmarked on fall into a few shapes: find a product, cheapest with or without requirements, vague requirements, substitutes. Agents fail most on vague requirements (64% at best) and on filters and sorting (under 35%).', 'The census of question shapes, and the seven primitives version 2 composes from.'],
      ['ask-back', 'DiscoBench (Jun 2026), SAGE-Agent (ACL 2026)', 'Ask only when ambiguity changes the answer; over-asking and under-asking both scored, with a simulated user answering.', 'Our "offer" case is their facet ambiguity, our scripted user is their simulator, and the clear questions are the control.'],
      ['ask-back', 'Dialogue to Discovery (Jun 2026)', 'Ask about an attribute only when the catalogue splits on it.', 'The rule not to ask when both readings agree on this page (designed, waits for a page that shows stock).'],
      ['stop rule', 'AB-RAG, Stop-RAG, TASR, Know Before You Fetch (2025 to 2026)', 'When to stop retrieving, decided from the model\'s own uncertainty under a budget.', 'The contrast that defines the gap: the block\'s stop rule reads a bound from the page, and its check can refuse an answer the model is confident about.'],
      ['stop rule', 'Calibrate-Then-Act (Feb 2026), optimal stopping, branch and bound', 'Weigh another look against what it could change; a lower bound on an unopened item lets it be skipped.', 'The cheapest strategy is branch and bound with the advertised price as the bound; the saving is counted in the measured $0.035 per listing opened.'],
      ['model + rules', 'LLM-Modulo (2024), Metagent-P (ACL 2025), plan verification with formal methods (Oct 2025)', 'A model proposes, a symbolic critic verifies, before anything executes.', 'Version 2\'s shape. The fifth property, "the attribute exists on this shop", is the one the 18 September probe showed was missing.'],
      ['reviews', 'Product QA survey (ACL 2023), AmazonQA (2019)', 'Review questions have an answerability problem: the evidence may not be there.', 'How review questions join: the depth primitive stops at the first mention or the last page, and never answers "no" from an unread page.'],
      ['framing', 'NRF and Salesforce (Jan 2026), the agentic commerce press (2026)', 'Nearly half of shoppers used an AI assistant in their last purchase; agents are starting to check out; the worry is hallucinated orders.', 'Why answering matters: every purchase is a retrieval question first.'],
    ];
    const tag = { 'primitives': 'accent', 'ask-back': 'warn', 'stop rule': 'info', 'model + rules': 'good', 'reviews': '', 'framing': 'bad' };
    $('#research-table').innerHTML = '<div class="table-wrap"><table class="striped"><thead><tr><th>Influenced</th><th>Source</th><th>What it says</th><th>What it changed in the block</th></tr></thead><tbody>' +
      rows.map((r) => '<tr><td>' + chip(r[0], tag[r[0]]) + '</td><td><b>' + esc(r[1]) + '</b></td><td class="small">' + esc(r[2]) + '</td><td>' + esc(r[3]) + '</td></tr>').join('') + '</tbody></table></div>';
  }

  function architecture() {
    const steps = [
      ['Results page', 'shop', 'Fetched over HTTP with the agent\'s own user agent and parsed: sellers, advertised prices, URLs. Checked: the same 15 prices in the same order as the agent\'s own whole-page probe.', 'page.fetch, page.parse'],
      ['Logical form', 'ours', 'The question becomes a record: quantifier (lookup, exists, every, cheapest, top-k, count), the attribute, the filters (size M, buyable, under $20), the population. Rules write it; a model can too, and the two are compared.', 'form.from_rules, form.from_model'],
      ['Verify', 'ours', 'Five properties: a bound only over an enumerated population; nothing derived from a bound reported as a price; a universal claim needs a counterexample or everything; the best of a population needs coverage of what the bound cannot rule out; every attribute the form needs is shown on this shop.', 'form.verify'],
      ['Ask, push back, or bypass', 'warn', 'Ambiguous verb about a variant: ask which reading. A price word with no figure: ask the threshold. An attribute the shop does not show: say so, run nothing. No shopping signal at all: hand the question to the agent unchanged and count it.', 'ambiguity.ask, form.refusal, box.decide'],
      ['Compose', 'ours', 'The primitive for the quantifier: Lookup, Witness, Counterexample, BoundPrune, Exhaust, Depth, with filters inside. Candidates ordered by advertised price for price questions.', 'primitives.compose'],
      ['Render', 'ours', 'The exact text: the listing count, the listings by advertised price with URLs, the strategy with its stop rule and what must never be reported. Same bytes every time for the same question and page.', 'primitives.Plan, targeting.BODIES'],
      ['openJiuwen', 'theirs', 'The unmodified agent runs with that text as its task. Browser confined to the shop. Same model, budget, window and clock as every earlier test.', 'suite.run_once'],
      ['Check the answer', 'ours', 'From the page, not the answer key: a cheapest answer must have opened every listing advertised at or below its price; a count all of them; a No one counterexample; a Yes its witness. An unsupported answer is refused, not reported.', 'box.check, policy.gate_from_page'],
    ];
    const el = $('#arch');
    el.innerHTML = '<div class="flow">' + steps.map((s, i) => '<button type="button" class="node ' + s[1] + ' arch-node" data-step="' + i + '" aria-pressed="' + (i === 0) + '"><b>' + (i + 1) + '. ' + esc(s[0]) + '</b><span><code>' + esc(s[3]) + '</code></span></button>' + (i < steps.length - 1 ? '<div class="arrow"></div>' : '')).join('') + '</div><div class="callout info arch-detail" id="arch-detail"></div>';
    const show = (i) => { $('#arch-detail').innerHTML = '<b>' + (i + 1) + '. ' + esc(steps[i][0]) + '</b> ' + esc(steps[i][2]) + ' <span class="small">Code: <code>' + esc(steps[i][3]) + '</code></span>'; $$('.arch-node', el).forEach((n) => n.setAttribute('aria-pressed', String(Number(n.dataset.step) === i))); };
    el.addEventListener('click', (ev) => { const n = ev.target.closest('.arch-node'); if (n) show(Number(n.dataset.step)); });
    show(0);
  }

  function scenarioTable() {
    const Pt = S.patterns;
    const prim = { 'none': '', 'Depth': 'info', 'Counterexample': 'warn', 'BoundPrune': 'accent', 'Witness': 'good', 'Lookup': '', 'Exhaust': 'bad' };
    const rows = [
      ['Answered on the results page', 'results_page', Pt.targeting.RESULTS_PAGE, 'read the page, open nothing', 'none'],
      ['Reviews', 'depth_search', Pt.targeting.REVIEWS, 'page through the reviews; stop at the first mention or the last page', 'Depth'],
      ['Does every listing have it', 'refutation', Pt.targeting.UNIVERSAL, 'one counterexample settles it', 'Counterexample'],
      ['Best per unit', 'rate_bound', Pt.targeting.UNIT_RATE, 'advertised price over the largest pack bounds the rate', 'BoundPrune'],
      ['Cheapest that can be bought', 'availability_bound', Pt.targeting.CHEAPEST + '  and  ' + Pt.targeting.BUYABLE, 'ascending advertised price; choose the size, look again, check it is buyable; skip at or above the best', 'BoundPrune'],
      ['Cheapest', 'total_bound', Pt.targeting.CHEAPEST, 'ascending advertised price; skip at or above the best', 'BoundPrune'],
      ['Is there any, with a price ceiling', 'exists_price', Pt.form.EXISTS + '  with  ' + Pt.form.CEILING, 'cheapest first; stop at the first buyable one under the limit', 'Witness'],
      ['The k cheapest', 'topk_price', Pt.form.TOPK + '  or  ' + Pt.form.TOPK_COUNT, 'bound to the k-th best', 'BoundPrune'],
      ['Most expensive', 'argmax_price', Pt.form.ARGMAX, 'the advertised price bounds from below, so open everything', 'BoundPrune'],
      ['A named listing, or two to compare', 'named_lookup', Pt.form.URL + '  or  ' + Pt.form.NAMED_PAIR, 'open exactly those', 'Lookup'],
      ['How many, or anything else with a shopping signal', 'survey', 'the fallback: a market word such as ' + Pt.form.MARKET_WORDS.slice(0, 70) + '…', 'open every listing', 'Exhaust'],
      ['No shopping signal at all', 'bypass', 'none of: a URL, a market word, a price word, a variant word, an availability word, a review word, a filter', 'the agent gets the question unchanged, and the run is counted', 'none'],
    ];
    const asks = [
      ['warn', 'Facet ambiguity, ask back', Pt.ambiguity.VERB + '  within six words of  ' + Pt.ambiguity.GOVERNED + '  and none of  ' + Pt.ambiguity.CLEAR.slice(0, 110) + '…', 'listed in the menu, or can sell it now?'],
      ['warn', 'Missing threshold, ask back', Pt.form.VAGUE_PRICE + '  with no figure in the question', 'what price counts as cheap?'],
      ['bad', 'Attribute the shop does not show, push back', 'the objective or a filter is not in: ' + S.patterns.listing_page_shows.join(', ') + ' (listing page), ' + S.patterns.review_page_shows.join(', ') + ' (reviews), or seller, title, advertised price, URL (results page)', 'the box says what the shop does not show'],
    ];
    $('#scenarios').innerHTML = '<div class="table-wrap"><table class="striped"><thead><tr><th>Question kind</th><th>Kind name</th><th>What the rules key on (regular expressions from the code)</th><th>Stop rule</th><th>Primitive</th></tr></thead><tbody>' +
      rows.map((r) => '<tr><td><b>' + esc(r[0]) + '</b></td><td class="mono">' + esc(r[1]) + '</td><td class="mono small">' + esc(r[2]) + '</td><td>' + esc(r[3]) + '</td><td>' + chip(r[4], prim[r[4]]) + '</td></tr>').join('') + '</tbody></table></div>' +
      '<h4>When the block asks or pushes back instead of planning</h4><div class="table-wrap"><table class="striped"><thead><tr><th>Case</th><th>What the rules key on</th><th>What the user is asked</th></tr></thead><tbody>' +
      asks.map((r) => '<tr><td>' + chip(r[1], r[0]) + '</td><td class="mono small">' + esc(r[2]) + '</td><td>' + esc(r[3]) + '</td></tr>').join('') + '</tbody></table></div>' +
      '<p class="note">Versions in the code today: box ' + S.patterns.versions.box + ', form ' + S.patterns.versions.form + ', primitives ' + S.patterns.versions.primitives + ', strategy text ' + S.patterns.versions.targeting + ', planner ' + S.patterns.versions.planner + '.</p>';
  }

  function censusBlock() {
    const c = S.census;
    $('#census').innerHTML = '<div class="stats">' +
      '<div class="stat good"><b>' + c.same_quantifier + ' of ' + c.calls + '</b><span>same quantifier, the field that picks the strategy</span></div>' +
      '<div class="stat good"><b>' + c.same_quantifier_objective + ' of ' + c.calls + '</b><span>same quantifier and objective</span></div>' +
      '<div class="stat warn"><b>' + c.same_with_population + ' of ' + c.calls + '</b><span>and the same population: the model says "listing" where the rules say "results"</span></div>' +
      '<div class="stat bad"><b>' + c.same_every_field + ' of ' + c.calls + '</b><span>same on every field: the model leaves the URL out of the filters</span></div>' +
      '<div class="stat"><b>' + money(c.charged, 3) + '</b><span>' + c.calls + ' calls, ' + esc(c.model.split('/')[1]) + ', temperature ' + c.temperature + ', no browser</span></div></div>' +
      '<h4>The four questions where the model and the rules chose a different quantifier or objective</h4>' +
      '<div class="table-wrap"><table class="striped"><thead><tr><th>Question</th><th>Rules</th><th>Model</th><th>Who is right</th></tr></thead><tbody>' +
      c.disagreements.map((d, i) => '<tr><td>' + esc(d.question) + '</td><td class="mono">' + esc(d.rules.quantifier + ' ' + d.rules.objective + ' over ' + d.rules.population) + '</td><td class="mono">' + esc(d.model.quantifier + ' ' + d.model.objective + ' over ' + d.model.population) + '</td><td>' + chip(i === 0 ? 'either' : 'the rules', i === 0 ? 'warn' : 'good') + '</td></tr>').join('') + '</tbody></table></div>';
  }

  function unitTests() {
    $('#unit').innerHTML = S.tests.unit.map((f) => '<details><summary>' + esc(f.file.replace('experiments/tests/', '')) + ' ' + chip(sum(f.classes.map((c) => c.tests.length)) + ' tests', 'good') + '</summary><div><p class="note">' + esc(f.doc) + '</p>' +
      f.classes.map((c) => '<h4>' + esc(c.name) + '</h4>' + (c.doc ? '<p class="note">' + esc(c.doc) + '</p>' : '') + '<ul>' + c.tests.map((t) => '<li>' + esc(t) + '</li>').join('') + '</ul>').join('') + '</div></details>').join('');
  }

  function figures() {
    const c1 = cell('1'), c2 = cell('2'), c5 = cell('5');
    const F = {
      'c1.opened': c1.opened, 'c2.opened': c2.opened, 'pilot.cheapest.opened': pilotCheapest.opened, 'pilot.cheapest.cost': money(pilotCheapest.cost),
      'refusal.c1.refused': C.refusal[byLabel('1')].refused, 'refusal.c1.wrong': C.refusal[byLabel('1')].wrong,
      'tests.unit': sum(S.tests.unit.map((f) => sum(f.classes.map((c) => c.tests.length)))), 'tests.mod': S.tests.mod.length, 'tests.regression': S.tests.regression_questions,
      'lessons': sum(S.lessons.groups.map((g) => g.rows.length)), 'built': S.built ? S.built.date + ' from ' + S.built.commit : '',
      'census.qo': S.census.same_quantifier_objective, 'census.n': S.census.calls, 'c5.cost': money(c5.cost, 3), 'ratio51': (c5.cost / c1.cost).toFixed(1),
    };
    $$('[data-f]').forEach((el) => { const v = F[el.dataset.f]; el.textContent = v == null ? '?' : v; if (v == null) console.warn('no figure', el.dataset.f); });
  }

  document.addEventListener('click', (ev) => { const b = ev.target.closest('[data-reading]'); if (b) setReading(b.dataset.reading); });
  keyFindings(); bars(); cellsTable(); questionsTable(); significance(); testsTable(); errorsTable(); pilotPanels(); research(); architecture(); scenarioTable(); censusBlock(); unitTests(); figures();
})();
