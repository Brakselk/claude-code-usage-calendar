import { expect, mock, test } from 'claude-code/testing'

// Made-up numbers: nobody's real usage
const NOW = Date.parse('2026-10-23T12:50:00Z')
const SAMPLE = {
  generatedAt: '2026-10-23T15:45+03:00',
  today: '2026-10-23',
  utcOffsetMinutes: 180,
  days: [
    { date: '2026-10-01', messages: 1200, prompts: 40, sessions: 12, tools: 300, tokens: 90_000_000, topModel: 'claude-opus-5-5', inputTokens: 88_000_000, outputTokens: 2_000_000, costUsd: 75.5, models: { 'claude-opus-5-5': 60_000_000, 'claude-sonnet-5-5': 30_000_000 }, isEstimated: false },
    { date: '2026-10-22', messages: 300, prompts: 10, sessions: 2, tools: 40, tokens: 5_000_000, topModel: 'claude-opus-5-5', inputTokens: 4_900_000, outputTokens: 100_000, costUsd: 4.25, models: { 'claude-opus-5-5': 5_000_000 }, isEstimated: false },
    { date: '2026-10-23', messages: 100, prompts: 5, sessions: 1, tools: 20, tokens: 2_000_000, topModel: 'claude-opus-5-5', inputTokens: 1_950_000, outputTokens: 50_000, costUsd: 1.5, models: { 'claude-opus-5-5': 2_000_000 }, isEstimated: false },
  ],
  hours: Array.from({ length: 24 }, (_, hour) => ({ hour, prompts: hour === 20 ? 12 : hour === 10 ? 4 : 0 })),
  sessions: [
    { session: 'other', title: 'Refactor the parser', where: 'terminal', model: 'claude-opus-5-5', contextTokens: 120_000, contextWindow: 1_000_000, percentUsed: 12, lastActive: '2026-10-23T14:00+03:00' },
  ],
}

const PANE = {
  plugin: 'token-garden',
  component: 'Pane',
  requestId: 'token-garden',
  props: { title: 'Token Garden', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 40 }, view: {} },
} as const

const has = async (ui: { find: (q: { type: 'Text'; text: RegExp }) => Promise<unknown> }, text: RegExp) =>
  (await ui.find({ type: 'Text', text })) ? 'found' : `missing ${text}`

function engine(on: any, runs: string[][], stdout = JSON.stringify(SAMPLE), opened = { count: 0 }) {
  mock.clock(on, { now: NOW })
  mock.store(on)
  on('command.register', () => ({ value: { command: 'token-garden' } }))
  on('ui.open', () => {
    opened.count += 1
    return { value: { isPlaced: true } }
  })
  on('ui.toast', () => ({ value: undefined }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('session.id', () => ({ value: 'self' }))
  on('session.usage', () => ({
    value: {
      startedAt: 0,
      context: { tokens: 210_000, window: 1_000_000, percent: 21 },
      rateLimits: [
        { kind: 'five_hour', percentUsed: 23, resetsAt: '2026-10-23T15:50:00Z' },
        { kind: 'seven_day', percentUsed: 12, resetsAt: '2026-10-24T21:00:00Z' },
      ],
    },
  }))
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    runs.push([...e.argv])
    // Only "python" answers here, as on a machine without a python3 command
    if (e.argv[0] !== 'python') return { value: { exitCode: 9009, stdout: '', stderr: 'not found', isStdoutTruncated: false, isStderrTruncated: false } }
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
}

test('the panel draws in English and switches to Turkish', async ($, on) => {
  const runs: string[][] = []
  engine(on, runs)
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  // The first start has no kept data, so it runs the script, trying Python names in turn
  expect(runs.map(r => r[0])).toEqual(['python3', 'python'])
  expect(runs[1]?.slice(-1)).toEqual(['--json'])
  expect(await has(ui, /^Token Garden$/)).toBe('found')
  expect(await has(ui, /^1,600$/)).toBe('found') // messages, all days
  expect(await has(ui, /^Opus 5\.5$/)).toBe('found')
  expect(await has(ui, /^October 2026$/)).toBe('found')
  expect(await has(ui, /^5-hour limit$/)).toBe('found')
  expect(await has(ui, /^23%$/)).toBe('found')
  expect(await has(ui, /^Refactor the parser$/)).toBe('found')

  await ui.press({ key: 'sec-tokens' })
  expect(await has(ui, /^\$81\.25$/)).toBe('found')

  await ui.press({ key: 'lang' })
  expect(await has(ui, /^Aktif gün$/)).toBe('found')
  expect(await has(ui, /^1\.600$/)).toBe('found')
  expect(await has(ui, /^%23$/)).toBe('found')
  expect(await has(ui, /^\$81,25$/)).toBe('found')
  await ui.unmount()
})

test('the color choice and sections answer presses', async ($, on) => {
  engine(on, [])
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })

  await ui.press({ key: 'accent-ocean' })
  expect(JSON.stringify(await ui.drawn())).toContain('#3b82f6')
  await ui.press({ key: 'sec-days' })
  expect(await ui.find({ type: 'Markdown' })).toBeDefined()
  await ui.press({ key: 'metric-tokens' })
  await ui.unmount()
})

test('no web controls unless the options name them', async ($, on) => {
  engine(on, [])
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(JSON.stringify(await ui.drawn())).not.toContain('Open on web')
  expect(await ui.find({ type: 'Button', text: /Update web too/ })).toBeUndefined()
  await ui.unmount()
})

test('with the options set, the web controls show', { options: { webUrl: 'https://example.com/dash', webRefreshTask: 'refresh-web' } }, async ($, on) => {
  engine(on, [])
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(JSON.stringify(await ui.drawn())).toContain('https://example.com/dash')
  expect(JSON.stringify(await ui.drawn())).toContain('Update web too')
  await ui.unmount()
})

test('a machine without Python gets told how to fix it', async ($, on) => {
  mock.clock(on, { now: NOW })
  mock.store(on)
  on('command.register', () => ({ value: { command: 'token-garden' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('session.usage', () => ({ value: { startedAt: 0, context: { window: 1_000_000 }, rateLimits: [] } }))
  on('process.run', () => {
    throw new Error('ENOENT')
  })
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect(await has(ui, /Python 3 was not found/)).toBe('found')
  await ui.unmount()
})

test('the terminal gets words where pictures would be', async ($, on) => {
  engine(on, [])
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect(await has(ui, /Daily messages over the last 6 months/)).toBe('found')
  await ui.unmount()
})

const BAND = {
  plugin: 'token-garden',
  component: 'AbovePrompt',
  requestId: 'band',
  props: { hasSurvey: false, isWorking: false, maxRows: 10, bodyColumns: 80, scroll: { offset: 0, bodyRows: 9 }, view: {} },
} as const

test('the button above the prompt shows only while the panel is closed', async ($, on) => {
  const opened = { count: 0 }
  engine(on, [], JSON.stringify(SAMPLE), opened)
  // What the engine draws in the band when the plugin passes
  on('ui.render', ($: any, e: any) => {
    const { Text } = $.ui.resolve(e)
    return <Text>engine band</Text>
  })

  // Before the session opens the panel, it counts as closed: the button shows
  let band = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect(await band.find({ type: 'Button', key: 'open-token-garden' })).toBeDefined()
  await band.press({ key: 'open-token-garden' })
  expect(opened.count).toBe(1)
  expect(await band.find({ type: 'Button', key: 'open-token-garden' })).toBeUndefined()
  await band.unmount()

  // The session start opens it too, so the band stays the engine's
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  band = await $.ui.mount({ ...BAND, surface: 'desktop' })
  expect(await band.find({ type: 'Text', text: /engine band/ })).toBeDefined()
  await band.unmount()
})
