export interface AgentCard {
  name: string
  role: string
  version: string
  capabilities: string[]
  server_url: string
}

export interface AgentStatus {
  name: string
  role: string
  tools: number
  tasks: { task_count: number; tasks: Record<string, unknown> }
  memory: { vector_count: number; embedding_model: string }
  subordinates: number
}

export interface SSEEvent {
  type: string
  task_id: string
  data: Record<string, unknown>
  timestamp: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  thoughts?: string
  toolCalls?: ToolCall[]
  timestamp: number
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
  result?: string
  isError?: boolean
  status: 'pending' | 'running' | 'done' | 'error'
}

export type ToolIcons = Record<string, string>
