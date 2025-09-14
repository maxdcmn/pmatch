'use client';

import { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Send } from 'lucide-react';
import { api, LLMResponse } from '@/lib/api';

type Message = {
  id: string;
  content: string;
  role: 'user' | 'ai';
  timestamp: Date;
  error?: boolean;
  contactData?: {
    text: string;
    email: string;
    subject: string;
  };
};

type ChatProps = {
  className?: string;
  onContactDataUpdate?: (data: { text: string; email: string; subject: string }) => void;
};

export function Chat({ className, onContactDataUpdate }: ChatProps) {
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
      const response: LLMResponse = await api.chatWithLLM(currentMessage);

      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: response.response,
        role: 'ai',
        timestamp: new Date(),
        contactData: response.metadata?.contact,
      };

      setMessages((prev) => [...prev, aiMessage]);
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
                          'max-w-[80%] px-3 py-2 text-sm break-words',
                          msg.role === 'user'
                            ? 'bg-primary text-primary-foreground ml-auto'
                            : msg.error
                              ? 'bg-destructive/10 text-destructive'
                              : 'bg-muted text-foreground',
                        )}
                      >
                        <div>{msg.content}</div>
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
