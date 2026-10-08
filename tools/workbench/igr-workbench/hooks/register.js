// igr-workbench: the research workbench for this repository.
//
// Two jobs, each written after mistakes that cost this project time or money. LESSONS.md
// numbers the mistakes, and the numbers are cited where each rule is enforced.
//
//   1. Keep the objective in front of every turn, and flag a turn that drifts from it.
//      Lesson 26: weeks of side investigations without a decisive result.
//   2. Refuse any command that spends OpenRouter credit until the code it runs has a
//      verifier pass, its cost is declared, the laptop is kept awake and the user agrees.
//      Lessons 15, 23 and 25.

const OBJECTIVE_FILE = 'OBJECTIVE.md'
const PARKED_FILE = 'PARKED.md'
const STAMP_FILE = '.verification/latest.json'
const LEDGER_FILE = '.verification/spend.jsonl'

// The code a paid run depends on. Results and run logs change with every run, so they are
// not code. Kept identical to CODE_PATHS in tools/verification_stamp.py.
const CODE_PATHS = ['experiments', 'env', 'tools', ':(exclude)experiments/results', ':(exclude)experiments/runs']

// Running one of these scripts calls a paid model through OpenRouter. Matched where a script
// is executed, so reading or searching the file is not mistaken for running it. The text after
// the script, up to the next separator, is that invocation's arguments.
const PAID_RUN = /(?:python[0-9.]*|\bsh|\bbash)\s+(?:-u\s+)?(?:\S*\/)?(suite\.py|run_browser_task\.py|naive_agent\.py|plan_probe\.py|run\.sh)\b([^;&|\n"']*)/g
const PAID_DIRECT = /(?:^|[;&|(]\s*)(?:caffeinate\s+(?:-\w+\s+)*)?(?:nohup\s+)?(?:\.\/)?(?:\S*\/)?run\.sh\b([^;&|\n"']*)/g
// A dry run or a help page calls no model. Checked per invocation, so a free invocation
// cannot carry a paid one through in the same command.
const FREE_FLAG = /(?:^|\s)(?:--dry-run|--help|-h)(?=\s|$)/
const ESTIMATE = /\bIGR_ESTIMATE_USD=([0-9]+(?:\.[0-9]+)?)\b/
const AWAKE = /\bcaffeinate\b[^;&|\n]*?\s-[a-z]*i/
const STAMPER = /\btools\/verification_stamp\.py\b/
const IN_VERIFICATION = /\.verification\//
const WRITES = /(>|\btee\b|\bcp\b|\bmv\b|\brm\b|\btouch\b|\bln\b|\btruncate\b)/

const DRIFT_SYSTEM = 'You check whether one turn of an AI assistant served a research project\'s objective. ' +
  'Reply with one line only: ON TRACK, or DRIFT: followed by the reason in under fifteen words. ' +
  'On track means the turn specified, built, verified, measured or reported on what the objective names, ' +
  'its baselines or its evaluation, or kept up the tools that make that work accurate. ' +
  'Drift means the turn pursued something else, including when the user asked for it.'

let lastPrompt = ''
let lastDrift = null
let driftCheck = true

function northStar(text) {
  const found = text.match(/## North star\s*\n+([\s\S]*?)(?:\n## |$)/)
  return (found ? found[1] : text).trim()
}

function paidScripts(command) {
  const scripts = []
  for (const m of command.matchAll(PAID_RUN)) {
    if (!FREE_FLAG.test(m[2])) scripts.push(m[1])
  }
  for (const m of command.matchAll(PAID_DIRECT)) {
    if (!FREE_FLAG.test(m[1])) scripts.push('run.sh')
  }
  return scripts
}

// Whether the code checked out now is the code the verifier passed. Lesson 23: results were
// reported, and runs paid for, before anything had been verified.
async function verification($) {
  const head = (await $.process.run(['git', 'rev-parse', 'HEAD'])).stdout.trim()
  const dirty = (await $.process.run(['git', 'status', '--porcelain', '--', ...CODE_PATHS])).stdout.trim()
  let stamp = null
  if (await $.fs.exists(STAMP_FILE)) {
    try {
      stamp = JSON.parse(await $.fs.read(STAMP_FILE))
    } catch {
      stamp = null
    }
  }
  const problems = []
  if (!stamp) {
    problems.push('no verifier stamp exists')
  } else {
    if (stamp.verdict !== 'pass') problems.push('the latest verification failed (' + stamp.scope + ')')
    if (stamp.commit !== head) {
      problems.push('the stamp is for commit ' + String(stamp.commit).slice(0, 10) + ', and ' + head.slice(0, 10) + ' is checked out')
    }
  }
  if (dirty) problems.push('experiment code has uncommitted changes: ' + dirty.split('\n').join(', '))
  return { head, dirty, stamp, problems }
}

async function record($, entry) {
  try {
    const before = (await $.fs.exists(LEDGER_FILE)) ? await $.fs.read(LEDGER_FILE) : ''
    await $.fs.write(LEDGER_FILE, before + JSON.stringify(entry) + '\n')
  } catch {
    // A failed ledger write must not undo a run that has already happened
  }
}

async function guardPaid($, e, next, command, scripts) {
  // Lesson 25: credit was spent without the user seeing it coming
  const estimate = command.match(ESTIMATE)
  if (!estimate) {
    return { deny: 'Paid run refused by the workbench guard: no cost is declared. Tell the user the estimated cost and the run count, then put IGR_ESTIMATE_USD=<dollars> in front of the command.' }
  }
  // Lesson 15: the laptop slept mid-batch and three runs were voided
  if (!AWAKE.test(command)) {
    return { deny: 'Paid run refused by the workbench guard: wrap the run in caffeinate -i so the laptop cannot sleep mid-batch.' }
  }
  const state = await verification($)
  if (state.problems.length) {
    return { deny: 'Paid run refused by the workbench guard: ' + state.problems.join('; ') + '. Commit the code, ask the verifier subagent to verify commit ' + state.head.slice(0, 10) + ' for this run, and run the command again once it has stamped a pass.' }
  }
  let answer = null
  try {
    answer = await $.ui.ask(
      'Run a paid batch? ' + scripts.join(', ') + ', estimated $' + estimate[1] + '. Verified at ' + state.head.slice(0, 10) + ': ' + state.stamp.scope + '.',
      ['Run it', 'Refuse'],
    )
  } catch {
    answer = null
  }
  if (answer !== 'Run it') {
    return { deny: answer === null
      ? 'Paid run refused by the workbench guard: the user did not answer the approval question, so nothing was spent. Ask the user what they want.'
      : 'The user refused this paid run. Do not retry it. Ask the user what they want instead.' }
  }
  const result = await next(e)
  await record($, {
    at: new Date().toISOString(),
    commit: state.head,
    scope: state.stamp.scope,
    estimate_usd: Number(estimate[1]),
    scripts,
    refused_by_tool: result.deny || null,
    command: command.slice(0, 500),
  })
  return result
}

export function register(on) {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    try {
      await $.command.register({ name: 'objective', description: 'Show the objective, the last objective check and the parked ideas. "/objective drift off" stops the check', argumentHint: '[drift on|off]', immediate: true })
    } catch {
      // A taken command name must not stop the rest of the workbench
    }
    try {
      await $.command.register({ name: 'park', description: 'Save a side idea to PARKED.md instead of pursuing it', argumentHint: '<idea>', immediate: true })
    } catch {
      // As above
    }
    try {
      await $.command.register({ name: 'guard', description: 'Show the spend guard: verifier stamp, uncommitted code, recent paid runs. "/guard test" checks the approval dialog', argumentHint: '[test]', immediate: true })
    } catch {
      // As above
    }
    return result
  })

  // Job 1: the objective rides along with every prompt, where only Claude reads it
  on('prompt.submit', async ($, e, next) => {
    lastPrompt = e.text
    let star = ''
    try {
      star = northStar(await $.fs.read(OBJECTIVE_FILE))
    } catch {
      return next(e)
    }
    const lines = [
      'Project objective, from OBJECTIVE.md: ' + star,
      'Keep this turn on the objective. If the request does not serve it, say so in one line and suggest /park.',
    ]
    if (lastDrift) lines.push('The objective check flagged the previous turn: ' + lastDrift + '. Correct course, or say why the detour was needed.')
    return next({ ...e, context: [...(e.context ?? []), lines.join('\n')] })
  })

  // A small model reads each finished turn of the main conversation against the objective.
  // A drift is shown under the answer, where the app can draw it, and is always passed into
  // the next prompt, which every app delivers.
  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    if (!driftCheck || e.agentId || e.isAborted || !e.answer) return result
    let star = ''
    try {
      star = northStar(await $.fs.read(OBJECTIVE_FILE))
    } catch {
      return result
    }
    let reply = null
    try {
      reply = await $.model.complete({
        model: 'haiku',
        system: DRIFT_SYSTEM,
        prompt: 'Objective:\n' + star + '\n\nThe user\'s request:\n' + lastPrompt.slice(0, 2000) +
          '\n\nThe assistant\'s final answer:\n' + e.answer.slice(0, 4000),
        maxTokens: 60,
      })
    } catch {
      return result
    }
    if (!reply || !reply.isAnswered) return result
    const verdict = reply.text.trim().split('\n')[0]
    lastDrift = /^DRIFT/i.test(verdict) ? verdict.replace(/^DRIFT:?\s*/i, '') : null
    return lastDrift ? { ...result, text: 'objective check: drift, ' + lastDrift } : result
  })

  // Job 2: the spend guard, on every shell command Claude or a subagent runs
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const command = String(e.command || '')
    if (STAMPER.test(command)) {
      const agents = e.agentId ? await $.agent.list() : []
      const agent = agents.find((a) => a.id === e.agentId)
      if (!agent || agent.type !== 'verifier') {
        return { deny: 'Only the verifier subagent writes the verification stamp. Ask it to verify, and it stamps on a pass.' }
      }
      return next(e)
    }
    if (IN_VERIFICATION.test(command) && WRITES.test(command)) {
      return { deny: 'Nothing writes into .verification/ except tools/verification_stamp.py, run by the verifier.' }
    }
    const scripts = paidScripts(command)
    if (!scripts.length) return next(e)
    try {
      return await guardPaid($, e, next, command, scripts)
    } catch (error) {
      return { deny: 'Paid run refused: the workbench guard failed (' + String(error && error.message ? error.message : error) + '), so nothing was spent.' }
    }
  }).catch(async ($, e, next) => {
    return { deny: 'The workbench guard ' + (next.error.kind === 'timeout' ? 'timed out' : 'failed') + ' on this shell command, so it was not run. Try again, or check the guard with /guard.' }
  })

  on('tool.call', { tool: ['Write', 'Edit', 'MultiEdit', 'NotebookEdit'] }, async ($, e, next) => {
    if (IN_VERIFICATION.test(String(e.file_path || e.notebook_path || ''))) {
      return { deny: 'Nothing writes into .verification/ except tools/verification_stamp.py, run by the verifier.' }
    }
    return next(e)
  })

  on('command.run', { command: 'objective' }, async ($, e) => {
    const arg = String(e.args || '').trim()
    if (/^drift\s+off$/i.test(arg)) {
      driftCheck = false
      return { text: 'Objective check after each turn: off.' }
    }
    if (/^drift\s+on$/i.test(arg)) {
      driftCheck = true
      return { text: 'Objective check after each turn: on.' }
    }
    let star = '(OBJECTIVE.md was not found)'
    try {
      star = northStar(await $.fs.read(OBJECTIVE_FILE))
    } catch {
      // Keep the placeholder
    }
    let parked = 0
    try {
      parked = ((await $.fs.read(PARKED_FILE)).match(/^- /gm) || []).length
    } catch {
      parked = 0
    }
    return { text: star + '\n\nLast objective check: ' + (lastDrift ? 'drift, ' + lastDrift : 'no drift flagged') +
      '. Check after each turn: ' + (driftCheck ? 'on' : 'off') + '. Parked ideas: ' + parked + '.' }
  })

  on('command.run', { command: 'park' }, async ($, e) => {
    const idea = String(e.args || '').trim()
    if (!idea) return { text: 'Usage: /park <idea>' }
    let text = '# Parked\n'
    try {
      text = await $.fs.read(PARKED_FILE)
    } catch {
      text = '# Parked\n'
    }
    const today = new Date().toISOString().slice(0, 10)
    await $.fs.write(PARKED_FILE, text.replace(/\s*$/, '\n') + '- ' + today + ': ' + idea + '\n')
    return { text: 'Parked: ' + idea }
  })

  on('command.run', { command: 'guard' }, async ($, e) => {
    if (String(e.args || '').trim() === 'test') {
      let answer = null
      try {
        answer = await $.ui.ask('Workbench test: can you see this question?', ['Yes', 'No'])
      } catch {
        answer = null
      }
      return { text: answer
        ? 'The approval dialog works here. You answered ' + answer + '.'
        : 'The approval dialog could not be shown here, so a paid run cannot be approved in this app.' }
    }
    const state = await verification($)
    let recent = []
    try {
      recent = (await $.fs.read(LEDGER_FILE)).trim().split('\n').slice(-3)
    } catch {
      recent = []
    }
    const stamp = state.stamp
      ? state.stamp.verdict + ' at ' + String(state.stamp.commit).slice(0, 10) + ', ' + state.stamp.at + ': ' + state.stamp.scope
      : 'none'
    return { text: 'Checked out: ' + state.head.slice(0, 10) + '\nVerifier stamp: ' + stamp +
      '\nA paid run would be ' + (state.problems.length ? 'refused: ' + state.problems.join('; ') : 'allowed, after your yes') +
      '\nRecent paid runs: ' + (recent.length ? '\n' + recent.join('\n') : 'none recorded') }
  })
}
