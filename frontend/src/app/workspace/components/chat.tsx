'use client';

import { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Send } from 'lucide-react';
import { api, LLMResponse } from '@/lib/api';
import ReactMarkdown from 'react-markdown';

type Contact = {
  email: string;
  name: string;
  institution?: string;
  country?: string;
  title?: string;
  research_area?: string;
  profile_url?: string;
  abstracts?: string[];
  similarity_score?: number;
};

type Message = {
  id: string;
  content: string;
  role: 'user' | 'ai';
  timestamp: Date;
  error?: boolean;
  contacts?: Contact[];
  contactData?: {
    text: string;
    email: string;
    subject: string;
  };
};

type ChatProps = {
  className?: string;
  onContactDataUpdate?: (data: { text: string; email: string; subject: string }, contacts?: Contact[]) => void;
  userId?: string | null;
};

export function Chat({ className, onContactDataUpdate, userId }: ChatProps) {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!message.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      content: message.trim(),
      role: 'user',
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    const currentMessage = message.trim();
    setMessage('');
    setIsLoading(true);

    try {
      const response: LLMResponse = await api.chatWithLLM(currentMessage, userId || undefined);

      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: response.response,
        role: 'ai',
        timestamp: new Date(),
        contacts: response.contacts,
        contactData: response.metadata?.contact,
      };

      setMessages((prev) => [...prev, aiMessage]);
      
      // Handle contacts - send to contact form
      if (response.contacts && response.contacts.length > 0) {
        const contactEmails = response.contacts.map(c => c.email).join(', ');
        const contactNames = response.contacts.map(c => c.name).join(', ');
        
        onContactDataUpdate?.({
          text: `Found ${response.contacts.length} researcher(s): ${contactNames}`,
          email: contactEmails,
          subject: `Research Collaboration Inquiry - ${response.contacts[0]?.research_area || 'Academic Collaboration'}`
        }, response.contacts);
      }

      if (response.metadata?.contact) {
        onContactDataUpdate?.(response.metadata.contact);
      }
    } catch (error) {
      console.error('Chat API error:', error);

      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: `Error: ${error instanceof Error ? error.message : 'Failed to get response'}`,
        role: 'ai',
        timestamp: new Date(),
        error: true,
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={cn('bg-card flex h-full flex-col', className)}>
      <div className="flex min-h-0 flex-1 flex-col p-6">
        <div className="flex h-full flex-col overflow-hidden">
          <div className="bg-accent min-h-0 flex-1">
            <div className="h-full overflow-y-auto p-3">
              {messages.length === 0 ? (
                <div className="flex h-full items-center justify-center">
                  <p className="text-muted-foreground text-center text-sm">
                    Who would you like to reach out to?
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {messages.map((msg) => (
                    <div
                      key={msg.id}
                      className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}
                    >
                      <div
                        className={cn(
                          'max-w-[80%] px-3 py-2 text-sm break-words rounded-lg',
                          msg.role === 'user'
                            ? 'bg-primary text-primary-foreground ml-auto rounded-br-sm'
                            : msg.error
                              ? 'bg-destructive/10 text-destructive rounded-bl-sm'
                              : 'bg-muted text-foreground rounded-bl-sm',
                        )}
                      >
                        {msg.role === 'ai' ? (
                          <div className="prose prose-sm max-w-none prose-headings:font-semibold prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground prose-ul:text-foreground prose-ol:text-foreground prose-li:text-foreground prose-blockquote:text-muted-foreground prose-blockquote:border-l-border">
                            <ReactMarkdown 
                              components={{
                                h1: (props) => <h1 className="text-lg font-semibold mb-2 text-foreground" {...props} />,
                                h2: (props) => <h2 className="text-base font-semibold mb-2 text-foreground" {...props} />,
                                h3: (props) => <h3 className="text-sm font-semibold mb-1 text-foreground" {...props} />,
                                p: (props) => <p className="mb-2 last:mb-0 text-foreground" {...props} />,
                                ul: (props) => <ul className="mb-2 ml-4 space-y-1 text-foreground" {...props} />,
                                ol: (props) => <ol className="mb-2 ml-4 space-y-1 text-foreground" {...props} />,
                                li: (props) => <li className="text-foreground" {...props} />,
                                strong: (props) => <strong className="font-semibold text-foreground" {...props} />,
                                em: (props) => <em className="italic text-foreground" {...props} />,
                                blockquote: (props) => <blockquote className="border-l-2 border-border pl-3 text-muted-foreground italic" {...props} />,
                                code: (props) => (
                                  <code className="bg-muted px-1 py-0.5 rounded text-sm font-mono text-foreground" {...props} />
                                ),
                              }}
                            >
                              {msg.content}
                            </ReactMarkdown>
                          </div>
                        ) : (
                          <div>{msg.content}</div>
                        )}
                        {msg.contactData && (
                          <div className="text-muted-foreground mt-1 text-[11px] italic">
                            Changed contact
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                  {isLoading && (
                    <div className="flex justify-start">
                      <div className="bg-muted text-foreground px-3 py-2 text-sm">
                        <span className="animate-pulse">Thinking...</span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>
          </div>

          <div className="bg-accent mt-2 border-2 border-transparent transition-colors focus-within:border-emerald-600 dark:focus-within:border-emerald-400">
            <form onSubmit={handleSubmit} className="flex flex-shrink-0 items-center px-3 py-2">
              <input
                type="text"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Ask anything"
                className="text-foreground placeholder:text-muted-foreground flex-1 border-none bg-transparent text-sm outline-none"
                disabled={isLoading}
              />
              <button
                type="submit"
                disabled={!message.trim() || isLoading}
                className="text-muted-foreground hover:text-foreground ml-2 cursor-pointer p-1 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Send size={16} />
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
