export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8001'

export type Role = 'employee' | 'support_agent' | 'admin'
export type LoginResult = { access_token: string; role: Role; display_name: string }
export type Citation = { document_id: string; title: string; excerpt: string; score: number }
export type ChatResult = {
  session_id: string
  status: string
  intent: string
  reply: string
  confidence: number
  citations: Citation[]
  requires_confirmation: boolean
  pending_action?: { tool: string; description: string }
  ticket_id?: string
  resolved: boolean
  deflected: boolean
}

export async function request<T>(path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response.json()
}
