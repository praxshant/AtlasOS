'use client';

import React, { useState, useRef, useEffect } from 'react';
import { authenticatedFetch } from '../utils/api';

interface Citation {
  id: number;
  filename: string;
  page: number;
  snippet: string;
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
}

interface ChatInterfaceProps {
  onCitationsChange?: (citations: Citation[]) => void;
  onGraphChange?: (graph: any) => void;
}

export default function ChatInterface({ onCitationsChange, onGraphChange }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: 'Hello, I am the ATLASOS Expert Copilot. Ask me any questions about plant equipment, failures, maintenance history, or safety compliance logs.'
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const historyRef = useRef<any[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom of chat
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userText = input;
    setInput('');
    setLoading(true);

    // Append user message
    const updatedMessages = [...messages, { role: 'user', content: userText } as Message];
    setMessages(updatedMessages);

    // Add assistant placeholder
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    abortControllerRef.current = new AbortController();

    try {
      const response = await authenticatedFetch('/api/copilot/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortControllerRef.current.signal,
        body: JSON.stringify({
          query: userText,
          history: historyRef.current
        })
      });

      if (!response.ok) {
        throw new Error(`Server returned HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let assistantText = '';
      let currentCitations: Citation[] = [];

      if (!reader) {
        throw new Error('Readable stream not supported.');
      }

      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        
        // Keep the last partial line in the buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          const cleanLine = line.trim();
          if (!cleanLine.startsWith('data: ')) continue;
          
          const rawData = cleanLine.substring(6);
          if (!rawData) continue;

          try {
            const data = JSON.parse(rawData);
            
            if (data.status === 'thinking') {
              // Just visual state
            } else if (data.status === 'done') {
              setLoading(false);
            } else if (data.error) {
              assistantText += `\n[Error: ${data.error}]`;
            } else if (data.citations) {
              currentCitations = data.citations;
              if (onCitationsChange) {
                onCitationsChange(data.citations);
              }
            } else if (data.graph) {
              if (onGraphChange) {
                onGraphChange(data.graph);
              }
            } else if (data.token) {
              assistantText += data.token;
              // Update last message
              setMessages(prev => {
                const copy = [...prev];
                const last = copy[copy.length - 1];
                last.content = assistantText;
                last.citations = currentCitations;
                return copy;
              });
            }
          } catch (e) {
            // Partial JSON or unparseable line, ignore and wait for next chunks
          }
        }
      }

      // Save to chat history
      historyRef.current = [
        ...historyRef.current,
        { role: 'user', content: userText },
        { role: 'assistant', content: assistantText }
      ];

    } catch (error: any) {
      console.error(error);
      if (error.name === 'AbortError') {
        // If aborted, just leave the message as is and stop loading
        setLoading(false);
        return;
      }
      setMessages(prev => {
        const copy = [...prev];
        const last = copy[copy.length - 1];
        last.content = `AtlasOS couldn't generate a response.\n\nPossible reasons:\n• AI provider unavailable\n• Network issue\n\n[Technical Details: ${error.message || error}]`;
        return copy;
      });
      setLoading(false);
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  return (
    <div className="chat-window">
      <div className="chat-history">
        {messages.map((msg, index) => (
          <div key={index} className={`chat-message ${msg.role}`}>
            <div className="avatar">
              {msg.role === 'user' ? 'U' : 'AI'}
            </div>
            <div>
              <div className="bubble">
                <div style={{ whiteSpace: 'pre-wrap' }}>
                  {msg.content || (loading && index === messages.length - 1 && (
                    <div className="thinking-dots">
                      <span></span>
                      <span></span>
                      <span></span>
                    </div>
                  ))}
                </div>
                
                {msg.citations && msg.citations.length > 0 && (
                  <div className="chat-citations">
                    {msg.citations.map(cit => (
                      <span 
                        key={cit.id} 
                        className="citation-badge" 
                        title="Click to view extracted snippet"
                        onClick={() => alert(`Source: ${cit.filename} (Page ${cit.page})\n\nExtracted Snippet:\n"...${cit.snippet}..."`)}
                        style={{ cursor: 'pointer', textDecoration: 'underline' }}
                      >
                        [{cit.id}] {cit.filename} (Page {cit.page})
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSend} className="chat-input-bar">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask expert copilot (e.g. 'What caused pump P-104 failures?')..."
          className="form-input"
          disabled={loading}
        />
        <button type="submit" className="btn btn-primary" disabled={loading || !input.trim()}>
          Send
        </button>
        {loading && (
          <button type="button" onClick={handleStop} className="btn btn-secondary" style={{ marginLeft: '0.5rem', background: 'var(--accent-red)', color: 'white', border: 'none' }}>
            Stop
          </button>
        )}
      </form>
    </div>
  );
}
