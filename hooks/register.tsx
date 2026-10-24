import { atom, read, update } from 'claude-code'
import type { EngineInterface, PluginOptions, Register } from 'claude-code'

import type { CalendarView, DayRow, HourRow, Lang, LiveUsage, Metric, RefreshState, UsageData } from '../types'
import { STRINGS } from './i18n'
import type { Strings } from './i18n'

type E = EngineInterface

const PANE = 'usage-calendar'
const DAY = 864e5
const STALE_MS = 30 * 60e3
const RUN_LIMIT_MS = 150_000 // the script's own timeout is 120 s
const NO_PYTHON = 'no-python'
const BAD_OUTPUT = 'bad-output'
const SCRIPT_MISSING = 'script-missing'
const EXIT_CODE = 'exit-code:'

const MUTED = '#8a8a8a'
const WARN = '#d9a441'
const BAD = '#d9534f'
// The heatmap and bars take one accent; the heatmap's steps are its opacity, so any of these reads
const ACCENTS = [
  { id: 'clay', hex: '#d97757' },
  { id: 'ocean', hex: '#3b82f6' },
  { id: 'forest', hex: '#22a06b' },
  { id: 'violet', hex: '#8b5cf6' },
  { id: 'rose', hex: '#e5487d' },
  { id: 'amber', hex: '#e0a526' },
  { id: 'teal', hex: '#14b8a6' },
]
const METRICS: Metric[] = ['messages', 'prompts', 'sessions', 'tools', 'tokens']
const SECTION_IDS = ['tokens', 'limits', 'sessions', 'hours', 'days'] as const

type Col = { width: string; align?: 'left' | 'right' }
const LIMIT_COLS: Col[] = [{ width: '42%' }, { width: '33%' }, { width: '25%', align: 'right' }]
const SESSION_COLS: Col[] = [
  { width: '33%' },
  { width: '15%' },
  { width: '24%' },
  { width: '13%', align: 'right' },
  { width: '15%', align: 'right' },
]

const DEFAULT_VIEW: CalendarView = {
  metric: 'messages',
  weeks: 26,
  lang: 'en',
  accent: 'clay',
  open: { tokens: false, limits: true, sessions: true, hours: false, days: false },
}

const dataAtom = atom({ plugin: 'usage-calendar', key: 'data' } as const, null)
const liveAtom = atom({ plugin: 'usage-calendar', key: 'live' } as const, null)
const viewAtom = atom({ plugin: 'usage-calendar', key: 'view' } as const, DEFAULT_VIEW)
const refreshAtom = atom({ plugin: 'usage-calendar', key: 'refresh' } as const, {
  isRunning: false,
  startedAt: null,
  lastAt: null,
  error: null,
} as RefreshState)

// Per session, and kept across a reload: whether the panel was opened once, and whether × closed it
const uiAtom = atom({ plugin: 'usage-calendar', key: 'ui' } as const, { started: false, closed: false })

async function openPane($: E): Promise<void> {
  const view = await read($, viewAtom)
  await $.ui.open({ id: PANE, title: STRINGS[view.lang].paneTitle })
}

/** Work started without waiting for it: a failure there must not surface as an unhandled rejection */
const quietly = (p: Promise<unknown>) => void p.catch(() => undefined)

async function registerCommand($: E): Promise<void> {
  const lang = (await read($, viewAtom)).lang
  await $.command.register({ name: 'usage-calendar', description: STRINGS[lang].commandDescription })
}

// The line under the prompt: how to reopen the panel, and the limits as they stand
async function showStatus($: E): Promise<void> {
  const [view, live] = await Promise.all([read($, viewAtom), read($, liveAtom)])
  const S = STRINGS[view.lang]
  const limits = (live?.rateLimits ?? []).map(r => `${S.statusLimits[r.kind] ?? r.kind} ${fmtPct(r.percentUsed, S, view.lang)}`)
  $.ui.status([S.statusHint, ...limits].join(' · '))
}

// --- formatting -----------------------------------------------------------

function fmtInt(n: number, S: Strings): string {
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, S.group)
}

function fmtDec(n: number, S: Strings): string {
  const [whole, frac] = (Math.round(n * 10) / 10).toFixed(1).split('.')
  return frac === '0' ? fmtInt(Number(whole), S) : `${fmtInt(Number(whole), S)}${S.decimal}${frac}`
}

function fmtCompact(n: number, S: Strings): string {
  const units: [number, string][] = [[1e9, S.compact[2]], [1e6, S.compact[1]], [1e3, S.compact[0]]]
  for (let i = 0; i < units.length; i++) {
    const [size, unit] = units[i]!
    if (n < (size === 1e3 ? 1e4 : size)) continue
    // 999,960 rounds to 1,000 K: say it in the next unit up
    const bigger = units[i - 1]
    if (bigger && Math.round((n / size) * 10) / 10 >= 1000) return `${fmtDec(n / bigger[0], S)} ${bigger[1]}`
    return `${fmtDec(n / size, S)} ${unit}`
  }
  return fmtInt(n, S)
}

function fmtUsd(n: number, S: Strings): string {
  const [whole, cents] = n.toFixed(2).split('.')
  return `$${fmtInt(Number(whole), S)}${S.decimal}${cents}`
}

const fmtPct = (n: number, S: Strings, lang: Lang) => (lang === 'tr' ? `%${fmtDec(n, S)}` : `${fmtDec(n, S)}%`)

function fmtRel(ms: number, S: Strings, lang: Lang): string {
  const m = Math.round(Math.abs(ms) / 6e4)
  const u = (n: number, unit: string) => (lang === 'tr' ? `${n} ${unit}` : `${n}${unit}`)
  const text =
    m < 60
      ? u(m, S.units.min)
      : m < 1440
        ? `${u(Math.floor(m / 60), S.units.hour)} ${u(m % 60, S.units.min)}`
        : `${u(Math.floor(m / 1440), S.units.day)} ${u(Math.floor((m % 1440) / 60), S.units.hour)}`
  return S.rel(text, ms >= 0)
}

const pad2 = (n: number) => String(n).padStart(2, '0')

/** A Date whose UTC fields read as the user's own clock (the script reports its offset) */
const localDate = (ms: number, offsetMin: number) => new Date(ms + offsetMin * 6e4)

function fmtStamp(ms: number, offsetMin: number, S: Strings, lang: Lang): string {
  if (!Number.isFinite(ms)) return '—'
  const d = localDate(ms, offsetMin)
  const time = `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`
  const mon = S.months[d.getUTCMonth()]
  return lang === 'tr' ? `${d.getUTCDate()} ${mon} ${time}` : `${mon} ${d.getUTCDate()} ${time}`
}

function fmtDay(date: string, S: Strings, lang: Lang, isLong = false): string {
  const d = new Date(`${date.slice(0, 10)}T00:00:00Z`)
  const mon = S.months[d.getUTCMonth()]
  const weekday = S.weekdays[d.getUTCDay()]
  if (lang === 'tr') {
    const base = `${d.getUTCDate()} ${mon} ${d.getUTCFullYear()}`
    return isLong ? `${base}, ${weekday}` : base
  }
  const base = `${mon} ${d.getUTCDate()}, ${d.getUTCFullYear()}`
  return isLong ? `${weekday}, ${base}` : base
}

const fmtMonth = (ym: string, S: Strings) => `${S.monthsLong[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`

// claude-opus-5-5 → Opus 5.5, claude-haiku-4-5-20251001 → Haiku 4.5
function modelName(id: string): string {
  const base = id.replace(/-\d{8}$/, '')
  // The 3.x line put the version first: claude-3-7-sonnet → Sonnet 3.7
  const old = /^claude-(\d+)(?:-(\d+))?-([a-z]+)/.exec(base)
  if (old) return `${old[3]!.charAt(0).toUpperCase()}${old[3]!.slice(1)} ${old[1]}${old[2] ? `.${old[2]}` : ''}`
  const m = /^claude-([a-z]+)-(\d+)(?:-(\d+))?/.exec(base)
  if (!m) return id
  const family = m[1]!.charAt(0).toUpperCase() + m[1]!.slice(1)
  return `${family} ${m[2]}${m[3] ? `.${m[3]}` : ''}`
}

const meterColor = (pct: number, accent: string) => (pct >= 90 ? BAD : pct >= 70 ? WARN : accent)
const accentHex = (id: string) => ACCENTS.find(a => a.id === id)?.hex ?? ACCENTS[0]!.hex

/** Text in a Markdown table cell: a pipe or a line break would end the cell */
const mdCell = (text: string) => text.replace(/\|/g, '\\|').replace(/\s*[\r\n]+\s*/g, ' ')

/** The heatmap's first day: the Monday `weeks` weeks back, in the user's own calendar */
function heatmapStart(nowMs: number, offsetMin: number, weeks: number): number {
  const now = localDate(nowMs, offsetMin)
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  return today - (((new Date(today).getUTCDay() + 6) % 7) + (weeks - 1) * 7) * DAY
}

/** Only an http(s) address short enough for a Link; anything else would sink the pane's whole tree */
function safeUrl(raw: unknown): string {
  if (typeof raw !== 'string') return ''
  const url = raw.trim()
  return /^https?:\/\/\S+$/i.test(url) && url.length <= 2000 ? url : ''
}

// --- data -----------------------------------------------------------------

/** What the script printed, checked before anything keeps it */
function isUsageData(x: unknown): x is UsageData {
  if (!x || typeof x !== 'object') return false
  const d = x as Partial<UsageData>
  return (
    Array.isArray(d.days) &&
    Array.isArray(d.hours) &&
    Array.isArray(d.sessions) &&
    typeof d.generatedAt === 'string' &&
    Number.isFinite(Date.parse(d.generatedAt)) &&
    typeof d.utcOffsetMinutes === 'number'
  )
}

const lastLine = (text: string) => text.trim().split('\n').pop()?.trim() ?? ''
// What a launcher says when there is no such Python, the Windows Store stub's exit 9009 included
const NOT_FOUND = /not found|not recognized|cannot find|no such file|microsoft store/i

/** Runs the bundled script with the first Python 3 that answers, and remembers which one did */
async function runScript($: E): Promise<UsageData> {
  const script = `${$.plugin.root}/scripts/collect_usage.py`
  if (!(await $.fs.stat(script).then(() => true, () => false))) throw new Error(SCRIPT_MISSING)
  const saved = await $.store.get('python')
  const candidates: string[][] = [['python3'], ['python'], ['py', '-3']]
  if (Array.isArray(saved) && saved.every(part => typeof part === 'string')) candidates.unshift(saved as string[])
  for (const cmd of candidates) {
    let run
    try {
      run = await $.process.run([...cmd, script, '--json'], { timeoutMs: 120_000 })
    } catch {
      continue // that name does not start here
    }
    if (run.exitCode === 0) {
      let parsed: unknown
      try {
        parsed = JSON.parse(run.stdout)
      } catch {
        parsed = null
      }
      if (!isUsageData(parsed)) throw new Error(BAD_OUTPUT)
      await $.store.set('python', cmd)
      return parsed
    }
    // A launcher that found nothing, or a Python 2 that can't parse the script, tries the next name;
    // a Python 3 that ran and failed is the answer
    const isTooOld = run.stderr.includes('SyntaxError') && !run.stderr.includes('Traceback')
    if (run.exitCode === 9009 || isTooOld || (NOT_FOUND.test(run.stderr) && !run.stderr.includes('Traceback'))) continue
    throw new Error(lastLine(run.stderr) || `${EXIT_CODE}${run.exitCode}`)
  }
  throw new Error(NO_PYTHON)
}

type Reading = {
  rateLimits: readonly { kind: string; percentUsed: number; resetsAt?: string }[]
  context: { tokens?: number; window: number; percent?: number }
}

/** A reading from this session; one without limit windows keeps the last ones it had */
async function keepReading($: E, r: Reading, windowsChanged = false): Promise<void> {
  const kept = await read($, liveAtom)
  const now = await $.clock.now()
  const isFresh = r.rateLimits.length > 0
  // A measurement saying the windows changed to none means they left; any other empty reading keeps the last ones
  const haveLeft = !isFresh && windowsChanged
  const live: LiveUsage = {
    rateLimits: isFresh
      ? r.rateLimits.map(w => ({ kind: w.kind, percentUsed: w.percentUsed, resetsAt: w.resetsAt ?? null }))
      : haveLeft ? [] : kept?.rateLimits ?? [],
    limitsAt: isFresh || haveLeft ? now : kept?.limitsAt ?? null,
    limitsLive: isFresh || haveLeft || (kept?.limitsLive ?? false),
    contextTokens: r.context.tokens ?? null,
    contextWindow: r.context.window,
    contextPercent: r.context.percent ?? null,
    at: now,
  }
  await update($, liveAtom, () => live)
  // A new session has no reading until its first reply: it shows the last one meanwhile
  if (isFresh) await $.store.set('limits', { rateLimits: live.rateLimits, at: now })
  await showStatus($)
}

async function loadLive($: E): Promise<void> {
  await keepReading($, await $.session.usage())
}

async function refreshAll($: E, announce: boolean): Promise<void> {
  const now = await $.clock.now()
  let isMine = false
  await update($, refreshAtom, r => {
    // A run cut short by a reload never cleared its flag: past the script's own limit it is not running
    const isStuck = r.isRunning && (r.startedAt === null || now - r.startedAt > RUN_LIMIT_MS)
    isMine = !r.isRunning || isStuck
    return isMine ? { ...r, isRunning: true, startedAt: now, error: null } : r
  })
  if (!isMine) return
  // Every open session has its own timer: an automatic run steps aside while another session is counting
  const lock = await $.store.get('refreshLock')
  const lockedAt = lock && typeof lock === 'object' ? Number((lock as { at?: unknown }).at) : NaN
  if (!announce && Number.isFinite(lockedAt) && now - lockedAt < RUN_LIMIT_MS) {
    await update($, refreshAtom, r => ({ ...r, isRunning: false, startedAt: null }))
    return
  }
  await $.store.set('refreshLock', { at: now })
  try {
    const data = await runScript($)
    await $.store.set('data', data)
    await update($, dataAtom, () => data)
    await loadLive($).catch(() => null)
    await update($, refreshAtom, r => ({ ...r, isRunning: false, lastAt: now, error: null }))
    if (announce) $.ui.toast(STRINGS[(await read($, viewAtom)).lang].toastRefreshed)
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    await update($, refreshAtom, r => ({ ...r, isRunning: false, error: message }))
  } finally {
    await $.store.delete('refreshLock').catch(() => undefined)
  }
}

/** The timer's refresh: another open session may already have done it, so the kept data is checked first */
async function refreshIfStale($: E): Promise<void> {
  const kept = await $.store.get('data')
  const now = await $.clock.now()
  if (isUsageData(kept) && now - Date.parse(kept.generatedAt) < STALE_MS) {
    await update($, dataAtom, () => kept)
    await update($, refreshAtom, r => ({ ...r, error: null })) // fresh numbers: an old failure no longer applies
    return
  }
  await refreshAll($, false)
}

async function setView($: E, fn: (v: CalendarView) => CalendarView): Promise<void> {
  const before = (await read($, viewAtom)).lang
  await update($, viewAtom, fn)
  const view = await read($, viewAtom)
  await $.store.set('view', view)
  await showStatus($)
  if (view.lang !== before) {
    // The command menu and the pane's tab speak the new language too; an open pane is retitled in place
    await registerCommand($)
    if ((await $.ui.panes().catch(() => [])).some(p => p.id === PANE)) await openPane($)
  }
}

function summarize(days: DayRow[], nowMs: number, offsetMin: number) {
  const active = days.filter(d => d.messages > 0).sort((a, b) => (a.date < b.date ? -1 : 1))
  let longest = 0
  let run = 0
  let prev: number | null = null
  for (const d of active) {
    const t = Date.parse(`${d.date}T00:00:00Z`)
    run = prev !== null && t - prev === DAY ? run + 1 : 1
    longest = Math.max(longest, run)
    prev = t
  }
  const sum = (k: 'messages' | 'sessions' | 'tools' | 'tokens' | 'inputTokens' | 'outputTokens' | 'costUsd') =>
    active.reduce((s, d) => s + (Number(d[k]) || 0), 0)
  const top = active.reduce<DayRow | null>((a, d) => (!a || d.messages > a.messages ? d : a), null)

  // The streak still running counts back from today, or from yesterday before today's first use
  const activeSet = new Set(active.map(d => d.date))
  const now = localDate(nowMs, offsetMin)
  let day = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  if (!activeSet.has(new Date(day).toISOString().slice(0, 10))) day -= DAY
  let current = 0
  while (activeSet.has(new Date(day).toISOString().slice(0, 10))) {
    current += 1
    day -= DAY
  }

  const byModel = new Map<string, number>()
  const byMonth = new Map<string, number>()
  for (const d of active) {
    for (const [model, n] of Object.entries(d.models ?? (d.topModel ? { [d.topModel]: d.tokens } : {}))) {
      byModel.set(model, (byModel.get(model) ?? 0) + n)
    }
    const month = d.date.slice(0, 7)
    byMonth.set(month, (byMonth.get(month) ?? 0) + (Number(d.tokens) || 0))
  }
  const most = <K,>(m: Map<K, number>) =>
    [...m.entries()].reduce<[K, number] | null>((a, e) => (!a || e[1] > a[1] ? e : a), null)

  return {
    activeDays: active.length,
    messages: sum('messages'),
    sessions: sum('sessions'),
    tools: sum('tools'),
    tokens: sum('tokens'),
    inputTokens: sum('inputTokens'),
    outputTokens: sum('outputTokens'),
    costUsd: sum('costUsd'),
    isCostPartial: active.some(d => d.costUsd == null || d.isEstimated),
    unpriced: active.reduce((t, d) => t + (Number(d.unpricedTokens) || 0), 0),
    longest,
    current,
    top,
    topModel: most(byModel),
    topMonth: most(byMonth),
  }
}

// --- drawings (SVG markup) --------------------------------------------------

const SVG_TEXT = `font-family="system-ui, -apple-system, Segoe UI, sans-serif" font-size="10" fill="${MUTED}"`
const OPACITY = [0, 0.3, 0.55, 0.8, 1]
const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;')

function heatmapSvg(
  days: DayRow[],
  metric: Metric,
  weeks: number,
  nowMs: number,
  offsetMin: number,
  accent: string,
  S: Strings,
  lang: Lang,
): string {
  const unit = S.metrics[metric].unit
  const byDate = new Map(days.map(d => [d.date.slice(0, 10), d]))
  const value = (d: DayRow | undefined) => (d ? Number(d[metric]) || 0 : 0)
  const now = localDate(nowMs, offsetMin)
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  const weekday = (t: number) => (new Date(t).getUTCDay() + 6) % 7 // Monday = 0
  const start = heatmapStart(nowMs, offsetMin, weeks)

  // The scale is the shown weeks' own: one busy day long ago must not wash out the rest
  const first = new Date(start).toISOString().slice(0, 10)
  const max = days.reduce((m, d) => (d.date >= first ? Math.max(m, value(d)) : m), 0)
  const level = (v: number) => (v <= 0 || !max ? 0 : Math.min(4, Math.ceil((v / max) * 4)))

  const cell = 12
  const step = 15
  const left = 28
  const top = 16
  const width = left + weeks * step
  const height = top + 7 * step
  const parts: string[] = []

  ;[S.dayLabels[0], '', S.dayLabels[1], '', S.dayLabels[2], '', ''].forEach((name, i) => {
    if (name) parts.push(`<text x="0" y="${top + i * step + cell - 2}" ${SVG_TEXT}>${esc(name)}</text>`)
  })

  let lastLabel = -10
  for (let t = start; t <= today; t += DAY) {
    const d = new Date(t)
    const col = Math.floor((t - start) / DAY / 7)
    if ((d.getUTCDate() === 1 || t === start) && col - lastLabel >= 3 && col <= weeks - 2) {
      lastLabel = col
      parts.push(`<text x="${left + col * step}" y="${top - 5}" ${SVG_TEXT}>${esc(S.months[d.getUTCMonth()]!)}</text>`)
    }
    const key = d.toISOString().slice(0, 10)
    const v = value(byDate.get(key))
    const l = level(v)
    const fill = l ? `fill="${accent}" fill-opacity="${OPACITY[l]}"` : `fill="${MUTED}" fill-opacity="0.18"`
    const ring = t === today ? ` stroke="${MUTED}" stroke-width="1"` : ''
    const tip = `${fmtDay(key, S, lang, true)}: ${v ? `${fmtInt(v, S)} ${unit}` : S.noUsage}`
    parts.push(
      `<rect x="${left + col * step}" y="${top + weekday(t) * step}" width="${cell}" height="${cell}" rx="2" ${fill}${ring}><title>${esc(tip)}</title></rect>`,
    )
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${parts.join('')}</svg>`
}

const LEGEND = { width: 130, height: 13 }

function legendSvg(accent: string, S: Strings): string {
  const x0 = 30
  const cells = OPACITY.map((o, i) => {
    const fill = o ? `fill="${accent}" fill-opacity="${o}"` : `fill="${MUTED}" fill-opacity="0.18"`
    return `<rect x="${x0 + i * 14}" y="1" width="11" height="11" rx="2" ${fill}/>`
  }).join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${LEGEND.width}" height="${LEGEND.height}" viewBox="0 0 ${LEGEND.width} ${LEGEND.height}"><text x="${x0 - 4}" y="10" text-anchor="end" ${SVG_TEXT}>${esc(S.less)}</text>${cells}<text x="${x0 + 5 * 14 + 2}" y="10" ${SVG_TEXT}>${esc(S.more)}</text></svg>`
}

const METER = { width: 64, height: 6 }

function meterSvg(pct: number, accent: string): string {
  const { width: w, height: h } = METER
  // A sliver still shows as a dot
  const fillW = pct > 0 ? Math.max(h, (Math.min(100, pct) / 100) * w) : 0
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><rect width="${w}" height="${h}" rx="${h / 2}" fill="${MUTED}" fill-opacity="0.22"/><rect width="${fillW}" height="${h}" rx="${h / 2}" fill="${meterColor(pct, accent)}"/></svg>`
}

function hoursSvg(hours: HourRow[], accent: string, S: Strings): string {
  const width = 360
  const height = 130
  const left = 22
  const bottom = 16
  const max = Math.max(1, ...hours.map(h => h.prompts))
  const band = (width - left) / 24
  const scale = (v: number) => ((height - bottom - 6) * v) / max
  const parts: string[] = [
    `<line x1="${left}" x2="${width}" y1="${height - bottom}" y2="${height - bottom}" stroke="${MUTED}" stroke-opacity="0.5"/>`,
    `<text x="${left - 4}" y="${height - bottom - scale(max) + 4}" text-anchor="end" ${SVG_TEXT}>${fmtInt(max, S)}</text>`,
    `<text x="${left - 4}" y="${height - bottom + 3}" text-anchor="end" ${SVG_TEXT}>0</text>`,
  ]
  for (const h of hours) {
    const x = left + h.hour * band + band * 0.15
    const bh = scale(h.prompts)
    const tip = `${pad2(h.hour)}:00–${pad2((h.hour + 1) % 24)}:00: ${S.prompts(fmtInt(h.prompts, S))}`
    parts.push(
      `<rect x="${x}" y="${height - bottom - bh}" width="${band * 0.7}" height="${Math.max(bh, 0)}" rx="2" fill="${accent}"><title>${esc(tip)}</title></rect>`,
    )
    if (h.hour % 6 === 0 || h.hour === 23) {
      parts.push(`<text x="${x + band * 0.35}" y="${height - 3}" text-anchor="middle" ${SVG_TEXT}>${pad2(h.hour)}</text>`)
    }
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${parts.join('')}</svg>`
}

// Timers belong to this load of the module: a reload drops them (and this flag), so the next start arms them again
let isArmed = false

/** What a session with a window gets: live readings, refreshes, and the panel opened once */
async function startUi($: E): Promise<void> {
  if (!isArmed) {
    isArmed = true
    quietly(loadLive($))
    quietly(refreshIfStale($))
    $.clock.every(STALE_MS, () => quietly(refreshIfStale($)))
  }
  const ui = await read($, uiAtom)
  if (ui.started) return // a reload: the panel was opened before, and × may have closed it since
  await update($, uiAtom, u => ({ ...u, started: true }))
  if (!ui.closed) quietly(openPane($))
}

// --- hooks ----------------------------------------------------------------

export const register: Register = (on, options: PluginOptions) => {
  const webUrl = safeUrl(options.webUrl)
  const webTask = typeof options.webRefreshTask === 'string' ? options.webRefreshTask.trim() : ''
  on('session.start', async ($, e, next) => {
    const [view, data, limits] = await Promise.all([$.store.get('view'), $.store.get('data'), $.store.get('limits')])
    if (view && typeof view === 'object') {
      const saved = view as Partial<CalendarView>
      await update($, viewAtom, () => ({ ...DEFAULT_VIEW, ...saved, open: { ...DEFAULT_VIEW.open, ...saved.open } }))
    }
    await registerCommand($)
    if (isUsageData(data)) await update($, dataAtom, () => data)
    if (limits && typeof limits === 'object' && Array.isArray((limits as { rateLimits?: unknown }).rateLimits)) {
      const kept = limits as { rateLimits: LiveUsage['rateLimits']; at: number }
      await update($, liveAtom, () => ({
        rateLimits: kept.rateLimits,
        limitsAt: typeof kept.at === 'number' ? kept.at : null,
        limitsLive: false,
        contextTokens: null,
        contextWindow: null,
        contextPercent: null,
        at: kept.at,
      }))
    }
    // A fresh load starts with no refresh of its own running
    await update($, refreshAtom, r => ({ ...r, isRunning: false, startedAt: null }))

    // The terminal REPL starts with its window; the desktop app and other hosts start headless and
    // attach a window afterwards (session.attach). A -p run never does, so it never runs Python or opens a pane.
    const surfaces = await $.session.surfaces().catch(() => [])
    if (e.isInteractive || e.surface !== null || surfaces.length > 0) await startUi($).catch(() => undefined)

    return next(e)
  })

  on('session.attach', async ($, e, next) => {
    await startUi($).catch(() => undefined)

    return next(e)
  })

  on('ui.close', async ($, e, next) => {
    // × keeps the panel closed for the rest of this session, through reloads; /usage-calendar opens it again
    if (e.id === PANE && e.origin.kind === 'person') await update($, uiAtom, u => ({ ...u, closed: true }))

    return next(e)
  })

  on('command.run', { command: 'usage-calendar' }, async $ => {
    await update($, uiAtom, u => ({ ...u, started: true, closed: false }))
    await openPane($)

    return { text: STRINGS[(await read($, viewAtom)).lang].opened }
  })

  on('session.measure', async ($, e, next) => {
    await keepReading($, e, e.changed.includes('rateLimits')).catch(() => undefined)

    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const els = $.ui.resolve(e)
    const { Box, Text, Button, Link, Markdown } = els
    // The terminal's table carries no Svg: there each picture becomes its words
    const Svg = e.surface !== 'terminal' && 'Svg' in els ? els.Svg : null
    const data = await read($, dataAtom)
    const live = await read($, liveAtom)
    const view = await read($, viewAtom)
    const refresh = await read($, refreshAtom)
    const now = await $.clock.now()
    const lang = view.lang
    const S = STRINGS[lang]
    const accent = accentHex(view.accent)
    const offset = data?.utcOffsetMinutes ?? 0

    // Pictures with a size of their own stay that size; the rest fill the slot
    // Only pictures with tooltips get a frame of their own (isInteractive); the rest are plain images
    const picture = (source: string, alt: string, size?: { width: number; height: number }, hasTips = false) =>
      Svg ? (
        <Svg source={source} alt={alt} isInteractive={hasTips || undefined} width={size?.width} height={size?.height} />
      ) : (
        <Text dimColor>{alt}</Text>
      )

    const card = (id: string, title: string, note: string, description: string | null, body: () => JSX.Element) => (
      <Box key={`card-${id}`} flexDirection="column" gap="sm" borderStyle="round" borderDimColor padding="md">
        <Box flexDirection="row" justifyContent="space-between" alignItems="center" gap="sm">
          <Button key={`sec-${id}`} plain onPress={() => setView($, v => ({ ...v, open: { ...v.open, [id]: !v.open[id] } }))}>
            {/* ▾ and ▸ sit on the middle of the line */}
            <Text dimColor>{view.open[id] ? '▾  ' : '▸  '}</Text>
            <Text size="heading" weight="medium">{title}</Text>
          </Button>
          <Text dimColor size="caption">{note}</Text>
        </Box>
        {view.open[id] && description ? <Text dimColor size="caption">{description}</Text> : null}
        {view.open[id] ? body() : null}
      </Box>
    )

    // Table rows share column widths, so the columns line up
    const row = (key: string, cols: Col[], cells: (JSX.Element | string)[], isHead = false) => (
      <Box key={key} flexDirection="row" alignItems="center" paddingY={isHead ? 0 : 'xs'}>
        {cells.map((cell, i) => (
          <Box
            key={`${key}-${i}`}
            width={cols[i]?.width}
            flexDirection="row"
            alignItems="center"
            gap="sm"
            justifyContent={cols[i]?.align === 'right' ? 'flex-end' : 'flex-start'}
            paddingRight="sm"
          >
            {typeof cell === 'string' ? (
              <Text dimColor={isHead} size={isHead ? 'caption' : 'body'} tabular wrap="truncate-end">
                {cell}
              </Text>
            ) : (
              cell
            )}
          </Box>
        ))}
      </Box>
    )
    const gauge = (pct: number | null, alt: string) =>
      pct == null ? (
        <Text dimColor>—</Text>
      ) : (
        <Box flexDirection="row" alignItems="center" gap="sm">
          {picture(meterSvg(pct, accent), alt, METER)}
          <Text tabular color={pct >= 90 ? 'error' : pct >= 70 ? 'warning' : undefined}>{fmtPct(pct, S, lang)}</Text>
        </Box>
      )

    const header = (
      <Box flexDirection="row" justifyContent="space-between" alignItems="flex-start" gap="sm">
        <Box flexDirection="column" gap="xs">
          <Text size="heading" weight="semibold">{S.title}</Text>
          <Text dimColor size="caption">
            {data ? S.dataAsOf(fmtStamp(Date.parse(data.generatedAt), offset, S, lang)) : S.noData}
            {refresh.lastAt ? ` · ${S.refreshedAgo(fmtRel(refresh.lastAt - now, S, lang))}` : ''}
          </Text>
        </Box>
        <Button key="lang" label={S.langLabel} dimColor onPress={() => setView($, v => ({ ...v, lang: v.lang === 'en' ? 'tr' : 'en' }))}>
          {lang === 'en' ? 'TR' : 'EN'}
        </Button>
      </Box>
    )

    const actions = (
      <Box flexDirection="row" flexWrap="wrap" gap="sm" alignItems="center">
        <Button key="refresh" variant="primary" hotkey="r" onPress={() => refreshAll($, true)}>
          {refresh.isRunning ? S.refreshing : S.refresh}
        </Button>
        {webTask ? (
          <Button
            key="web"
            onPress={async () => {
              try {
                await $.prompt.submit({ text: S.webPrompt(webTask) })
                $.ui.toast(S.toastWeb)
              } catch {
                $.ui.toast(S.webFailed)
              }
            }}
          >
            {S.webUpdate}
          </Button>
        ) : null}
        {webUrl ? <Link href={webUrl} label={S.openWeb} /> : null}
      </Box>
    )
    const failure = refresh.error ? (
      <Text color="error">
        {refresh.error === NO_PYTHON
          ? S.noPython
          : refresh.error === BAD_OUTPUT
            ? S.badOutput
            : refresh.error === SCRIPT_MISSING
              ? S.scriptMissing
              : S.refreshFailed(
                  refresh.error.startsWith(EXIT_CODE) ? S.exitCode(refresh.error.slice(EXIT_CODE.length)) : refresh.error,
                )}
      </Text>
    ) : null

    if (!data) {
      return (
        <Box flexDirection="column" gap="md" padding="sm">
          {header}
          {actions}
          {failure}
          <Text dimColor>{refresh.isRunning ? S.loading : S.noData}</Text>
        </Box>
      )
    }

    const selfId = await $.session.id().catch(() => '')
    const s = summarize(data.days, now, offset)
    // What the heatmap shows, in words for a reader that can't see it
    const shown = (() => {
      const from = new Date(heatmapStart(now, offset, view.weeks)).toISOString().slice(0, 10)
      const inRange = data.days.filter(d => d.date >= from && (Number(d[view.metric]) || 0) > 0)
      const value = (d: DayRow) => Number(d[view.metric]) || 0
      return {
        total: inRange.reduce((t, d) => t + value(d), 0),
        activeDays: inRange.length,
        best: inRange.reduce<DayRow | null>((a, d) => (!a || value(d) > value(a) ? d : a), null),
      }
    })()
    // [label, value, line under it]
    const tiles: [string, string, string | null][] = [
      [S.tiles.activeDays, fmtInt(s.activeDays, S), null],
      [S.tiles.messages, fmtInt(s.messages, S), null],
      [S.tiles.sessions, fmtInt(s.sessions, S), null],
      [S.tiles.tools, fmtInt(s.tools, S), null],
      [S.tiles.tokens, fmtCompact(s.tokens, S), null],
      [S.tiles.topModel, s.topModel ? modelName(s.topModel[0]) : '—', s.topModel ? `${fmtCompact(s.topModel[1], S)} ${S.tokensUnit}` : null],
      [S.tiles.peakMonth, s.topMonth ? fmtMonth(s.topMonth[0], S) : '—', s.topMonth ? `${fmtCompact(s.topMonth[1], S)} ${S.tokensUnit}` : null],
      [S.tiles.longest, S.days(s.longest), S.current(s.current)],
    ]
    const tokenStats: [string, string][] = [
      [S.tokenStats[0], fmtCompact(s.inputTokens, S)],
      [S.tokenStats[1], fmtCompact(s.outputTokens, S)],
      [S.tokenStats[2], fmtCompact(s.tokens, S)],
      [S.tokenStats[3], fmtUsd(s.costUsd, S)],
    ]

    // Live once this session has a reading of its own; until then the one kept from an earlier session
    const limitRows = (live?.rateLimits ?? []).map(r => ({ name: S.limitNames[r.kind] ?? r.kind, pct: r.percentUsed, resetsAt: r.resetsAt }))
    const limitNote =
      limitRows.length === 0
        ? S.noReading
        : live?.limitsLive
          ? S.live
          : live?.limitsAt
            ? S.asOf(fmtStamp(live.limitsAt, offset, S, lang))
            : S.noReading

    // This session's row comes live from the engine; the script's copy of it is older
    const selfRow = data.sessions.find(r => r.session === selfId)
    const sessionRows = [
      ...(live && live.contextWindow
        ? [{
            id: selfId || 'self',
            title: selfRow?.title ?? S.thisSession,
            where: S.where[selfRow?.where ?? (e.surface === 'terminal' ? 'terminal' : 'desktop')],
            pct: live.contextPercent,
            tokens: live.contextTokens,
            lastActive: S.now,
            isLive: true,
          }]
        : []),
      ...data.sessions
        .filter(r => r.session !== selfId)
        .map(r => ({
          id: r.session,
          title: r.title ?? S.untitled,
          where: S.where[r.where] ?? r.where,
          pct: r.percentUsed,
          tokens: r.contextTokens as number | null,
          lastActive: fmtRel(Date.parse(r.lastActive) - now, S, lang),
          isLive: false,
        })),
    ]

    const daysTable = [
      `| ${S.daysHead.join(' | ')} |`,
      '|---|---:|---:|---:|---:|---:|---|',
      ...[...data.days]
        .sort((a, b) => (a.date < b.date ? 1 : -1))
        .map(
          d =>
            `| ${fmtDay(d.date, S, lang)} | ${fmtInt(d.messages, S)} | ${d.prompts == null ? '—' : fmtInt(d.prompts, S)} | ${fmtInt(d.sessions, S)} | ${fmtInt(d.tools, S)} | ${fmtCompact(d.tokens, S)} | ${d.topModel ? mdCell(modelName(d.topModel)) : '—'} |`,
        ),
    ].join('\n')

    const titles: Record<(typeof SECTION_IDS)[number], string> = S.sections

    return (
      <Box flexDirection="column" gap="md" padding="sm">
        {header}
        {actions}
        {failure}

        <Box flexDirection="row" flexWrap="wrap" gap="sm">
          {tiles.map(([label, value, sub]) => (
            <Box key={`tile-${label}`} flexDirection="column" borderStyle="round" borderDimColor paddingX="sm" paddingY="xs" minWidth={11}>
              <Text dimColor size="caption">{label}</Text>
              <Text size="heading" weight="medium" tabular>{value}</Text>
              {sub ? <Text dimColor size="caption" tabular>{sub}</Text> : null}
            </Box>
          ))}
        </Box>
        {s.top ? <Text dimColor size="caption">{S.busiest(fmtDay(s.top.date, S, lang), fmtInt(s.top.messages, S))}</Text> : null}

        <Box flexDirection="column" gap="sm" borderStyle="round" borderDimColor padding="md">
          <Box flexDirection="row" justifyContent="space-between" alignItems="center" gap="sm" flexWrap="wrap">
            <Text size="heading" weight="medium">{S.daily}</Text>
            <Box flexDirection="row" alignItems="center" gap="xs">
              <Text dimColor size="caption">{S.color}</Text>
              {ACCENTS.map(a => (
                <Button
                  key={`accent-${a.id}`}
                  label={`${S.color}: ${S.colorNames[a.id] ?? a.id}`}
                  plain
                  onPress={() => setView($, v => ({ ...v, accent: a.id }))}
                >
                  <Text color={a.hex}>{a.id === view.accent ? '◉' : '●'}</Text>
                </Button>
              ))}
            </Box>
          </Box>
          <Box flexDirection="row" flexWrap="wrap" gap="xs">
            {METRICS.map(m => (
              <Button
                key={`metric-${m}`}
                variant={m === view.metric ? 'primary' : 'secondary'}
                onPress={() => setView($, v => ({ ...v, metric: m }))}
              >
                {S.metrics[m].label}
              </Button>
            ))}
            <Button key="weeks" dimColor onPress={() => setView($, v => ({ ...v, weeks: v.weeks === 26 ? 53 : 26 }))}>
              {S.showMonths(view.weeks === 26 ? 12 : 6)}
            </Button>
          </Box>
          {picture(
            heatmapSvg(data.days, view.metric, view.weeks, now, offset, accent, S, lang),
            S.heatAlt(
              view.weeks === 26 ? 6 : 12,
              S.metrics[view.metric].unit,
              fmtInt(shown.total, S),
              shown.activeDays,
              shown.best ? fmtDay(shown.best.date, S, lang) : null,
            ),
            undefined,
            true,
          )}
          <Box flexDirection="row" justifyContent="space-between" alignItems="center">
            <Text dimColor size="caption">{S.hoverHint}</Text>
            {picture(legendSvg(accent, S), S.legendAlt, LEGEND)}
          </Box>
        </Box>

        {card('tokens', titles.tokens, S.allTime, S.tokensDesc(s.isCostPartial, s.unpriced > 0 ? fmtCompact(s.unpriced, S) : null), () => (
          <Box flexDirection="row" flexWrap="wrap" gap="md">
            {tokenStats.map(([label, value]) => (
              <Box key={`tok-${label}`} flexDirection="column" minWidth={11} flexGrow={1}>
                <Text dimColor size="caption">{label}</Text>
                <Text size="heading" weight="medium" tabular>{value}</Text>
              </Box>
            ))}
          </Box>
        ))}

        {card('limits', titles.limits, limitNote, S.limitsDesc, () =>
          limitRows.length === 0 ? (
            <Text dimColor>{S.noLimits}</Text>
          ) : (
            <Box flexDirection="column">
              {row('limits-head', LIMIT_COLS, S.limitsHead, true)}
              {limitRows.map(r =>
                row(`limit-${r.name}`, LIMIT_COLS, [
                  r.name,
                  gauge(r.pct, S.used(fmtDec(r.pct, S))),
                  r.resetsAt ? (Date.parse(r.resetsAt) > now ? fmtRel(Date.parse(r.resetsAt) - now, S, lang) : S.resetDone) : '—',
                ]),
              )}
            </Box>
          ),
        )}

        {card('sessions', titles.sessions, S.contextFill, S.sessionsDesc, () => (
          <Box flexDirection="column">
            {row('sess-head', SESSION_COLS, S.sessionsHead, true)}
            {sessionRows.map(r =>
              row(`sess-${r.id}`, SESSION_COLS, [
                r.isLive ? (
                  <Text wrap="truncate-end">
                    {r.title} <Text color={accent}>· {S.live}</Text>
                  </Text>
                ) : (
                  r.title
                ),
                r.where,
                gauge(r.pct, r.pct == null ? S.contextUnknown : S.contextAlt(fmtDec(r.pct, S))),
                r.tokens == null ? '—' : fmtInt(r.tokens, S),
                r.lastActive,
              ]),
            )}
            {sessionRows.length === 0 ? <Text dimColor>{S.noSessions}</Text> : null}
          </Box>
        ))}

        {card('hours', titles.hours, S.localTime, S.hoursDesc, () => picture(hoursSvg(data.hours, accent, S), S.hoursAlt, undefined, true))}

        {card('days', titles.days, S.days(s.activeDays), S.daysDesc, () => <Markdown text={daysTable} />)}

        <Text dimColor size="caption">{S.footer}</Text>
      </Box>
    )
  })
}
