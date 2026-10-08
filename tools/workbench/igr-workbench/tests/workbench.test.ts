import { expect, test } from 'claude-code/testing'

// Each rule gets a case where it must fire and a case where it must stay quiet, because a
// check that has never been seen to fire proves nothing (LESSONS.md, lesson 1).

const HEAD = 'abc1234567890'
const OBJECTIVE = '# Objective\n\n## North star\n\nBuild and prove a pre-processing box.\n\n## What counts as progress\n\n- things\n'
const PASS_STAMP = JSON.stringify({ verdict: 'pass', commit: HEAD, scope: 'box v1 cheapest-M', checks: ['dry run'], at: '2026-10-08T12:00:00' })

type Opts = {
  head?: string
  dirty?: string
  files?: Record<string, string>
  answer?: string | null
  agents?: { id: string, type: string }[]
}

// Stands in for Claude Code: git, the files, the approval dialog and the subagent list.
function shop(on: any, opts: Opts = {}) {
  const files: Record<string, string> = { 'OBJECTIVE.md': OBJECTIVE, ...(opts.files ?? {}) }
  const written: { path: string, text: string }[] = []
  on('process.run', ($: any, e: any) => {
    if (e.argv.includes('rev-parse')) return { value: { exitCode: 0, stdout: (opts.head ?? HEAD) + '\n', stderr: '' } }
    if (e.argv.includes('status')) return { value: { exitCode: 0, stdout: opts.dirty ?? '', stderr: '' } }
    return { value: { exitCode: 0, stdout: '', stderr: '' } }
  })
  const match = (path: string) => Object.keys(files).find((name) => path.endsWith(name))
  on('fs.exists', ($: any, e: any) => ({ value: match(e.path) !== undefined }))
  on('fs.read', ($: any, e: any) => {
    const name = match(e.path)
    return name === undefined ? { deny: 'no such file' } : { value: files[name] }
  })
  on('fs.write', ($: any, e: any) => {
    written.push({ path: e.path, text: e.text ?? e.content ?? e.data })
    return { value: undefined }
  })
  on('agent.list', () => ({ value: (opts.agents ?? []).map((a) => ({ ...a, description: '', status: 'running' })) }))
  on('tool.call', ($: any, e: any) => {
    if (e.tool === 'AskUserQuestion') {
      if (opts.answer === null) return { deny: 'dismissed' }
      return { result: { answers: { [e.questions[0].question]: opts.answer ?? 'Run it' } } }
    }
    return { result: 'ran' }
  })
  return written
}

const PAID = 'IGR_ESTIMATE_USD=3.11 caffeinate -i python3 experiments/suite.py --tasks experiments/tasks_apparel.json --repeats 3'

test('an ordinary command passes untouched', async ($, on) => {
  shop(on)
  const out = await $.tool.call({ tool: 'Bash', command: 'git status' })
  expect(out).toEqual({ result: 'ran' })
})

test('reading or searching a paid script is not running it', async ($, on) => {
  shop(on)
  for (const command of ['grep -n dry-run experiments/suite.py', 'cat experiments/run.sh', 'sed -n 1,5p experiments/naive_agent.py']) {
    expect(await $.tool.call({ tool: 'Bash', command })).toEqual({ result: 'ran' })
  }
})

test('a dry run is free', async ($, on) => {
  shop(on)
  const out = await $.tool.call({ tool: 'Bash', command: 'python3 experiments/suite.py --tasks experiments/tasks_apparel.json --exhaustive --dry-run | head -3' })
  expect(out).toEqual({ result: 'ran' })
})

test('a free invocation cannot carry a paid one through', async ($, on) => {
  shop(on)
  const out = await $.tool.call({ tool: 'Bash', command: 'python3 experiments/suite.py --dry-run; python3 experiments/suite.py --repeats 3' })
  expect(out.deny).toMatch(/no cost is declared/)
})

test('every paid script is recognised', async ($, on) => {
  shop(on)
  for (const command of [
    'python3 experiments/suite.py --repeats 1',
    'uv run python /Users/x/repo/experiments/run_browser_task.py "a task"',
    '.venv-naive/bin/python experiments/naive_agent.py "a task"',
    'python3 experiments/plan_probe.py',
    'bash experiments/run.sh "a task"',
    './experiments/run.sh "a task"',
    'caffeinate -i sh -c "python3 -u experiments/suite.py --only x > out.log 2>&1"',
  ]) {
    const out = await $.tool.call({ tool: 'Bash', command })
    expect(out.deny).toMatch(/no cost is declared/)
  }
})

test('a paid run must be kept awake', async ($, on) => {
  shop(on)
  const out = await $.tool.call({ tool: 'Bash', command: 'IGR_ESTIMATE_USD=3 python3 experiments/suite.py --repeats 3' })
  expect(out.deny).toMatch(/caffeinate -i/)
})

test('a paid run needs a verifier stamp', async ($, on) => {
  shop(on)
  const out = await $.tool.call({ tool: 'Bash', command: PAID })
  expect(out.deny).toMatch(/no verifier stamp exists/)
})

test('a stamp for another commit does not count', async ($, on) => {
  shop(on, { head: 'fff0000000000', files: { '.verification/latest.json': PASS_STAMP } })
  const out = await $.tool.call({ tool: 'Bash', command: PAID })
  expect(out.deny).toMatch(/the stamp is for commit abc1234567, and fff0000000 is checked out/)
})

test('a failed verification does not count', async ($, on) => {
  shop(on, { files: { '.verification/latest.json': JSON.stringify({ verdict: 'fail', commit: HEAD, scope: 'box v1' }) } })
  const out = await $.tool.call({ tool: 'Bash', command: PAID })
  expect(out.deny).toMatch(/the latest verification failed/)
})

test('uncommitted experiment code does not count', async ($, on) => {
  shop(on, { dirty: ' M experiments/targeting.py', files: { '.verification/latest.json': PASS_STAMP } })
  const out = await $.tool.call({ tool: 'Bash', command: PAID })
  expect(out.deny).toMatch(/uncommitted changes: M experiments\/targeting.py/)
})

test('a verified, declared, awake run still waits for the user, and is logged', async ($, on) => {
  const written = shop(on, { files: { '.verification/latest.json': PASS_STAMP } })
  const out = await $.tool.call({ tool: 'Bash', command: PAID })
  expect(out).toEqual({ result: 'ran' })
  expect(written.length).toBe(1)
  expect(written[0].path).toMatch(/\.verification\/spend\.jsonl$/)
  expect(written[0].text).toMatch(/"estimate_usd":3\.11/)
})

test('the user can refuse', async ($, on) => {
  shop(on, { answer: 'Refuse', files: { '.verification/latest.json': PASS_STAMP } })
  const out = await $.tool.call({ tool: 'Bash', command: PAID })
  expect(out.deny).toMatch(/The user refused this paid run/)
})

test('an unanswered question spends nothing', async ($, on) => {
  shop(on, { answer: null, files: { '.verification/latest.json': PASS_STAMP } })
  const out = await $.tool.call({ tool: 'Bash', command: PAID })
  expect(out.deny).toMatch(/did not answer the approval question/)
})

test('only the verifier writes the stamp', async ($, on) => {
  shop(on, { agents: [{ id: 'v1', type: 'verifier' }, { id: 'c1', type: 'coder' }] })
  const stamp = 'python3 tools/verification_stamp.py --scope "box v1" --checks "dry run"'
  expect((await $.tool.call({ tool: 'Bash', command: stamp })).deny).toMatch(/Only the verifier subagent/)
  expect((await $.tool.call({ tool: 'Bash', command: stamp, agentId: 'c1' })).deny).toMatch(/Only the verifier subagent/)
  expect(await $.tool.call({ tool: 'Bash', command: stamp, agentId: 'v1' })).toEqual({ result: 'ran' })
})

test('nothing else writes into .verification/', async ($, on) => {
  shop(on)
  expect((await $.tool.call({ tool: 'Bash', command: 'echo {} > .verification/latest.json' })).deny).toMatch(/Nothing writes into/)
  expect((await $.tool.call({ tool: 'Write', file_path: '/repo/.verification/latest.json', content: '{}' })).deny).toMatch(/Nothing writes into/)
  expect(await $.tool.call({ tool: 'Bash', command: 'cat .verification/latest.json' })).toEqual({ result: 'ran' })
  expect(await $.tool.call({ tool: 'Write', file_path: '/repo/notes/a.md', content: 'x' })).toEqual({ result: 'ran' })
})

test('the objective rides along with every prompt', async ($, on) => {
  shop(on)
  let seen: any = null
  on('prompt.submit', ($: any, e: any) => {
    seen = e
    return { text: e.text }
  })
  await $.prompt.submit({ text: 'what next', wait: false })
  expect(seen.text).toBe('what next')
  expect(seen.context.join('\n')).toMatch(/Project objective, from OBJECTIVE.md: Build and prove a pre-processing box\./)
  expect(seen.context.join('\n')).not.toMatch(/What counts as progress/)
})

test('a drifting turn is flagged, and the flag reaches the next prompt', async ($, on) => {
  shop(on)
  on('model.complete', () => ({ value: { isAnswered: true, text: 'DRIFT: redesigned the slide deck', usage: { input_tokens: 1, output_tokens: 1, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 } } }))
  on('turn.complete', () => ({ text: '' }))
  let seen: any = null
  on('prompt.submit', ($: any, e: any) => {
    seen = e
    return { text: e.text }
  })
  await $.prompt.submit({ text: 'make the deck nicer', wait: false })
  const shown = await $.turn.complete({ turnId: 't1', answer: 'I restyled every slide.', durationMs: 10, isAborted: false, usage: null })
  expect(shown.text).toBe('objective check: drift, redesigned the slide deck')
  await $.prompt.submit({ text: 'next', wait: false })
  expect(seen.context.join('\n')).toMatch(/flagged the previous turn: redesigned the slide deck/)
})

test('an on-track turn shows nothing and clears the flag', async ($, on) => {
  shop(on)
  on('model.complete', () => ({ value: { isAnswered: true, text: 'ON TRACK', usage: { input_tokens: 1, output_tokens: 1, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 } } }))
  on('turn.complete', () => ({ text: '' }))
  const shown = await $.turn.complete({ turnId: 't1', answer: 'Wrote the box spec.', durationMs: 10, isAborted: false, usage: null })
  expect(shown.text).toBe('')
})

test('a subagent turn is not checked', async ($, on) => {
  shop(on)
  let asked = false
  on('model.complete', () => {
    asked = true
    return { value: { isAnswered: true, text: 'DRIFT: x', usage: { input_tokens: 1, output_tokens: 1, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 } } }
  })
  on('turn.complete', () => ({ text: '' }))
  await $.turn.complete({ turnId: 't1', answer: 'done', durationMs: 10, isAborted: false, usage: null, agentId: 'v1' })
  expect(asked).toBe(false)
})

test('/park saves the idea with the date', async ($, on) => {
  const written = shop(on, { files: { 'PARKED.md': '# Parked\n\n- 2026-10-08: reviews\n' } })
  const out = await $.command.run({ command: 'park', args: 'try a second market' })
  expect(out.text).toBe('Parked: try a second market')
  expect(written[0].path).toMatch(/PARKED\.md$/)
  expect(written[0].text).toMatch(/- 2026-10-08: reviews\n- \d{4}-\d{2}-\d{2}: try a second market\n$/)
})

test('/guard says why a paid run would be refused', async ($, on) => {
  shop(on, { dirty: ' M experiments/planner.py' })
  const out = await $.command.run({ command: 'guard', args: '' })
  expect(out.text).toMatch(/A paid run would be refused: no verifier stamp exists; experiment code has uncommitted changes/)
})
