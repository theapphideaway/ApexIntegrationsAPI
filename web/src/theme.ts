// Light / dark theme. Stored per browser; defaults to the OS preference.
export type Theme = 'light' | 'dark'
const KEY = 'docuflow_theme'

export function getTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* private mode */ }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t
  try { localStorage.setItem(KEY, t) } catch { /* ignore */ }
}

/** Call once at startup so the first paint is already the right theme. */
export function initTheme() { document.documentElement.dataset.theme = getTheme() }
