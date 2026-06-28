const API_BASE = '/api'

export async function startSearch(question, maxTurns = 5, concurrency = 1) {
  const res = await fetch(`${API_BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, max_turns: maxTurns, concurrency: concurrency }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export function connectSSE(taskId, onEvent, onError, onDone) {
  const source = new EventSource(`${API_BASE}/stream/${taskId}`)

  source.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      if (data.done) {
        onDone?.(data)
        source.close()
      } else {
        onEvent?.(data)
      }
    } catch { /* ignore parse errors */ }
  }

  source.addEventListener('error', (e) => {
    onError?.(e)
    source.close()
  })

  return () => source.close()
}

export async function getResult(taskId) {
  const res = await fetch(`${API_BASE}/result/${taskId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ── 历史记录 API ──
export async function fetchHistory() {
  const res = await fetch(`${API_BASE}/history`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchHistoryResult(taskId) {
  const res = await fetch(`${API_BASE}/history/${taskId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchProcessLog(taskId) {
  const res = await fetch(`${API_BASE}/process/${taskId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

// ── 评估 API ──
export async function fetchEvalSummary() {
  const res = await fetch(`${API_BASE}/eval/summary`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchEvalTask(taskId) {
  const res = await fetch(`${API_BASE}/eval/task/${taskId}`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchEvalTasks() {
  const res = await fetch(`${API_BASE}/eval/tasks`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
