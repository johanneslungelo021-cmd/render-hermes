import type { ToolIcons } from './types'

export const TOOL_ICONS: ToolIcons = {
  memory_search: '🔍',
  memory_store: '💾',
  bash: '⌨️',
  python: '🐍',
  delegate: '📤',
  list_subordinates: '📋',
  read_file: '📄',
  cat: '🐱',
  browser: '🌐',
  skill: '📚',
}

export function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ')
}

export function escapeHtml(text: string): string {
  const d = document.createElement('div')
  d.textContent = text
  return d.innerHTML
}

// Simple markdown renderer for when react-markdown isn't available
export function renderMarkdown(text: string): string {
  if (!text) return ''
  let html = escapeHtml(text)
  // Code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, _lang, code) => {
    return `<pre><code>${escapeHtml(code)}</code></pre>`
  })
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  // Italic
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" class="text-[var(--accent)] hover:underline">$1</a>')
  // Line breaks
  html = html.replace(/\n/g, '<br>')
  return html
}

export function classNames(...classes: (string | undefined | null | false)[]): string {
  return classes.filter(Boolean).join(' ')
}
