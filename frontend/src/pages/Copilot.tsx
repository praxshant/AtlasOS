import { useState, useRef, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getJson, authenticatedFetch } from '../api/client';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Bot, Send, User, Link as LinkIcon, AlertCircle, Loader2 } from 'lucide-react';

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
    <div className="flex flex-col h-[calc(100vh-6rem)]">
      <h2 className="text-xl font-semibold tracking-tight mb-4">AI Copilot</h2>

      <Card className="flex-1 flex flex-col overflow-hidden">
        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-5">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <Bot size={32} className="text-primary/40 mb-4" />
              <p className="text-sm text-on-surface-variant mb-6">Ask a question about your industrial knowledge base.</p>
              {suggestions.length > 0 && (
                <div className="flex flex-wrap gap-2 justify-center max-w-lg">
                  {suggestions.slice(0, 4).map((s: string, i: number) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(s)}
                      className="px-3 py-1.5 text-xs border border-outline-variant/50 rounded-lg text-on-surface-variant hover:text-primary hover:border-primary/50 transition-colors text-left"
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
                      <div className="space-y-4">
                        {parsed.summary && (
                          <div>
                            <p className="text-[10px] font-mono text-primary mb-1 uppercase tracking-wider">Summary</p>
                            <p className="whitespace-pre-wrap">{parsed.summary}</p>
                          </div>
                        )}
                        {parsed.evidence && parsed.evidence.length > 0 && (
                          <div>
                            <p className="text-[10px] font-mono text-primary mb-1 uppercase tracking-wider">Evidence</p>
                            <ul className="list-disc pl-4 space-y-1">
                              {parsed.evidence.map((e: any, i: number) => (
                                <li key={i}>{e}</li>
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
                <div className="w-7 h-7 rounded-md bg-surface-variant flex items-center justify-center shrink-0 mt-0.5">
                  <User size={14} className="text-on-surface-variant" />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Input */}
        <div className="p-3 border-t border-outline-variant/30">
          <div className="relative flex items-center">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendMessage(input)}
              placeholder="Ask about assets, procedures, compliance..."
              className="w-full h-10 bg-surface-container border border-outline-variant/50 rounded-lg pl-3 pr-10 text-sm text-on-surface focus:outline-none focus:border-primary transition-colors placeholder:text-on-surface-variant/50"
              disabled={streaming}
            />
            <button
              onClick={() => sendMessage(input)}
              disabled={!input.trim() || streaming}
              className="absolute right-1.5 p-1.5 bg-primary text-on-primary rounded-md hover:bg-primary/90 transition-colors disabled:opacity-40"
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}
