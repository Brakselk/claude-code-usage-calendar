export type Metric = 'messages' | 'prompts' | 'sessions' | 'tools' | 'tokens'
export type Lang = 'en' | 'tr'

export type DayRow = {
  date: string
  messages: number
  prompts: number | null
  sessions: number
  tools: number
  tokens: number
  topModel: string | null
  /** All input the model read: uncached, cache writes and cache reads */
  inputTokens?: number
  outputTokens?: number
  /** At API list prices; a subscription does not bill it */
  costUsd?: number
  models?: Record<string, number>
  isEstimated?: boolean
}

export type HourRow = { hour: number; prompts: number }

export type SessionRow = {
  session: string
  title: string | null
  where: 'desktop' | 'terminal'
  model: string
  contextTokens: number
  contextWindow: number | null
  percentUsed: number | null
  lastActive: string
}

/** What scripts/collect_usage.py --json prints */
export type UsageData = {
  generatedAt: string
  today: string
  utcOffsetMinutes: number
  days: DayRow[]
  hours: HourRow[]
  sessions: SessionRow[]
}

export type LiveLimit = { kind: string; percentUsed: number; resetsAt: string | null }

export type LiveUsage = {
  rateLimits: LiveLimit[]
  contextTokens: number | null
  contextWindow: number | null
  contextPercent: number | null
  at: number
}

export type CalendarView = {
  metric: Metric
  weeks: number
  lang: Lang
  accent: string
  open: Record<string, boolean>
}

export type RefreshState = {
  isRunning: boolean
  lastAt: number | null
  error: string | null
}

declare module 'claude-code' {
  interface PluginState {
    'token-garden': {
      data: UsageData | null
      live: LiveUsage | null
      view: CalendarView
      refresh: RefreshState
      /** Whether the panel is open, so the band above the prompt can offer to reopen it */
      paneOpen: boolean
    }
  }
}
