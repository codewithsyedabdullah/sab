import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface ToolEvent {
  name: string
  arguments: Record<string, unknown>
  output?: string
}

function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [sessionId, setSessionId] = useState('')
  const [provider, setProvider] = useState('ollama')
  const [model, setModel] = useState('codellama:13b')
  const [apiKey, setApiKey] = useState('')
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const currentAssistant = useRef('')

  useEffect(() => {
    connectWebSocket()
    return () => wsRef.current?.close()
  }, [])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, toolEvents])

  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/chat`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      ws.send(JSON.stringify({
        type: 'config',
        provider,
        model,
        api_key: apiKey,
      }))
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'session') {
        setSessionId(data.session_id)
        return
      }

      if (data.type === 'content') {
        currentAssistant.current += data.text
        setMessages(prev => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last && last.role === 'assistant') {
            last.content = currentAssistant.current
          } else {
            updated.push({ role: 'assistant', content: currentAssistant.current })
          }
          return [...updated]
        })
        return
      }

      if (data.type === 'tool_start') {
        setToolEvents(prev => [...prev, {
          name: data.name,
          arguments: data.arguments,
        }])
        return
      }

      if (data.type === 'tool_result') {
        setToolEvents(prev => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last && last.name === data.name && !last.output) {
            last.output = data.output
          }
          return [...updated]
        })
        return
      }

      if (data.type === 'done') {
        setIsStreaming(false)
        currentAssistant.current = ''
        return
      }

      if (data.type === 'error') {
        setIsStreaming(false)
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `Error: ${data.message}`,
        }])
        return
      }
    }

    ws.onclose = () => {
      setConnected(false)
      setTimeout(connectWebSocket, 2000)
    }

    ws.onerror = () => setConnected(false)
  }

  function sendMessage() {
    if (!input.trim() || isStreaming || !wsRef.current) return

    const userMsg = input.trim()
    setInput('')
    setToolEvents([])
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setIsStreaming(true)
    currentAssistant.current = ''

    wsRef.current.send(JSON.stringify({
      type: 'chat',
      message: userMsg,
    }))
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  function newSession() {
    setMessages([])
    setToolEvents([])
    setSessionId('')
    currentAssistant.current = ''
    wsRef.current?.send(JSON.stringify({ type: 'reset' }))
  }

  function updateConfig() {
    wsRef.current?.send(JSON.stringify({
      type: 'config',
      provider,
      model,
      api_key: apiKey,
      session_id: sessionId,
    }))
  }

  return (
    <>
      <div className="header">
        <h1>SAB</h1>
        <div className="status">{connected ? 'Connected' : 'Disconnected'}</div>
      </div>

      <div className="settings-bar">
        <select value={provider} onChange={e => setProvider(e.target.value)}>
          <option value="ollama">Ollama (Local)</option>
          <option value="anthropic">Claude (API)</option>
          <option value="openai">GPT (API)</option>
        </select>
        <input
          type="text"
          value={model}
          onChange={e => setModel(e.target.value)}
          placeholder="Model"
          style={{ width: 200 }}
        />
        {(provider === 'anthropic' || provider === 'openai') && (
          <input
            type="password"
            value={apiKey}
            onChange={e => setApiKey(e.target.value)}
            placeholder="API Key"
            style={{ width: 220 }}
          />
        )}
        <button onClick={updateConfig}>Apply</button>
        <button onClick={newSession} style={{ background: 'var(--red)' }}>New Chat</button>
      </div>

      <div className="chat-area">
        {messages.length === 0 && (
          <div className="welcome">
            <h2>SAB</h2>
            <p>Open-source coding agent. Ask me to write code, fix bugs, search files, or run commands.</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            {msg.role === 'assistant' ? (
              <ReactMarkdown>{msg.content}</ReactMarkdown>
            ) : (
              msg.content
            )}
          </div>
        ))}

        {toolEvents.map((tool, i) => (
          <div key={`tool-${i}`} className="tool-message">
            <div className="tool-name">{tool.name}()</div>
            {tool.output && (
              <div className="tool-output">{tool.output.slice(0, 500)}{tool.output.length > 500 ? '...' : ''}</div>
            )}
          </div>
        ))}

        {isStreaming && (
          <div className="typing">
            <span></span><span></span><span></span>
          </div>
        )}

        <div ref={chatEndRef} />
      </div>

      <div className="input-area">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask SAB anything..."
          rows={1}
        />
        <button onClick={sendMessage} disabled={isStreaming || !input.trim()}>
          {isStreaming ? 'Working...' : 'Send'}
        </button>
      </div>
    </>
  )
}

export default App
