import { useState, useCallback, useRef, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import ChatPanel from './features/chat/ChatPanel'
import type { Message, ToolCall } from './lib/types'
import { streamChat, buildMessageFromStream, fetchStatus, fetchAgentCard } from './lib/api'

let messageIdCounter = 0
function nextId() {
  return `msg_${++messageIdCounter}`
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [agentName, setAgentName] = useState('pi-agent')
  const [toolCount, setToolCount] = useState(10)
  const [memoryCount, setMemoryCount] = useState(0)
  const [taskCount, setTaskCount] = useState(0)
  const abortRef = useRef<(() => void) | null>(null)

  // Load agent info on mount
  useEffect(() => {
    fetchAgentCard().then(card => {
      setAgentName(card.name)
      setToolCount(card.capabilities.length)
    }).catch(() => {})
    fetchStatus().then(s => {
      setMemoryCount(s.memory?.vector_count ?? 0)
      setTaskCount(s.tasks?.task_count ?? 0)
    }).catch(() => {})
  }, [])

  // Refresh stats periodically
  useEffect(() => {
    const interval = setInterval(() => {
      fetchStatus().then(s => {
        setMemoryCount(s.memory?.vector_count ?? 0)
        setTaskCount(s.tasks?.task_count ?? 0)
      }).catch(() => {})
    }, 10000)
    return () => clearInterval(interval)
  }, [])

  const handleSend = useCallback((text: string) => {
    if (!text.trim() || isProcessing) return

    const userMsg: Message = {
      id: nextId(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg])
    setIsProcessing(true)

    // Create placeholder assistant message
    const assistantId = nextId()
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      thoughts: '',
      toolCalls: [],
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, assistantMsg])

    const textDeltas: string[] = []
    const thoughtDeltas: string[] = []
    const toolCalls: ToolCall[] = []

    const stream = streamChat(
      text,
      (event) => {
        const { type, data } = event
        if (type === 'text_delta' || type === 'text') {
          const delta = (data.delta as string) || (data.text as string) || ''
          if (delta) {
            textDeltas.push(delta)
            updateMessage(assistantId, {
              content: textDeltas.join(''),
              thoughts: thoughtDeltas.join('') || undefined,
              toolCalls: toolCalls.length > 0 ? [...toolCalls] : undefined,
            })
          }
        } else if (type === 'thought_delta') {
          const delta = (data.delta as string) || ''
          if (delta) {
            thoughtDeltas.push(delta)
            updateMessage(assistantId, {
              thoughts: thoughtDeltas.join(''),
              toolCalls: toolCalls.length > 0 ? [...toolCalls] : undefined,
            })
          }
        } else if (type === 'tool_call') {
          const tc: ToolCall = {
            id: (data.tool_call_id as string) || `tc_${toolCalls.length}`,
            name: data.tool_name as string,
            arguments: data.arguments as Record<string, unknown>,
            status: 'running',
          }
          toolCalls.push(tc)
          updateMessage(assistantId, { toolCalls: [...toolCalls] })
        } else if (type === 'tool_result') {
          const tcId = data.tool_call_id as string
          const found = toolCalls.find(t => t.id === tcId)
          if (found) {
            found.result = data.output as string
            found.isError = (data.is_error as boolean) || false
            found.status = found.isError ? 'error' : 'done'
            updateMessage(assistantId, { toolCalls: [...toolCalls] })
          }
        }
      },
      (error) => {
        updateMessage(assistantId, { content: `Error: ${error}` })
        setIsProcessing(false)
      },
      () => {
        setIsProcessing(false)
      },
    )

    abortRef.current = stream.abort

    function updateMessage(id: string, updates: Partial<Message>) {
      setMessages(prev => prev.map(m => (m.id === id ? { ...m, ...updates } : m)))
    }
  }, [isProcessing])

  const handleAbort = useCallback(() => {
    abortRef.current?.()
    setIsProcessing(false)
  }, [])

  const handleNewSession = useCallback(() => {
    abortRef.current?.()
    setMessages([])
    setIsProcessing(false)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-primary)]">
      <Sidebar
        agentName={agentName}
        toolCount={toolCount}
        memoryCount={memoryCount}
        taskCount={taskCount}
        onNewSession={handleNewSession}
      />
      <ChatPanel
        messages={messages}
        onSend={handleSend}
        onAbort={handleAbort}
        isProcessing={isProcessing}
      />
    </div>
  )
}
