'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { ExternalLink, Save } from 'lucide-react';

type ContactProps = {
  className?: string;
};

export function Contact({ className }: ContactProps) {
  const [recipient, setRecipient] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');

  const handleOpenInMail = () => {
    const encodedRecipient = encodeURIComponent(recipient);
    const encodedSubject = encodeURIComponent(subject);
    const encodedBody = encodeURIComponent(body);
    const mailtoLink = `mailto:${encodedRecipient}?subject=${encodedSubject}&body=${encodedBody}`;
    window.open(mailtoLink, '_self');
  };

  const handleSaveToTemplates = () => {
    console.log('Saving to templates:', { recipient, subject, body });
  };

  return (
    <div className={cn('bg-card flex h-full flex-col', className)}>
      <div className="px-6 pt-6 pb-4">
        <h2 className="text-2xl">Contact Proposal</h2>
        <p className="text-muted-foreground font-mono text-xs tracking-wider uppercase">
          Draft your proposal
        </p>
      </div>

      <div className="flex-1 px-6 pb-6">
        <div className="bg-accent border-border flex h-full flex-col overflow-hidden rounded-sm border">
          <div className="border-border flex items-center border-b">
            <span className="text-foreground px-3 py-2 text-sm select-none">To:</span>
            <input
              type="email"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              placeholder="Enter recipient email address"
              className={cn(
                'flex-1 bg-transparent pr-4',
                'placeholder:text-muted-foreground text-foreground',
                'focus:outline-none',
                'text-sm',
                'border-none',
              )}
            />
          </div>

          <div className="border-border flex items-center border-b">
            <span className="text-foreground px-3 py-2 text-sm select-none">Subject:</span>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Enter your proposal subject"
              className={cn(
                'flex-1 bg-transparent py-2 pr-4',
                'placeholder:text-muted-foreground text-foreground',
                'focus:outline-none',
                'text-sm',
                'border-none',
              )}
            />
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Compose your proposal message here"
              className={cn(
                'w-full flex-1 resize-none bg-transparent px-3 py-2',
                'placeholder:text-muted-foreground text-foreground',
                'focus:outline-none',
                'text-sm leading-relaxed',
                'border-none',
                'overflow-y-auto',
              )}
            />

            <div className="relative h-14">
              <div className="absolute right-2 bottom-2 flex items-center gap-2">
                <button
                  onClick={handleSaveToTemplates}
                  className={cn(
                    'group flex cursor-pointer items-center gap-0 rounded-sm hover:gap-2',
                    'bg-background text-foreground',
                    'hover:bg-accent/30 transition-all duration-300 ease-out',
                    'border-border border text-sm font-medium',
                    'px-2.5 py-2 hover:px-4 hover:py-2',
                  )}
                >
                  <Save size={16} className="flex-shrink-0" />
                  <span className="max-w-0 overflow-hidden whitespace-nowrap transition-all duration-300 ease-out group-hover:max-w-[120px]">
                    To Templates
                  </span>
                </button>

                <button
                  onClick={handleOpenInMail}
                  className={cn(
                    'group flex cursor-pointer items-center gap-0 rounded-sm hover:gap-2',
                    'bg-primary text-primary-foreground',
                    'hover:bg-primary/90 transition-all duration-300 ease-out',
                    'border-primary/20 border text-sm font-medium',
                    'px-2.5 py-2 hover:px-4 hover:py-2',
                  )}
                >
                  <ExternalLink size={16} className="flex-shrink-0" />
                  <span className="max-w-0 overflow-hidden whitespace-nowrap transition-all duration-300 ease-out group-hover:max-w-[120px]">
                    Open in Mail
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
