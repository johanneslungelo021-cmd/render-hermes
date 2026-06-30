import type { AgentCard, AgentStatus, Message, ToolCall } from './types'

const A2A_BASE = '/a2a'

export async function fetchAgentCard(): Promise<AgentCard> {
  const r = await fetch('/.well-known/agent.json')
  return r.json()
}

export async function fetchStatus(): Promise<AgentStatus> {
  const r = await fetch(`${A2A_BASE}/status`)
  return r.json()
}

export function streamChat(
  message: string,
  onEvent: (event: { type: string; data: Record<string, unknown> }) => void,
  onError: (error: string) => void,
  onDone: () => void,
  signal?: AbortSignal,
): { abort: () => void } {
  const controller = new AbortController()
  const combinedSignal = signal
    ? combineSignals(signal, controller.signal)
    : controller.signal

  fetch(`${A2A_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal: combinedSignal,
  })
    .then(async (r) => {
      if (!r.ok) {
        onError(`Server error: ${r.status}`)
        return
      }
      const reader = r.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6).trim()
          if (!payload) continue
          try {
            const ev = JSON.parse(payload)
            onEvent(ev)
            if (ev.type === 'done') onDone()
            if (ev.type === 'error') onError(ev.data?.message || ev.data?.text || 'Unknown error')
          } catch {
            // skip malformed events
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message)
      }
    })

  return { abort: () => controller.abort() }
}

function combineSignals(...signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController()
  for (const sig of signals) {
    if (sig.aborted) {
      controller.abort(sig.reason)
      return controller.signal
    }
    sig.addEventListener('abort', () => controller.abort(sig.reason), { once: true })
  }
  return controller.signal
}

export function buildMessageFromStream(
  textDeltas: string[],
  thoughtDeltas: string[],
  toolCalls: ToolCall[],
): Pick<Message, 'content' | 'thoughts' | 'toolCalls'> {
  return {
    content: textDeltas.join(''),
    thoughts: thoughtDeltas.join(''),
    toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
  }
}
