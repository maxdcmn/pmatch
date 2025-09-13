'use client';

import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { ExternalLink, Save, Check, X } from 'lucide-react';
import InlineDiffResolver from '@/app/workspace/components/inline-diff-resolver';

type ContactData = {
  text: string;
  email: string;
  subject: string;
};

type ContactProps = {
  className?: string;
  incomingContactData?: ContactData | null;
  onContactDataUpdate?: (data: ContactData) => void;
};

export function Contact({ className, incomingContactData, onContactDataUpdate }: ContactProps) {
  const [recipient, setRecipient] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [pendingChanges, setPendingChanges] = useState<ContactData | null>(null);
  type FieldStatus = 'unchanged' | 'pending' | 'applied' | 'dismissed';
  const [status, setStatus] = useState<{
    email: FieldStatus;
    subject: FieldStatus;
    text: FieldStatus;
  }>({ email: 'unchanged', subject: 'unchanged', text: 'unchanged' });

  // Handle incoming contact data updates
  useEffect(() => {
    if (incomingContactData) {
      setPendingChanges(incomingContactData);
      setStatus({
        email: recipient !== incomingContactData.email ? 'pending' : 'unchanged',
        subject: subject !== incomingContactData.subject ? 'pending' : 'unchanged',
        text: body !== incomingContactData.text ? 'pending' : 'unchanged',
      });
    }
  }, [incomingContactData]);

  const resolveIfDone = (nextStatus: {
    email: FieldStatus;
    subject: FieldStatus;
    text: FieldStatus;
  }) => {
    const anyPending = Object.values(nextStatus).some((s) => s === 'pending');
    if (!anyPending) {
      setPendingChanges(null);
    }
  };

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

  // Global accept/decline controls
  const acceptAll = () => {
    if (!pendingChanges) return;
    setRecipient(pendingChanges.email);
    setSubject(pendingChanges.subject);
    setBody(pendingChanges.text);
    setStatus({ email: 'applied', subject: 'applied', text: 'applied' });
    onContactDataUpdate?.(pendingChanges);
    setPendingChanges(null);
  };

  const declineAll = () => {
    if (!pendingChanges) return;
    setStatus({ email: 'dismissed', subject: 'dismissed', text: 'dismissed' });
    setPendingChanges(null);
  };

  // (legacy in-file diff resolver removed; using shared InlineDiffResolver)

  return (
    <div className={cn('bg-card flex h-full flex-col', className)}>
      <div className="px-6 pt-6 pb-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl">Contact Proposal</h2>
            <p className="text-muted-foreground font-mono text-xs tracking-wider uppercase">
              Draft your proposal
            </p>
          </div>
          {pendingChanges && (
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={acceptAll}
                className="inline-flex items-center rounded border border-green-600/40 px-2 py-1 text-[11px] font-medium text-green-700 hover:bg-green-500/10"
              >
                <Check size={12} className="mr-1" /> Accept All
              </button>
              <button
                type="button"
                onClick={declineAll}
                className="inline-flex items-center rounded border border-red-600/40 px-2 py-1 text-[11px] font-medium text-red-700 hover:bg-red-500/10"
              >
                <X size={12} className="mr-1" /> Decline All
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 px-6 pb-6">
        <div className="bg-accent border-border flex h-full flex-col overflow-hidden rounded-sm border">
          <div className="border-border flex items-center border-b">
            <span className="text-foreground px-3 py-2 text-sm select-none">To:</span>
            {pendingChanges && status.email === 'pending' ? (
              <div className="flex-1 bg-transparent py-2 pr-4 text-sm">
                <InlineDiffResolver
                  key={`email-${recipient}|${pendingChanges.email}`}
                  before={recipient}
                  after={pendingChanges.email}
                  onChange={(merged, allResolved) => {
                    setRecipient(merged);
                    setStatus((prev) => {
                      let nextState: FieldStatus = 'pending';
                      if (allResolved) {
                        nextState = merged === pendingChanges.email ? 'applied' : 'dismissed';
                      }
                      const next = { ...prev, email: nextState } as typeof prev;
                      if (nextState !== 'pending') resolveIfDone(next);
                      return next;
                    });
                  }}
                />
              </div>
            ) : (
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
            )}
          </div>

          <div className="border-border flex items-center border-b">
            <span className="text-foreground px-3 py-2 text-sm select-none">Subject:</span>
            {pendingChanges && status.subject === 'pending' ? (
              <div className="flex-1 bg-transparent py-2 pr-4 text-sm">
                <InlineDiffResolver
                  key={`subject-${subject}|${pendingChanges.subject}`}
                  before={subject}
                  after={pendingChanges.subject}
                  onChange={(merged, allResolved) => {
                    setSubject(merged);
                    setStatus((prev) => {
                      let nextState: FieldStatus = 'pending';
                      if (allResolved) {
                        nextState = merged === pendingChanges.subject ? 'applied' : 'dismissed';
                      }
                      const next = { ...prev, subject: nextState } as typeof prev;
                      if (nextState !== 'pending') resolveIfDone(next);
                      return next;
                    });
                  }}
                />
              </div>
            ) : (
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
            )}
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            {pendingChanges && status.text === 'pending' ? (
              <div className="w-full flex-1 overflow-y-auto px-3 py-2 text-sm leading-relaxed">
                <div className="p-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-foreground/90 whitespace-pre-wrap">
                      <InlineDiffResolver
                        key={`text-${body}|${pendingChanges.text}`}
                        before={body}
                        after={pendingChanges.text}
                        onChange={(merged, allResolved) => {
                          setBody(merged);
                          setStatus((prev) => {
                            let nextState: FieldStatus = 'pending';
                            if (allResolved) {
                              nextState = merged === pendingChanges.text ? 'applied' : 'dismissed';
                            }
                            const next = { ...prev, text: nextState } as typeof prev;
                            if (nextState !== 'pending') resolveIfDone(next);
                            return next;
                          });
                        }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ) : (
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
            )}

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
