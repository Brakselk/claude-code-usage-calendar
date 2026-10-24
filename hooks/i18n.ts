import type { Lang, Metric } from '../types'

// Everything the panel says, in English and Turkish. Number and date shapes live here too,
// so a third language is one more entry.
export type Strings = {
  title: string
  dataAsOf: (when: string) => string
  noData: string
  refreshedAgo: (rel: string) => string
  refresh: string
  refreshing: string
  webUpdate: string
  openWeb: string
  refreshFailed: (why: string) => string
  noPython: string
  toastRefreshed: string
  toastWeb: string
  webPrompt: (task: string) => string
  color: string
  tiles: {
    activeDays: string
    messages: string
    sessions: string
    tools: string
    tokens: string
    topModel: string
    peakMonth: string
    longest: string
  }
  tokensUnit: string
  days: (n: number) => string
  current: (n: number) => string
  busiest: (day: string, n: string) => string
  daily: string
  metrics: Record<Metric, { label: string; unit: string }>
  showMonths: (n: number) => string
  heatAlt: (months: number, unit: string) => string
  hoverHint: string
  legendAlt: string
  less: string
  more: string
  noUsage: string
  sections: { limits: string; sessions: string; hours: string; days: string; tokens: string }
  live: string
  asOf: (when: string) => string
  noReading: string
  limitsDesc: string
  limitsHead: [string, string, string]
  limitNames: Record<string, string>
  resetDone: string
  noLimits: string
  used: (pct: string) => string
  contextFill: string
  sessionsDesc: string
  sessionsHead: [string, string, string, string, string]
  where: Record<'desktop' | 'terminal', string>
  now: string
  thisSession: string
  untitled: string
  noSessions: string
  contextAlt: (pct: string) => string
  contextUnknown: string
  localTime: string
  hoursDesc: string
  hoursAlt: string
  prompts: (n: string) => string
  daysDesc: string
  daysHead: string[]
  allTime: string
  tokenStats: [string, string, string, string]
  tokensDesc: (partial: boolean) => string
  footer: string
  months: string[]
  monthsLong: string[]
  weekdays: string[]
  dayLabels: [string, string, string]
  // number shapes
  group: string
  decimal: string
  compact: [string, string, string]
  rel: (text: string, isFuture: boolean) => string
  units: { min: string; hour: string; day: string }
  loading: string
  statusHint: string
  statusLimits: Record<string, string>
}

export const STRINGS: Record<Lang, Strings> = {
  en: {
    title: 'Claude Code Usage Calendar',
    dataAsOf: w => `Data as of ${w}`,
    noData: 'No data yet: press Refresh',
    refreshedAgo: r => `refreshed ${r}`,
    refresh: 'Refresh',
    refreshing: 'Refreshing…',
    webUpdate: 'Update web too',
    openWeb: 'Open on web',
    refreshFailed: w => `Refresh failed: ${w}`,
    noPython: 'Python 3 was not found. Install it from python.org, then press Refresh.',
    toastRefreshed: 'Calendar refreshed',
    toastWeb: 'Web update requested',
    webPrompt: t =>
      `Update the web version of the Claude Code Usage Calendar: run the scheduled task "${t}" with mcp__scheduled-tasks__run_scheduled_task (load it with ToolSearch if needed). Don't wait for it to finish; say in one line that it started.`,
    color: 'Color',
    tiles: {
      activeDays: 'Active days',
      messages: 'Messages',
      sessions: 'Sessions',
      tools: 'Tool calls',
      tokens: 'Tokens',
      topModel: 'Most used model',
      peakMonth: 'Peak month',
      longest: 'Longest streak',
    },
    tokensUnit: 'tokens',
    days: n => `${n} ${n === 1 ? 'day' : 'days'}`,
    current: n => `Current: ${n} ${n === 1 ? 'day' : 'days'}`,
    busiest: (d, n) => `Busiest day ${d}: ${n} messages`,
    daily: 'Daily activity',
    metrics: {
      messages: { label: 'Messages', unit: 'messages' },
      prompts: { label: 'Prompts', unit: 'prompts' },
      sessions: { label: 'Sessions', unit: 'sessions' },
      tools: { label: 'Tools', unit: 'tool calls' },
      tokens: { label: 'Tokens', unit: 'tokens' },
    },
    showMonths: n => `Show ${n} months`,
    heatAlt: (m, u) => `Daily ${u} over the last ${m} months`,
    hoverHint: 'Hover a square to see that day',
    legendAlt: 'Color scale from less to more',
    less: 'Less',
    more: 'More',
    noUsage: 'no usage',
    sections: { limits: 'Usage limits', sessions: 'Active sessions', hours: 'Time of day', days: 'Active days', tokens: 'Token details' },
    live: 'live',
    asOf: w => `as of ${w}`,
    noReading: 'no reading yet',
    limitsDesc: "How much of your plan's 5-hour and weekly limits is used.",
    limitsHead: ['Limit', 'Used', 'Resets'],
    limitNames: { five_hour: '5-hour limit', seven_day: 'Weekly · all models' },
    resetDone: 'Reset',
    noLimits: 'No reading yet; it arrives with the first reply in this session.',
    used: p => `${p}% used`,
    contextFill: 'Context window fill',
    sessionsDesc:
      'Sessions used in the last 24 hours or still open in the desktop app. Fill is how much of the context window the last reply saw; auto-compact starts at 97%.',
    sessionsHead: ['Session', 'Where', 'Context', 'Tokens', 'Last active'],
    where: { desktop: 'Desktop', terminal: 'Terminal' },
    now: 'now',
    thisSession: 'This session',
    untitled: 'Untitled session',
    noSessions: 'No sessions in the last 24 hours.',
    contextAlt: p => `Context ${p}% full`,
    contextUnknown: 'Context unknown',
    localTime: 'local time',
    hoursDesc: 'Your prompts by hour of day',
    hoursAlt: 'Prompts by hour of day',
    prompts: n => `${n} prompts`,
    daysDesc: 'Every day with usage, newest first',
    daysHead: ['Date', 'Messages', 'Prompts', 'Sessions', 'Tools', 'Tokens', 'Model'],
    allTime: 'all time',
    tokenStats: ['Input tokens', 'Output tokens', 'Total tokens', 'Est. cost'],
    tokensDesc: p =>
      `Estimated at API list prices; subscription plans don't bill this.${p ? ' Days whose transcripts were deleted are split from their totals.' : ''}`,
    footer: 'Only Claude Code sessions on this computer. claude.ai chats are not included.',
    months: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
    monthsLong: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
    weekdays: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
    dayLabels: ['Mon', 'Wed', 'Fri'],
    group: ',',
    decimal: '.',
    compact: ['K', 'M', 'B'],
    rel: (t, f) => (f ? `in ${t}` : `${t} ago`),
    units: { min: 'm', hour: 'h', day: 'd' },
    loading: 'Reading usage data…',
    statusHint: 'Usage Calendar: /usage-calendar',
    statusLimits: { five_hour: '5h', seven_day: 'week' },
  },
  tr: {
    title: 'Claude Code Kullanım Takvimi',
    dataAsOf: w => `Veriler ${w} itibarıyla`,
    noData: "Henüz veri yok: Yenile'ye bas",
    refreshedAgo: r => `panelden yenilendi ${r}`,
    refresh: 'Yenile',
    refreshing: 'Yenileniyor…',
    webUpdate: "Web'i de güncelle",
    openWeb: "Web'de aç",
    refreshFailed: w => `Yenilenemedi: ${w}`,
    noPython: "Python 3 bulunamadı. python.org'dan kurup Yenile'ye bas.",
    toastRefreshed: 'Takvim yenilendi',
    toastWeb: 'Web güncellemesi istendi',
    webPrompt: t =>
      `Claude Code Kullanım Takvimi'nin web sürümünü güncelle: mcp__scheduled-tasks__run_scheduled_task aracıyla "${t}" görevini çalıştır (gerekirse ToolSearch ile yükle). Bitmesini bekleme, başlatıldığını tek satırla söyle.`,
    color: 'Renk',
    tiles: {
      activeDays: 'Aktif gün',
      messages: 'Mesaj',
      sessions: 'Oturum',
      tools: 'Araç çağrısı',
      tokens: 'Token',
      topModel: 'En çok kullanılan model',
      peakMonth: 'En yoğun ay',
      longest: 'En uzun seri',
    },
    tokensUnit: 'token',
    days: n => `${n} gün`,
    current: n => `Şu anki: ${n} gün`,
    busiest: (d, n) => `En yoğun gün ${d}: ${n} mesaj`,
    daily: 'Günlük aktivite',
    metrics: {
      messages: { label: 'Mesaj', unit: 'mesaj' },
      prompts: { label: 'İstem', unit: 'istem' },
      sessions: { label: 'Oturum', unit: 'oturum' },
      tools: { label: 'Araç', unit: 'araç çağrısı' },
      tokens: { label: 'Token', unit: 'token' },
    },
    showMonths: n => `${n} ayı göster`,
    heatAlt: (m, u) => `Son ${m} ayda günlük ${u} sayısı`,
    hoverHint: 'Kareye gelince günün sayısı görünür',
    legendAlt: 'Az ile çok arası renk ölçeği',
    less: 'Az',
    more: 'Çok',
    noUsage: 'kullanım yok',
    sections: { limits: 'Kullanım limitleri', sessions: 'Aktif oturumlar', hours: 'Günün hangi saatinde', days: 'Aktif günler', tokens: 'Token detayları' },
    live: 'canlı',
    asOf: w => `${w} itibarıyla`,
    noReading: 'henüz okuma yok',
    limitsDesc: 'Planının 5 saatlik ve haftalık limitlerinden ne kadarı kullanılmış.',
    limitsHead: ['Limit', 'Kullanılan', 'Sıfırlanma'],
    limitNames: { five_hour: '5 saatlik limit', seven_day: 'Haftalık · tüm modeller' },
    resetDone: 'Sıfırlandı',
    noLimits: 'Henüz limit bilgisi yok; bu oturumdaki ilk yanıtla gelir.',
    used: p => `%${p} kullanıldı`,
    contextFill: 'Bağlam penceresi doluluğu',
    sessionsDesc:
      "Son 24 saatte kullanılan ya da uygulamada arşivlenmemiş oturumlar. Doluluk, son yanıtın gördüğü bağlamın pencereye oranı; %97'de otomatik özetleme başlar.",
    sessionsHead: ['Oturum', 'Nerede', 'Bağlam', 'Token', 'Son etkinlik'],
    where: { desktop: 'Masaüstü', terminal: 'Terminal' },
    now: 'şimdi',
    thisSession: 'Bu oturum',
    untitled: 'Adsız oturum',
    noSessions: 'Son 24 saatte oturum yok.',
    contextAlt: p => `Bağlam %${p} dolu`,
    contextUnknown: 'Bağlam bilinmiyor',
    localTime: 'yerel saat',
    hoursDesc: 'Yazdığın istemlerin saate göre dağılımı',
    hoursAlt: 'Saate göre istem sayısı',
    prompts: n => `${n} istem`,
    daysDesc: 'Kullanım olan her gün, en yenisi üstte',
    daysHead: ['Tarih', 'Mesaj', 'İstem', 'Oturum', 'Araç', 'Token', 'Model'],
    allTime: 'tüm kayıtlar',
    tokenStats: ['Giriş token', 'Çıkış token', 'Toplam token', 'Tahmini maliyet'],
    tokensDesc: p =>
      `Tahmini maliyet API liste fiyatlarıyla hesaplandı; abonelik planlarında ayrıca ödenmez.${p ? ' Dökümü silinmiş günlerin dağılımı toplamdan tahmin edildi.' : ''}`,
    footer: 'Yalnızca bu bilgisayardaki Claude Code oturumları. claude.ai sohbetleri dahil değil.',
    months: ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'],
    monthsLong: ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'],
    weekdays: ['Pazar', 'Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'],
    dayLabels: ['Pzt', 'Çar', 'Cum'],
    group: '.',
    decimal: ',',
    compact: ['B', 'Mn', 'Mr'],
    rel: (t, f) => `${t} ${f ? 'sonra' : 'önce'}`,
    units: { min: 'dk', hour: 'sa', day: 'gün' },
    loading: 'Kullanım verileri okunuyor…',
    statusHint: 'Kullanım Takvimi: /usage-calendar',
    statusLimits: { five_hour: '5 saat', seven_day: 'haftalık' },
  },
}
