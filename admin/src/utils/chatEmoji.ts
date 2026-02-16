const KEYWORD_MAP: [string, string][] = [
  ['тест', '🧪'],
  ['бот', '🤖'],
  ['заказ', '📦'],
  ['оплат', '💳'],
  ['помощь', '🆘'],
  ['привет', '👋'],
  ['ошибк', '🐛'],
  ['настрой', '⚙️'],
  ['виджет', '🔧'],
  ['продаж', '💰'],
  ['клиент', '👤'],
  ['вопрос', '❓'],
  ['обучен', '📚'],
  ['голос', '🎙️'],
  ['telegram', '✈️'],
  ['whatsapp', '💬'],
  ['новый', '✨'],
  ['new', '✨'],
]

const FALLBACK_EMOJIS = ['💬', '📝', '🗂️', '📌', '🔹', '🟢', '🔵', '🟣', '⭐', '🌐']

function simpleHash(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

export function getChatEmoji(title: string | undefined | null): string {
  if (!title) return '💬'
  const lower = title.toLowerCase()
  for (const [keyword, emoji] of KEYWORD_MAP) {
    if (lower.includes(keyword)) return emoji
  }
  return FALLBACK_EMOJIS[simpleHash(title) % FALLBACK_EMOJIS.length]
}
