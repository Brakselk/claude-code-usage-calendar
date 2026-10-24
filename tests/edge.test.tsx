import { expect, mock, test } from 'claude-code/testing'

// Made-up numbers: nobody's real usage
const NOW = Date.parse('2026-10-23T12:50:00Z')
const SAMPLE = {
  generatedAt: '2026-10-23T15:45+03:00',
  today: '2026-10-23',
  utcOffsetMinutes: 180,
  days: [{ date: '2026-10-22', messages: 30, prompts: 3, sessions: 1, tools: 4, tokens: 999_960, topModel: 'claude-opus-5-5' }],
  hours: Array.from({ length: 24 }, (_, hour) => ({ hour, prompts: 0 })),
  sessions: [],
}

const PANE = {
  plugin: 'usage-calendar',
  component: 'Pane',
  requestId: 'usage-calendar',
  props: { title: 'Usage Calendar', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

type Run = { exitCode: number; stdout: string; stderr: string }
const ok = (stdout: string): Run => ({ exitCode: 0, stdout, stderr: '' })
const has = async (ui: { find: (q: { type: 'Text'; text: RegExp }) => Promise<unknown> }, text: RegExp) =>
  (await ui.find({ type: 'Text', text })) ? 'found' : `missing ${text}`

/** The engine beneath the plugin; `python` answers with `answer`, other names are not installed */
function engine(on: any, answer: () => Run | Promise<Run>, opts: { store?: Record<string, unknown>; rateLimits?: unknown[] } = {}) {
  const seen = { runs: 0, opens: 0, toasts: [] as string[] }
  const clock = mock.clock(on, { now: NOW })
  mock.store(on, opts.store)
  on('command.register', () => ({ value: { command: 'usage-calendar' } }))
  on('ui.open', () => {
    seen.opens += 1
    return { value: { isPlaced: true } }
  })
  on('ui.toast', (_: unknown, e: { text: string }) => {
    seen.toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.status', () => ({ value: undefined }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 'self' }))
  on('session.usage', () => ({
    value: { startedAt: 0, context: { tokens: 1000, window: 1_000_000, percent: 0 }, rateLimits: opts.rateLimits ?? [] },
  }))
  on('process.run', async (_: unknown, e: { argv: string[] }) => {
    if (e.argv[0] !== 'python') return { value: { exitCode: 9009, stdout: '', stderr: 'Python was not found', isStdoutTruncated: false, isStderrTruncated: false } }
    seen.runs += 1
    return { value: { ...(await answer()), isStdoutTruncated: false, isStderrTruncated: false } }
  })
  return { seen, clock }
}

const start = ($: any, isInteractive = true) => $.session.start({ cwd: '/', surface: isInteractive ? 'desktop' : null, isInteractive })

test('limits kept from an earlier session survive the start of a new one', async ($, on) => {
  const kept = { rateLimits: [{ kind: 'five_hour', percentUsed: 40, resetsAt: '2026-10-23T15:00:00Z' }], at: NOW - 3_600_000 }
  engine(on, () => ok(JSON.stringify(SAMPLE)), { store: { limits: kept, data: SAMPLE } })
  await start($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await has(ui, /^5-hour limit$/)).toBe('found')
  expect(await has(ui, /^40%$/)).toBe('found')
  expect(await has(ui, /^as of /)).toBe('found') // not "live": this session hasn't read them
  await ui.unmount()
})

test('a second refresh while one runs does not start another script', async ($, on) => {
  let release = () => {}
  const gate = new Promise<void>(resolve => (release = resolve))
  const { seen } = engine(on, async () => {
    await gate
    return ok(JSON.stringify(SAMPLE))
  })
  await start($) // no kept data: the start begins a refresh, held at the gate
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'refresh' })
  release()
  await ui.unmount()
  expect(seen.runs).toBe(1)
})

test('output of the wrong shape is reported and not drawn', async ($, on) => {
  engine(on, () => ok('{"error":"nope"}'))
  await start($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await has(ui, /answered with something unexpected/)).toBe('found')
  expect(await has(ui, /No data yet/)).toBe('found')
  await ui.unmount()
})

test('a Python that runs and fails says why, not that Python is missing', async ($, on) => {
  engine(on, () => ({ exitCode: 2, stdout: '', stderr: 'usage: collect_usage.py\ncollect_usage.py: error: unrecognized arguments' }))
  await start($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await has(ui, /^Refresh failed: .*unrecognized arguments/)).toBe('found')
  await ui.unmount()
})

test('a headless run neither runs Python nor opens the panel', async ($, on) => {
  const { seen } = engine(on, () => ok(JSON.stringify(SAMPLE)))
  await start($, false)
  expect(seen.runs).toBe(0)
  expect(seen.opens).toBe(0)
})

test('the half-hourly refresh is quiet; a press says it refreshed', async ($, on) => {
  const { seen, clock } = engine(on, () => ok(JSON.stringify({ ...SAMPLE, generatedAt: new Date(clock.now()).toISOString() })))
  await start($)
  await clock.advance(2 * 30 * 60e3 + 1000)
  expect(seen.runs).toBeGreaterThan(1)
  expect(seen.toasts).toEqual([])
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'refresh' })
  expect(seen.toasts).toEqual(['Calendar refreshed'])
  await ui.unmount()
})

test('a number just under a unit says it in the next unit up', async ($, on) => {
  engine(on, () => ok(JSON.stringify(SAMPLE)), { store: { data: SAMPLE } })
  await start($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await has(ui, /^1 M$/)).toBe('found') // 999,960 tokens, not "1,000 K"
  await ui.unmount()
})

test('a web link that is not an http address is left out', { options: { webUrl: 'javascript:alert(1)' } }, async ($, on) => {
  engine(on, () => ok(JSON.stringify(SAMPLE)), { store: { data: SAMPLE } })
  await start($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(JSON.stringify(await ui.drawn())).not.toContain('javascript:')
  await ui.unmount()
})
