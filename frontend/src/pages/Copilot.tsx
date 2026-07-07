import { useState, useRef, useCallback, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getJson, authenticatedFetch } from '../api/client';
import { 
  Bot, Send, User, Link as LinkIcon, AlertCircle, 
  Loader2, ShieldCheck, ListTree, Lightbulb, Activity, Network, FileText, Trash2
} from 'lucide-react';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  citations?: any[];
  graph?: any;
}

export function Copilot() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Load history on mount
  useEffect(() => {
    const saved = localStorage.getItem('copilot_history');
    if (saved) {
      try {
        setMessages(JSON.parse(saved));
      } catch (e) {
        console.error("Failed to load chat history", e);
      }
    }
  }, []);

  // Save history on change
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem('copilot_history', JSON.stringify(messages));
    }
  }, [messages]);

  const clearHistory = () => {
    setMessages([]);
    localStorage.removeItem('copilot_history');
  };

  const { data: suggestionsData } = useQuery({
    queryKey: ['copilot-suggestions'],
    queryFn: () => getJson<any>('/copilot/suggestions'),
  });

  const suggestions = suggestionsData?.suggestions || [];

  const sendMessage = useCallback(async (query: string) => {
    if (!query.trim() || streaming) return;
    const userMsg: Message = { role: 'user', content: query };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setStreaming(true);

    const assistantMsg: Message = { role: 'assistant', content: '', citations: [], graph: null };
    setMessages((prev) => [...prev, assistantMsg]);

    try {
      const res = await authenticatedFetch('/copilot/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, history: messages.map((m) => ({ role: m.role, content: m.content })) }),
      });

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'token') {
                setMessages((prev) => {
                  const copy = [...prev];
                  const last = copy[copy.length - 1];
                  copy[copy.length - 1] = { ...last, content: last.content + data.content };
                  return copy;
                });
              } else if (data.type === 'citations') {
                setMessages((prev) => {
                  const copy = [...prev];
                  copy[copy.length - 1] = { ...copy[copy.length - 1], citations: data.citations };
                  return copy;
                });
              } else if (data.type === 'graph') {
                setMessages((prev) => {
                  const copy = [...prev];
                  copy[copy.length - 1] = { ...copy[copy.length - 1], graph: data.graph };
                  return copy;
                });
              }
            } catch {
              // skip malformed SSE
            }
          }
          scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
        }
      }
    } catch (err: any) {
      setMessages((prev) => {
        const copy = [...prev];
        copy[copy.length - 1] = { ...copy[copy.length - 1], content: `Error: ${err.message || 'Failed to reach Copilot'}` };
        return copy;
      });
    }
    setStreaming(false);
  }, [messages, streaming]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - var(--space-16))' }}>
      {/* Page Header */}
      <div className="page-header">
        <div>
          <h1>AI Copilot</h1>
          <p className="page-subtitle">Query your industrial knowledge base</p>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-3)', alignItems: 'center' }}>
          {messages.length > 0 && (
            <button 
              onClick={clearHistory}
              style={{
                display: 'flex', alignItems: 'center', gap: '4px',
                background: 'none', border: '1px solid var(--border-default)', 
                color: 'var(--text-secondary)', padding: '6px 12px',
                borderRadius: '6px', cursor: 'pointer', fontSize: '12px'
              }}
            >
              <Trash2 size={14} /> Clear Chat
            </button>
          )}
          <span className="badge badge-info">GraphRAG-powered</span>
        </div>
      </div>

      <div className="card" style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 0 }}>
        {/* Messages */}
        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: 'var(--space-5)', display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
          {messages.length === 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', textAlign: 'center' }}>
              <Bot size={32} style={{ color: 'var(--accent)', opacity: 0.4, marginBottom: 'var(--space-4)' }} />
              <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-tertiary)', marginBottom: 'var(--space-6)' }}>Ask a question about your industrial knowledge base.</p>
              {suggestions.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--space-2)', justifyContent: 'center', maxWidth: 520 }}>
                  {suggestions.slice(0, 4).map((s: string, i: number) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(s)}
                      style={{
                        padding: '6px 12px',
                        fontSize: 'var(--text-xs)',
                        border: '1px solid var(--border-default)',
                        borderRadius: 5,
                        background: 'none',
                        color: 'var(--text-secondary)',
                        cursor: 'pointer',
                        transition: 'color 0.12s, border-color 0.12s',
                        textAlign: 'left',
                      }}
                      onMouseEnter={e => { (e.currentTarget).style.color = 'var(--accent)'; (e.currentTarget).style.borderColor = 'var(--border-accent)'; }}
                      onMouseLeave={e => { (e.currentTarget).style.color = 'var(--text-secondary)'; (e.currentTarget).style.borderColor = 'var(--border-default)'; }}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
              {msg.role === 'assistant' && (
                <div className="w-7 h-7 rounded-md bg-primary/20 flex items-center justify-center shrink-0 border border-primary/30 mt-0.5">
                  <Bot size={14} className="text-primary" />
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-xl p-3 text-sm leading-relaxed ${msg.role === 'user' ? 'bg-surface-variant/50 rounded-tr-sm' : 'bg-surface-container rounded-tl-sm border border-outline-variant/30'}`}
              >
                {(() => {
                  const normalizeCopilotAnswer = (answer: string) => {
                    try {
                      return JSON.parse(answer);
                    } catch {
                      return null;
                    }
                  };
                  const parsed = msg.role === 'assistant' ? normalizeCopilotAnswer(msg.content) : null;
                  
                  if (parsed) {
                    return (
                      <div className="space-y-6">
                        {/* Confidence Score Header */}
                        {parsed.confidence !== undefined && (
                          <div className="flex items-center gap-3 bg-surface border border-outline-variant/30 p-2 rounded-lg">
                            <div className={`flex items-center justify-center w-10 h-10 rounded-full shrink-0 ${
                              parsed.confidence >= 80 ? 'bg-green-500/20 text-green-500' :
                              parsed.confidence >= 50 ? 'bg-yellow-500/20 text-yellow-500' :
                              'bg-red-500/20 text-red-500'
                            }`}>
                              <Activity size={18} />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-sm">Confidence: {parsed.confidence}%</span>
                              </div>
                              {parsed.confidence_basis && (
                                <p className="text-[11px] text-on-surface-variant truncate">{parsed.confidence_basis}</p>
                              )}
                            </div>
                          </div>
                        )}
                        
                        {/* Summary */}
                        {parsed.summary && (
                          <div className="bg-primary/5 border border-primary/20 p-3 rounded-lg">
                            <div className="flex items-center gap-2 mb-2 text-primary">
                              <Bot size={14} />
                              <p className="text-[11px] font-mono uppercase tracking-wider font-semibold">AI Synthesis</p>
                            </div>
                            <p className="whitespace-pre-wrap text-[13px]">{parsed.summary}</p>
                          </div>
                        )}
                        
                        {/* Missing Knowledge / Risks */}
                        {parsed.missing_knowledge && parsed.missing_knowledge.length > 0 && (
                          <div className="bg-red-500/5 border border-red-500/20 p-3 rounded-lg">
                            <div className="flex items-center gap-2 mb-2 text-red-500">
                              <AlertCircle size={14} />
                              <p className="text-[11px] font-mono uppercase tracking-wider font-semibold">Knowledge Gaps</p>
                            </div>
                            <ul className="list-disc pl-4 space-y-1 text-red-400 text-[12px]">
                              {parsed.missing_knowledge.map((e: any, i: number) => <li key={i}>{e}</li>)}
                            </ul>
                          </div>
                        )}
                        
                        {/* Reasoning Chain Timeline */}
                        {parsed.reasoning_chain && parsed.reasoning_chain.length > 0 && (
                          <div>
                            <div className="flex items-center gap-2 mb-2 text-on-surface-variant">
                              <ListTree size={14} />
                              <p className="text-[11px] font-mono uppercase tracking-wider font-semibold">Reasoning Path</p>
                            </div>
                            <div className="pl-2 border-l-2 border-outline-variant/30 space-y-3 ml-1">
                              {parsed.reasoning_chain.map((step: string, i: number) => (
                                <div key={i} className="relative">
                                  <div className="absolute w-2 h-2 bg-surface-variant border border-outline-variant/50 rounded-full -left-[13px] top-1.5" />
                                  <p className="text-[12px] text-on-surface-variant pl-2 leading-relaxed">{step}</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Graph Evidence */}
                        {parsed.graph_evidence && parsed.graph_evidence.length > 0 && (
                          <div>
                            <div className="flex items-center gap-2 mb-2 text-primary">
                              <Network size={14} />
                              <p className="text-[11px] font-mono uppercase tracking-wider font-semibold">Graph Topology Evidence</p>
                            </div>
                            <div className="space-y-2">
                              {parsed.graph_evidence.map((edge: any, i: number) => (
                                <div key={i} className="flex flex-wrap items-center gap-1.5 text-[11px] bg-surface-variant/30 p-2 rounded border border-outline-variant/30">
                                  <span className="font-semibold text-primary">{edge.entity}</span>
                                  <span className="text-on-surface-variant">──[{edge.relationship}]──&gt;</span>
                                  <span className="font-semibold">{edge.connected_to}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Text Evidence */}
                        {parsed.evidence && parsed.evidence.length > 0 && (
                          <div>
                            <div className="flex items-center gap-2 mb-2 text-on-surface-variant">
                              <FileText size={14} />
                              <p className="text-[11px] font-mono uppercase tracking-wider font-semibold">Extracted Excerpts</p>
                            </div>
                            <div className="space-y-2">
                              {parsed.evidence.map((e: any, i: number) => (
                                <div key={i} className="bg-surface-variant/30 p-2 rounded border border-outline-variant/30">
                                  <p className="text-[11px] text-on-surface-variant/70 mb-1">From: {e.source} (Page {e.page})</p>
                                  <p className="text-[12px] italic border-l-2 border-primary/30 pl-2">"{e.excerpt}"</p>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        
                        {/* Recommendations */}
                        {parsed.recommendations && parsed.recommendations.length > 0 && (
                          <div>
                            <div className="flex items-center gap-2 mb-2 text-green-500">
                              <Lightbulb size={14} />
                              <p className="text-[11px] font-mono uppercase tracking-wider font-semibold">Actionable Insights</p>
                            </div>
                            <ul className="space-y-2">
                              {parsed.recommendations.map((r: string, i: number) => (
                                <li key={i} className="flex gap-2 text-[13px] bg-green-500/5 border border-green-500/20 p-2 rounded">
                                  <ShieldCheck size={14} className="text-green-500 mt-0.5 shrink-0" />
                                  <span>{r}</span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}

                      </div>
                    );
                  }
                  return <p className="whitespace-pre-wrap">{msg.content}</p>;
                })()}

                {msg.role === 'assistant' && streaming && i === messages.length - 1 && !msg.content && (
                  <Loader2 size={14} className="animate-spin text-primary mt-2" />
                )}

                {/* Citations */}
                {msg.citations && msg.citations.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-outline-variant/30">
                    <p className="text-[10px] font-mono text-on-surface-variant mb-1.5">SOURCES</p>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.citations.map((c: any, ci: number) => (
                        <span key={ci} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-variant/50 text-[10px] border border-outline-variant/30">
                          <LinkIcon size={10} className="text-primary" />
                          {c.source || c.filename || `Source ${ci + 1}`}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Graph paths */}
                {msg.graph && msg.graph.paths && msg.graph.paths.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-outline-variant/30">
                    <p className="text-[10px] font-mono text-on-surface-variant mb-1.5">GRAPH PATHS</p>
                    <div className="space-y-1">
                      {msg.graph.paths.slice(0, 5).map((path: string, pi: number) => (
                        <p key={pi} className="text-[10px] font-mono text-on-surface-variant">{path}</p>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              {msg.role === 'user' && (
                <div style={{ width: 28, height: 28, borderRadius: 6, background: 'var(--bg-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 2 }}>
                  <User size={14} style={{ color: 'var(--text-tertiary)' }} />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Input */}
        <div style={{ padding: 'var(--space-3)', borderTop: '1px solid var(--border-default)' }}>
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendMessage(input)}
              placeholder="Ask about assets, procedures, compliance..."
              style={{
                width: '100%',
                height: 40,
                background: 'var(--bg-subtle)',
                border: '1px solid var(--border-default)',
                borderRadius: 5,
                paddingLeft: 'var(--space-3)',
                paddingRight: 44,
                fontSize: 'var(--text-sm)',
                color: 'var(--text-primary)',
                outline: 'none',
                boxSizing: 'border-box',
              }}
              onFocus={e => (e.target.style.borderColor = 'var(--accent)')}
              onBlur={e => (e.target.style.borderColor = 'var(--border-default)')}
              disabled={streaming}
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={!input.trim() || streaming}
              style={{
                position: 'absolute', right: 6,
                padding: 'var(--space-1)',
                background: 'var(--accent)',
                color: '#fff',
                border: 'none',
                borderRadius: 4,
                cursor: !input.trim() || streaming ? 'not-allowed' : 'pointer',
                opacity: !input.trim() || streaming ? 0.4 : 1,
                display: 'flex', alignItems: 'center',
              }}
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
