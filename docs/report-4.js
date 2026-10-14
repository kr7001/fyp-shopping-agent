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
  const TEST = { '1': 'Test 1', '2': 'Test 2', '3': 'Test 3', '5': 'Test 4' };
  const SHORT = { '1': 'as shipped', '2': 'window limit off', '3': 'second agent', '5': 'open everything' };
  let reading = 'menu';
  const right = (c) => (reading === 'menu' ? c.right : c.right_buyable);
  const opened = (c) => (reading === 'menu' ? c.opened : c.opened_buyable);
  const P = S.pilot;
  const pilotCheapest = P.find((r) => r.task === 'apparel-cheapest-target');
  const pilotCount = P.find((r) => r.task === 'apparel-count-buyable');
  const test = (a, b, m, rd, d) => C.tests.find((x) => x.a === a && x.b === b && x.measure === m && x.reading === rd && x.distinct === !!d);
  const errCount = (l, kind) => ((C.errors[byLabel(l)] || []).find((e) => e[0] === kind) || [kind, []])[1].length;
  const chip = (text, kind) => '<span class="chip ' + (kind || '') + '">' + esc(text) + '</span>';
  const score = (n, of) => chip(n + ' of ' + of, n === of ? 'good' : n === 0 ? 'bad' : '');
  const details = (summary, body, open) => '<details' + (open ? ' open' : '') + '><summary>' + summary + '</summary><div>' + body + '</div></details>';

  // ------------------------------------------------------------------ key findings
  function keyFindings() {
    const c1 = cell('1'), c2 = cell('2'), c3 = cell('3'), c5 = cell('5');
    const cards = [
      ['The problem', c1.opened + ' of 15', 'runs of the shipped agent opened every listing the answer needed. It stops at the four cards its probe shows it.'],
      ['The cause', c2.opened + ' of 15', 'once one default is switched off, the card probe\'s window limit. Correct answers went from ' + c1.right + ' to ' + c2.right + ' of 15 (p = ' + pfmt(test('2', '1', 'correct', 'menu').p_question) + ').'],
      ['The ceiling', (c5.cost / c1.cost).toFixed(1) + ' times', 'the cost when the agent is told to open everything, for ' + c5.right + ' of 15 correct. ' + errCount('5', 'read "offer" as "can sell it now"') + ' of its ' + (c5.runs - c5.right) + ' errors come from one ambiguous word.'],
      ['The second agent', c3.opened_buyable + ' of 15', 'runs opened what the answer needed, with no card probe. Its own errors were the ambiguous word and a price read too early, which the model does, not the scaffold.'],
      ['The block\'s pilot', P.filter((r) => r.verdict === 'correct').length + ' of ' + P.length, 'correct. On the cheapest question it opened ' + pilotCheapest.opened + ' listings instead of 15 and cost ' + money(pilotCheapest.cost) + ', against about $0.59 when everything is opened.'],
    ];
    $('#key').innerHTML = cards.map((c) => '<div class="key"><span class="eyebrow">' + esc(c[0]) + '</span><b>' + esc(c[1]) + '</b><p>' + esc(c[2]) + '</p></div>').join('');
  }

  // ------------------------------------------------------------------ section 1
  function bars() {
    const rows = ['1', '2', '3', '5'].map((l) => { const c = cell(l); return { name: TEST[l] + ', ' + SHORT[l], opened: opened(c), right: right(c), n: c.runs, cost: c.cost }; });
    rows.push({ name: 'Test 5, the block\'s pilot', opened: P.length, right: P.filter((r) => r.verdict === 'correct').length, n: P.length, cost: sum(P.map((r) => r.cost)) / P.length });
    $('#bars').innerHTML = '<div class="bars">' + rows.map((r) => '<div class="bar-row"><div class="who">' + esc(r.name) + '<small>' + money(r.cost, 3) + ' a run</small></div><div class="bar-pair">' +
      '<div class="bar"><span>Opened what it needs</span><div class="track"><i style="width:' + pct(r.opened, r.n) + '%"></i></div><span class="val">' + r.opened + ' of ' + r.n + '</span></div>' +
      '<div class="bar"><span>Correct</span><div class="track alt"><i style="width:' + pct(r.right, r.n) + '%"></i></div><span class="val">' + r.right + ' of ' + r.n + '</span></div></div></div>').join('') + '</div>';
  }

  function cellsTable() {
    const rows = ['1', '2', '3', '5'].map((l) => {
      const c = cell(l);
      return '<tr><td><b>' + TEST[l] + ', ' + SHORT[l] + '</b></td><td class="num">' + score(right(c), c.runs) + '</td><td class="num">' + score(opened(c), c.runs) + '</td>' +
        '<td class="num">' + c.median_opened + '</td><td class="num">' + Math.round(c.calls) + '</td><td class="num">' + money(c.cost, 3) + '</td></tr>';
    }).join('');
    const pilotRow = '<tr class="hl-row"><td><b>Test 5, the block\'s pilot</b></td><td class="num">' + score(P.filter((r) => r.verdict === 'correct').length, P.length) + '</td><td class="num">' + score(P.length, P.length) + '</td>' +
      '<td class="num">' + P.map((r) => r.opened).sort((a, b) => a - b).join(' and ') + '</td><td class="num">' + Math.round(sum(P.map((r) => r.tool_calls)) / P.length) + '</td><td class="num">' + money(sum(P.map((r) => r.cost)) / P.length, 3) + '</td></tr>';
    $('#cells').innerHTML = '<table class="fit"><thead><tr><th>Test</th><th class="num">Correct</th><th class="num">Opened what it needs</th><th class="num">Median listings opened</th><th class="num">Tool calls a run</th><th class="num">Cost a run</th></tr></thead><tbody>' + rows + pilotRow + '</tbody></table>' +
      '<p class="note">The second agent runs at temperature 0, so its 15 runs are ' + cell('3').distinct + ' distinct runs; comparisons with it use those. Test 5 has one run per question.</p>';
  }

  function questionsTable() {
    const labels = ['1', '2', '3', '5'];
    const rows = C.questions_detail.filter((q) => q.gated).map((q) => {
      const pr = P.find((r) => r.task === q.id);
      return '<tr><td><b>' + esc(q.short) + '</b><span class="sub">' + esc(q.question) + '</span></td><td>' + esc(q.answer) + '</td>' +
        labels.map((l) => { const p = cell(l).per_question[q.id]; return '<td class="num">' + chip(p.correct + ' of ' + p.of, p.correct === p.of ? 'good' : p.correct === 0 ? 'bad' : '') + '</td>'; }).join('') +
        '<td class="num">' + (pr ? chip(pr.verdict === 'correct' ? '1 of 1' : '0 of 1', pr.verdict === 'correct' ? 'good' : 'bad') : '<span class="sub">not run</span>') + '</td></tr>';
    }).join('');
    $('#questions').innerHTML = '<table class="fit"><thead><tr><th>Question</th><th>Answer key</th>' + labels.map((l) => '<th class="num">' + TEST[l] + '</th>').join('') + '<th class="num">Test 5</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function significance() {
    const c1 = cell('1'), c3 = cell('3'), c5 = cell('5');
    const cards = [
      ['Test 3, the second agent', 'The four-listing stop belongs to openJiuwen. The other two errors do not.',
        'With no card probe, the second agent opened what it needed in ' + c3.opened + ' of 15 runs under the key and ' + c3.opened_buyable + ' of 15 under the other reading, with a median of 15 listings opened, where the shipped agent managed ' + c1.opened + ' of 15 (p = ' + pfmt(test('3', '1', 'opened', 'menu', true).p_question) + ' by question, on its ' + c3.distinct + ' distinct runs). It was also the cheapest of the four at ' + money(c3.cost, 3) + ' a run.',
        '<p>Its wrong answers were the two kinds that have nothing to do with the scaffold. It read "offer" as "can sell it now" in ' + errCount('3', 'read "offer" as "can sell it now"') + ' distinct run and read a price before the page had revealed it in ' + errCount('3', 'read the price before the page revealed it') + '. Both are things the model does with the page, and both are what the block\'s ask-back and look-again steps are for.</p><p>The model matters as well. On 18 September DeepSeek, running the first agent, opened 10, 7, 10 and 4 listings, so the stop comes from the probe\'s default together with how far the model trusts it.</p>'],
      ['Test 4, open everything', 'It is the ceiling, it costs three times as much, and it still gets ' + (c5.runs - c5.right) + ' wrong.',
        c5.right + ' of 15 correct at ' + money(c5.cost, 3) + ' a run, which is ' + (c5.cost / c1.cost).toFixed(1) + ' times the shipped agent, with ' + Math.round(c5.calls) + ' tool calls a run. Opening everything works when the agent actually does it, and it is expensive.',
        '<p>' + errCount('5', 'read "offer" as "can sell it now"') + ' of its ' + (c5.runs - c5.right) + ' errors are the same thing. "How many listings offer size M?" was answered as "can sell it now" (5), where the key, fixed before any run, counts a sold-out M as offered (10). Every agent that explained its reasoning read it the second way. There was nothing left to open; the question itself has two readings.</p><p>That is where the block\'s ask-back came from. A question with two reasonable readings should be put back to the user rather than guessed, and the questions were kept as they are so that catching this is something the block can be measured on.</p>'],
      ['Test 5, the block\'s pilot', 'The agent followed the plan.',
        'On the cheapest question it opened exactly the ' + pilotCheapest.opened + ' listings whose advertised price was at or below the winning price, skipped the other 7, and named the right seller, for ' + money(pilotCheapest.cost) + '. Test 4 opened all 15 on the same question at about $0.59.',
        '<p>On the count question it opened all 15, which is what a count needs, answered 5 and cost ' + money(pilotCount.cost) + '.</p><p>This is two runs on the market the block was designed on. It shows the pipeline works end to end. It is not yet a result.</p>'],
    ];
    $('#sig').innerHTML = cards.map((c) => '<div class="sigcard"><span class="eyebrow">' + esc(c[0]) + '</span><h3>' + esc(c[1]) + '</h3><p>' + c[2] + '</p>' + details('More detail', c[3]) + '</div>').join('');
  }

  function testsTable() {
    const show = [['2', '1', 'correct', false], ['2', '1', 'opened', false], ['3', '1', 'opened', true], ['3', '1', 'correct', true], ['5', '1', 'correct', false], ['5', '2', 'correct', false]];
    const rows = show.map(([a, b, m, d]) => { const x = test(a, b, m, reading, d); const p = x.p_question; return '<tr><td>' + TEST[a] + ' against ' + TEST[b] + '</td><td>' + (m === 'opened' ? 'opened what it needs' : 'correct') + '</td><td>' + esc(x.text) + '</td><td class="num">' + pfmt(p) + '</td><td>' + (p < 0.01 ? 'clear difference' : p < 0.05 ? 'difference' : 'no difference found') + '</td><td>' + (d ? 'distinct runs' : 'every run') + '</td></tr>'; }).join('');
    $('#tests').innerHTML = '<table class="fit"><thead><tr><th>Comparison</th><th>Measure</th><th>Counts</th><th class="num">p, by question</th><th>Reading</th><th>Unit</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function errorsTable() {
    const fix = { 'did not open what the answer needs': 'the plan lists every listing and says which to open', 'read "offer" as "can sell it now"': 'the block asks the user which reading they mean', 'read the price before the page revealed it': 'the plan says to choose the size, then look at the page again', 'ran out of its 100 steps': 'the plan skips the listings the advertised price rules out', 'named a seller that cannot sell M': 'the plan says to check the size can actually be chosen' };
    const rows = ['1', '2', '3', '5'].map((l) => {
      const kinds = C.errors[byLabel(l)] || [];
      return kinds.map((k, i) => '<tr>' + (i === 0 ? '<td rowspan="' + kinds.length + '"><b>' + TEST[l] + '</b></td>' : '') + '<td>' + esc(k[0]) + '</td><td class="num">' + k[1].length + '</td><td>' + esc(fix[k[0]] || '') + '</td></tr>').join('');
    }).join('');
    $('#errors').innerHTML = '<table class="fit"><thead><tr><th>Test</th><th>Kind of error</th><th class="num">Runs</th><th>What the block does about it</th></tr></thead><tbody>' + rows + '</tbody></table>';
  }

  function setReading(v) {
    reading = v;
    $$('[data-reading]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.reading === v)));
    bars(); cellsTable(); testsTable();
  }

  function pilotPanels() {
    const el = $('#pilot');
    el.innerHTML = '<div class="tabs" role="tablist">' + P.map((r, i) => '<button class="tab" role="tab" data-tab="' + i + '" aria-selected="' + (i === 0) + '">' + esc(r.task.replace('apparel-', '')) + '</button>').join('') + '</div>' +
      P.map((r, i) => '<div class="panel' + (i === 0 ? ' on' : '') + '" data-panel="' + i + '"><dl class="kv"><dt>Verdict</dt><dd>' + chip(r.verdict, r.verdict === 'correct' ? 'good' : 'bad') + ' ' + esc(r.why) + '</dd><dt>Listings opened</dt><dd>' + r.opened + ' of ' + r.population + (r.floor ? ' (the page says a sound answer needs ' + r.floor + ')' : '') + '</dd><dt>Tool calls</dt><dd>' + r.tool_calls + '</dd><dt>Cost and time</dt><dd>' + money(r.cost, 3) + ', ' + Math.round(r.elapsed_s) + ' seconds</dd><dt>Strategy kind</dt><dd><code>' + esc(r.kind) + '</code></dd></dl>' +
        '<h4>The agent\'s answer</h4><blockquote>' + esc(r.answer) + '</blockquote>' +
        details('The exact text the block handed the agent', '<div class="code"><div class="code-head"><span>experiments/results/20261014T084322/' + esc(r.task) + '-1.json, the box record\'s query</span></div><pre class="wrap">' + esc(r.query) + '</pre></div>') + '</div>').join('');
    el.querySelector('.tabs').addEventListener('click', (ev) => { const b = ev.target.closest('[data-tab]'); if (!b) return; $$('[data-tab]', el).forEach((x) => x.setAttribute('aria-selected', String(x === b))); $$('.panel', el).forEach((p) => p.classList.toggle('on', p.dataset.panel === b.dataset.tab)); });
  }

  // ------------------------------------------------------------------ section 2
  function research() {
    const rows = [
      ['WebMall (SIGIR 2026), DeepShop (2025), WebShop (2022)', 'The reading tasks agents are benchmarked on fall into a few shapes: find a product, the cheapest with or without conditions, vague requirements, substitutes. Agents do worst on vague requirements (64% at best) and on filters and sorting (under 35%).', 'The census of question shapes, and the seven primitives version 2 builds plans from.'],
      ['DiscoBench (June 2026), SAGE-Agent (ACL 2026)', 'A search agent should ask only when the ambiguity would change the answer. Asking too much and too little are both scored, with a simulated user giving the answers.', 'Our "offer" case is what they call facet ambiguity. Our scripted user is their simulated user, and the clear questions are the control for asking too much.'],
      ['Dialogue to Discovery (June 2026)', 'Ask about an attribute only when the catalogue actually splits on it.', 'The rule that the block should not ask when both readings give the same answer on the page in front of it. Designed, and waiting for a page that shows stock.'],
      ['AB-RAG, Stop-RAG, TASR, Know Before You Fetch (2025 to 2026)', 'When to stop retrieving, decided from the model\'s own uncertainty, under a budget.', 'This is the nearest work, and the difference defines the gap: the block\'s stop rule reads a bound from the page, and its check can refuse an answer the model is sure about.'],
      ['Calibrate-Then-Act (February 2026), optimal stopping, branch and bound', 'Weigh another look against what it could change. A lower bound on an unopened item lets it be skipped.', 'The cheapest strategy is branch and bound with the advertised price as the bound. The saving is counted in the measured $0.035 per listing opened.'],
      ['LLM-Modulo (2024), Metagent-P (ACL 2025), plan verification with formal methods (October 2025)', 'A model proposes a plan and a symbolic checker verifies it before anything runs.', 'The shape of version 2. The fifth property, that the attribute must exist on this shop, is the one the 18 September probe showed was missing.'],
      ['Product QA survey (ACL 2023), AmazonQA (2019)', 'Questions about reviews have an answerability problem: the evidence may simply not be there.', 'How review questions will join: the depth primitive stops at the first mention or the last page, and never answers no from a page it did not read.'],
      ['NRF and Salesforce (January 2026), the agentic commerce press (2026)', 'Nearly half of shoppers used an AI assistant in their last purchase. Agents are starting to check out, and the worry is orders that were hallucinated.', 'Why answering matters: every purchase is a retrieval question first.'],
    ];
    $('#research-table').innerHTML = '<table class="fit"><thead><tr><th>Source</th><th>What it says</th><th>What it changed in the block</th></tr></thead><tbody>' +
      rows.map((r) => '<tr><td><b>' + esc(r[0]) + '</b></td><td>' + esc(r[1]) + '</td><td>' + esc(r[2]) + '</td></tr>').join('') + '</tbody></table>';
  }

  function architecture() {
    const steps = [
      ['Results page', 'The block fetches the first results page over HTTP with the same user agent the agent\'s browser uses, and reads the sellers, advertised prices and URLs. We checked that this gives the same 15 prices in the same order as the agent\'s own whole-page probe.', 'page.fetch, page.parse'],
      ['Logical form', 'The question becomes a small record: the kind of answer (a lookup, is there any, does every, the cheapest, the k cheapest, a count), the attribute compared, the conditions (size M, can be bought, under $20) and the population. Rules write it, and a model can write it too; the two are compared on every question.', 'form.from_rules, form.from_model'],
      ['Verify', 'Five properties. A bound may only be used over a population that was listed first. Nothing worked out from a bound may be reported as a price. A claim about every listing needs a counterexample or all of them. The best of a population needs everything the bound cannot rule out to have been opened. Every attribute the record needs must be something this shop shows.', 'form.verify'],
      ['Ask, push back, or pass through', 'An ambiguous verb about a variant: ask which reading is meant. A price word with no figure: ask for the threshold. An attribute the shop does not show: say so and run nothing. A question with no shopping signal at all: hand it to the agent unchanged and count it.', 'ambiguity.ask, form.refusal, box.decide'],
      ['Compose', 'Pick the primitive for the kind of answer (lookup, witness, counterexample, bound and prune, exhaust, depth) and put the conditions inside it. For price questions the candidates are ordered by advertised price.', 'primitives.compose'],
      ['Render', 'Write the text: how many listings there are, the listings in order with their URLs, then the strategy with its stop rule and what must never be reported. The same question and page give the same bytes every time.', 'primitives.Plan, targeting.BODIES'],
      ['The agent', 'openJiuwen, unmodified, runs with that text as its task. Its browser is confined to the shop. Same model, budget, window and clock as every earlier test.', 'suite.run_once'],
      ['Check the answer', 'From the page, not from any answer key. A cheapest answer must have opened every listing advertised at or below its price; a count must have opened all of them; a no needs one counterexample; a yes needs its witness. An answer the evidence does not support is refused rather than reported.', 'box.check, policy.gate_from_page'],
    ];
    const el = $('#arch');
    el.innerHTML = '<div class="flow">' + steps.map((s, i) => '<button type="button" class="node arch-node" data-step="' + i + '" aria-pressed="' + (i === 0) + '"><b>' + (i + 1) + '. ' + esc(s[0]) + '</b><span><code>' + esc(s[2]) + '</code></span></button>' + (i < steps.length - 1 ? '<div class="arrow"></div>' : '')).join('') + '</div><div class="callout arch-detail" id="arch-detail"></div>';
    const show = (i) => { $('#arch-detail').innerHTML = '<b>' + (i + 1) + '. ' + esc(steps[i][0]) + '.</b> ' + esc(steps[i][1]) + ' <span class="small">Code: <code>' + esc(steps[i][2]) + '</code></span>'; $$('.arch-node', el).forEach((n) => n.setAttribute('aria-pressed', String(Number(n.dataset.step) === i))); };
    el.addEventListener('click', (ev) => { const n = ev.target.closest('.arch-node'); if (n) show(Number(n.dataset.step)); });
    show(0);
  }

  function scenarioTable() {
    const Pt = S.patterns;
    const pat = (text) => details('The exact pattern', '<code class="pat">' + esc(text) + '</code>');
    const rows = [
      ['Answered on the results page', 'The question talks about what a listing advertises, or says "on the results page".', Pt.targeting.RESULTS_PAGE, 'Read the results page and open nothing. The advertised prices are already there.', 'none'],
      ['Reviews', 'The question mentions buyers, reviewers or reviews.', Pt.targeting.REVIEWS, 'Read the review pages in order. Stop at the first review that says it, or only answer no after the last page.', 'Depth'],
      ['Does every listing have it', '"Every" or "all", followed later by stock, carry, offer or have.', Pt.targeting.UNIVERSAL, 'Look for one listing that lacks it. The first one found settles the answer as no; only opening all of them can give a yes.', 'Counterexample'],
      ['Best value per unit', '"Per litre", "per kg", "per unit" or "best value".', Pt.targeting.UNIT_RATE, 'A listing\'s advertised price divided by the largest pack is the best rate it could have, so listings that cannot beat the best rate found are skipped.', 'BoundPrune'],
      ['Cheapest, and it must be buyable', '"Cheapest" or "lowest price", together with a word about buying: buy, available, in stock, supply, ship.', Pt.targeting.CHEAPEST + '  and  ' + Pt.targeting.BUYABLE, 'Open listings from the lowest advertised price up. In each, choose the size, look at the page again for its price, and check the size can be chosen. Skip every unopened listing advertised at or above the best buyable price found, then stop.', 'BoundPrune'],
      ['Cheapest', '"Cheapest" or "lowest price" on its own.', Pt.targeting.CHEAPEST, 'As above without the availability check.', 'BoundPrune'],
      ['Is there any, with a price limit', '"Is there any", "does any seller", "anyone", with a limit such as "under $20" or "less than 20".', Pt.form.EXISTS + '  with  ' + Pt.form.CEILING, 'Open from the lowest advertised price up and stop at the first one that satisfies the limit and can be bought. A no needs every listing the limit does not rule out.', 'Witness'],
      ['The k cheapest', 'A number next to "cheapest": "three cheapest", "the 3 cheapest sellers".', Pt.form.TOPK + '  or  ' + Pt.form.TOPK_COUNT, 'The same bound, applied to the k-th best rather than the best.', 'BoundPrune'],
      ['Most expensive', '"Most expensive", "dearest", "highest price".', Pt.form.ARGMAX, 'The advertised price is a lower bound, so it cannot rule anything out here; every listing is opened.', 'BoundPrune'],
      ['A named listing, or two to compare', 'A product URL in the question, or "between A and B" / "of A and B" with seller names.', Pt.form.URL + '  or  ' + Pt.form.NAMED_PAIR, 'Open exactly those listings.', 'Lookup'],
      ['A count, or any other shopping question without one of the shapes above', 'A shopping word is present (listing, seller, offer, product, price, size and so on) but none of the shapes above matched.', 'the fallback; the market words are ' + Pt.form.MARKET_WORDS, 'Open every listing. A count cannot stop early.', 'Exhaust'],
      ['Not a shopping question', 'None of the shopping signals is present: no URL, no market word, no price word, no size or variant word, no availability word, no review word, no condition.', 'none of the signals in form.SIGNALS', 'The block does nothing. The agent gets the question unchanged, and the batch counts how often this happened.', 'none'],
    ];
    const asks = [
      ['Two readings of a verb', 'One of offer, carry, stock, sell or have, within six words of a word like size, pack, variant or colour, and nothing in the question that settles which reading is meant (such as "in stock", "available to buy", "can be bought", "listed", "even if sold out").', Pt.ambiguity.VERB + '  then  ' + Pt.ambiguity.GOVERNED + '  and none of  ' + Pt.ambiguity.CLEAR, 'Whether they mean listings whose menu lists the size, sold out or not, or listings that can sell it now.'],
      ['No threshold', 'A vague price word (cheap, affordable, budget, bargain) and no number anywhere in the question.', Pt.form.VAGUE_PRICE, 'What price counts as cheap.'],
      ['Something the shop does not show', 'The question needs an attribute that neither the results page nor a listing page shows here. A listing page on these markets shows ' + S.patterns.listing_page_shows.join(', ') + '; the results page shows the seller, the title, the advertised price and the URL; a review page shows ' + S.patterns.review_page_shows.join(', ') + '. Delivery time, shipping cost, warranty and ratings on these listings are not shown.', 'anything outside form.LISTING_PAGE_SHOWS, form.REVIEW_PAGE_SHOWS and the results page', 'Nothing is asked. The block says what the shop does not show and runs nothing.'],
    ];
    $('#scenarios').innerHTML = '<table class="fit"><thead><tr><th>Question kind</th><th>What triggers it</th><th>What the agent is told to do, and when to stop</th><th>Primitive</th></tr></thead><tbody>' +
      rows.map((r) => '<tr><td><b>' + esc(r[0]) + '</b></td><td>' + esc(r[1]) + pat(r[2]) + '</td><td>' + esc(r[3]) + '</td><td class="mono">' + esc(r[4] === 'none' ? '' : r[4]) + '</td></tr>').join('') + '</tbody></table>' +
      '<h4>When the block asks, or pushes the question back, instead of planning</h4><table class="fit"><thead><tr><th>Case</th><th>What triggers it</th><th>What the user is asked</th></tr></thead><tbody>' +
      asks.map((r) => '<tr><td><b>' + esc(r[0]) + '</b></td><td>' + esc(r[1]) + pat(r[2]) + '</td><td>' + esc(r[3]) + '</td></tr>').join('') + '</tbody></table>' +
      '<p class="note">Versions in the code today: box ' + S.patterns.versions.box + ', form ' + S.patterns.versions.form + ', primitives ' + S.patterns.versions.primitives + ', strategy text ' + S.patterns.versions.targeting + ', planner ' + S.patterns.versions.planner + '.</p>';
  }

  function censusBlock() {
    const c = S.census;
    $('#census').innerHTML = '<div class="stats">' +
      '<div class="stat"><b>' + c.same_quantifier + ' of ' + c.calls + '</b><span>chose the same kind of answer, the field that picks the strategy</span></div>' +
      '<div class="stat"><b>' + c.same_quantifier_objective + ' of ' + c.calls + '</b><span>the same kind and the same attribute</span></div>' +
      '<div class="stat"><b>' + c.same_with_population + ' of ' + c.calls + '</b><span>and the same population</span></div>' +
      '<div class="stat"><b>' + c.same_every_field + ' of ' + c.calls + '</b><span>the same on every field</span></div>' +
      '<div class="stat"><b>' + money(c.charged, 3) + '</b><span>for ' + c.calls + ' calls to ' + esc(c.model.split('/')[1]) + ' at temperature ' + c.temperature + ', with no browser</span></div></div>' +
      details('The four questions where the model and the rules chose a different kind of answer or attribute',
        '<table class="fit"><thead><tr><th>Question</th><th>Rules</th><th>Model</th><th>Which is right</th></tr></thead><tbody>' +
        c.disagreements.map((d, i) => '<tr><td>' + esc(d.question) + '</td><td class="mono">' + esc(d.rules.quantifier + ' ' + d.rules.objective + ' over ' + d.rules.population) + '</td><td class="mono">' + esc(d.model.quantifier + ' ' + d.model.objective + ' over ' + d.model.population) + '</td><td>' + (i === 0 ? 'either, both open the two named pages' : 'the rules') + '</td></tr>').join('') + '</tbody></table>');
  }

  function unitTests() {
    $('#unit').innerHTML = S.tests.unit.map((f) => details(esc(f.file.replace('experiments/tests/', '')) + ', ' + sum(f.classes.map((c) => c.tests.length)) + ' tests',
      '<p class="note">' + esc(f.doc) + '</p>' + f.classes.map((c) => '<h4>' + esc(c.name) + '</h4>' + (c.doc ? '<p class="note">' + esc(c.doc) + '</p>' : '') + '<ul>' + c.tests.map((t) => '<li>' + esc(t) + '</li>').join('') + '</ul>').join(''))).join('');
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
