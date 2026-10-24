import { expect, mock, test } from 'claude-code/testing'

// Made-up numbers: nobody's real usage
const NOW = Date.parse('2026-10-23T12:50:00Z')
const sample = (generatedAt = '2026-10-23T15:45+03:00', topModel = 'claude-opus-5-5') => ({
  generatedAt,
  today: '2026-10-23',
  utcOffsetMinutes: 180,
  days: [{ date: '2026-10-22', messages: 30, prompts: 3, sessions: 1, tools: 4, tokens: 5000, topModel }],
  hours: Array.from({ length: 24 }, (_, hour) => ({ hour, prompts: 0 })),
  sessions: [],
})

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

type Opts = {
  store?: Record<string, unknown>
  python?: (argv: string[]) => Run | null // null: that name is not installed
  scriptExists?: boolean
}

function engine(on: any, opts: Opts = {}) {
  const seen = { runs: [] as string[], titles: [] as string[], descriptions: [] as string[], toasts: [] as string[] }
  const clock = mock.clock(on, { now: NOW })
  mock.store(on, opts.store)
  on('command.register', (_: unknown, e: { name: string; description: string }) => {
    seen.descriptions.push(e.description)
    return { value: { command: e.name } }
  })
  on('ui.open', (_: unknown, e: { title: string }) => {
    seen.titles.push(e.title)
    return { value: { isPlaced: true } }
  })
  on('ui.panes', () => ({ value: [{ id: 'usage-calendar', title: 'x', isShown: true, isFocused: false, isPlaced: true }] }))
  on('ui.toast', (_: unknown, e: { text: string }) => {
    seen.toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.status', () => ({ value: undefined }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('session.attach', (_: unknown, e: { clientId: string }) => ({ clientId: e.clientId }))
  on('session.measure', (_: unknown, e: { changed: string[] }) => ({ changed: e.changed }))
  on('session.id', () => ({ value: 'self' }))
  on('session.surfaces', () => ({ value: [] }))
  on('fs.stat', () => {
    if (opts.scriptExists === false) throw new Error('ENOENT')
    return { value: { kind: 'file', size: 1, mtimeMs: 0 } }
  })
  on('session.usage', () => ({
    value: { startedAt: 0, context: { window: 1_000_000 }, rateLimits: [{ kind: 'five_hour', percentUsed: 50 }] },
  }))
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    const answer = (opts.python ?? (argv => (argv[0] === 'python' ? ok(JSON.stringify(sample())) : null)))(e.argv)
    if (!answer) return { value: { exitCode: 9009, stdout: '', stderr: 'Python was not found', isStdoutTruncated: false, isStderrTruncated: false } }
    seen.runs.push(e.argv[0]!)
    return { value: { ...answer, isStdoutTruncated: false, isStderrTruncated: false } }
  })
  return { seen, clock }
}

const startDesktop = async ($: any) => {
  // The desktop app starts its sessions headless and attaches its window afterwards
  await $.session.start({ cwd: '/', surface: null, isInteractive: false })
  await $.session.attach({ surface: 'desktop', clientId: 'desktop:default' })
}

test('a desktop session opens the panel and refreshes once its window attaches', async ($, on) => {
  const { seen } = engine(on)
  await $.session.start({ cwd: '/', surface: null, isInteractive: false })
  expect([seen.titles.length, seen.runs.length]).toEqual([0, 0]) // nothing before a window
  await $.session.attach({ surface: 'desktop', clientId: 'desktop:default' })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(seen.titles).toEqual(['Usage Calendar'])
  expect(seen.runs).toEqual(['python'])
  expect(await has(ui, /^Data as of /)).toBe('found')
  await ui.unmount()
})

test('a second start in the same session (a reload) does not reopen the panel', async ($, on) => {
  const { seen } = engine(on, { store: { data: sample() } })
  await startDesktop($)
  await $.session.start({ cwd: '/', surface: null, isInteractive: false })
  await $.session.attach({ surface: 'desktop', clientId: 'desktop:default' })
  expect(seen.titles.length).toBe(1)
})

test('switching language retitles the pane and the command', async ($, on) => {
  const { seen } = engine(on, { store: { data: sample() } })
  await startDesktop($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'lang' })
  expect(seen.titles[seen.titles.length - 1]).toBe('Kullanım Takvimi')
  expect(seen.descriptions[seen.descriptions.length - 1]).toBe('Claude Code Kullanım Takvimi panelini açar')
  await ui.unmount()
})

test('fresh numbers kept by another session clear an old failure', async ($, on) => {
  let fail = false
  const later = new Date(NOW + 31 * 60e3).toISOString()
  const { clock } = engine(on, {
    store: { data: sample(later) }, // "kept by another session" when the timer looks
    python: argv => (argv[0] !== 'python' ? null : fail ? { exitCode: 1, stdout: '', stderr: 'Traceback\nValueError: boom' } : ok(JSON.stringify(sample(later)))),
  })
  await startDesktop($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  fail = true
  await ui.press({ key: 'refresh' })
  expect(await has(ui, /Refresh failed: ValueError: boom/)).toBe('found')
  await clock.advance(30 * 60e3 + 1000)
  expect(await has(ui, /Refresh failed/)).toBe('missing /Refresh failed/')
  await ui.unmount()
})

test('a pipe in a model name stays inside its table cell', async ($, on) => {
  engine(on, { store: { data: sample(undefined, 'gateway|model') } })
  await startDesktop($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'sec-days' })
  expect(JSON.stringify(await ui.drawn())).toContain('gateway\\\\|model')
  await ui.unmount()
})

test('a missing script says so instead of blaming Python', async ($, on) => {
  engine(on, { scriptExists: false })
  await startDesktop($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await has(ui, /usage script is missing/)).toBe('found')
  await ui.unmount()
})

test('a Python 2 that cannot read the script makes way for the next name', async ($, on) => {
  const { seen } = engine(on, {
    python: argv =>
      argv[0] === 'python3'
        ? { exitCode: 1, stdout: '', stderr: '  File "collect_usage.py", line 120\n    x = f"{y}"\n          ^\nSyntaxError: invalid syntax' }
        : argv[0] === 'python'
          ? ok(JSON.stringify(sample()))
          : null,
  })
  await startDesktop($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(seen.runs).toEqual(['python3', 'python'])
  expect(await has(ui, /^Data as of /)).toBe('found')
  await ui.unmount()
})

test('limit windows that leave are no longer shown as live', async ($, on) => {
  engine(on, { store: { data: sample() } })
  await startDesktop($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await has(ui, /^50%$/)).toBe('found')
  await $.session.measure({ context: { window: 1_000_000 }, rateLimits: [], changed: ['rateLimits'] })
  expect(await has(ui, /^50%$/)).toBe('missing /^50%$/')
  await ui.unmount()
})

test('an automatic refresh steps aside while another session holds the lock; a press does not', async ($, on) => {
  const { seen } = engine(on, { store: { refreshLock: { at: NOW - 10_000 } } })
  await startDesktop($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(seen.runs).toEqual([])
  await ui.press({ key: 'refresh' })
  expect(seen.runs).toEqual(['python'])
  await ui.unmount()
})

test('kept data whose time does not parse is not used', async ($, on) => {
  engine(on, { store: { data: sample('not a time') }, python: () => null })
  await startDesktop($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(JSON.stringify(await ui.drawn())).not.toContain('NaN')
  expect(await has(ui, /No data yet/)).toBe('found')
  await ui.unmount()
})

test('an exit code reads in the panel language', async ($, on) => {
  engine(on, {
    store: { view: { lang: 'tr' } },
    python: argv => (argv[0] === 'python' ? { exitCode: 3, stdout: '', stderr: '' } : null),
  })
  await startDesktop($)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await has(ui, /^Yenilenemedi: çıkış kodu 3$/)).toBe('found')
  await ui.unmount()
})
