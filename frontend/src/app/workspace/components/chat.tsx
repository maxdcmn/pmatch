'use client';

import { useState, useRef, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { Send } from 'lucide-react';

type Message = {
  id: string;
  content: string;
  role: 'user' | 'ai';
  timestamp: Date;
};

type ChatProps = {
  className?: string;
};

export function Chat({ className }: ChatProps) {
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
    setMessage('');
    setIsLoading(true);

    setTimeout(() => {
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: "I'm a simulated response. Replace this with your actual LLM integration.",
        role: 'ai',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, aiMessage]);
      setIsLoading(false);
    }, 1000);
  };

  return (
    <div className={cn('bg-card flex h-full flex-col', className)}>
      <div className="flex min-h-0 flex-1 flex-col p-6">
        <div className="bg-accent border-border flex h-full flex-col overflow-hidden rounded-sm border">
          <div className="min-h-0 flex-1">
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
                          'max-w-[80%] rounded-lg px-3 py-2 text-sm break-words',
                          msg.role === 'user'
                            ? 'bg-primary text-primary-foreground ml-auto'
                            : 'bg-muted text-foreground',
                        )}
                      >
                        {msg.content}
                      </div>
                    </div>
                  ))}
                  {isLoading && (
                    <div className="flex justify-start">
                      <div className="bg-muted text-foreground rounded-lg px-3 py-2 text-sm">
                        <span className="animate-pulse">Thinking...</span>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>
          </div>

          <div className="border-border border-t"></div>

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
  );
}
