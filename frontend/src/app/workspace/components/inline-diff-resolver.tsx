'use client';

import React, { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { Check, X } from 'lucide-react';
import { diffWords, DiffSegment } from '@/lib/diff';

export type InlineDiffResolverProps = {
  before: string;
  after: string;
  className?: string;
  onChange: (merged: string, allResolved: boolean) => void;
};

type EqualOp = { type: 'equal'; value: string };
type ChangeOp = { type: 'change'; before: string; after: string };
type Op = EqualOp | ChangeOp;

function groupOps(before: string, after: string): Op[] {
  const segs: DiffSegment[] = diffWords(before, after);
  const ops: Op[] = [];

  let i = 0;
  while (i < segs.length) {
    const s = segs[i];
    if (s.type === 'equal') {
      ops.push({ type: 'equal', value: s.value });
      i++;
      continue;
    }
    let removed = '';
    let added = '';
    while (i < segs.length && segs[i].type === 'removed') {
      removed += segs[i].value;
      i++;
    }
    while (i < segs.length && segs[i].type === 'added') {
      added += segs[i].value;
      i++;
    }
    if (removed.length > 0 || added.length > 0) {
      ops.push({ type: 'change', before: removed, after: added });
    }
  }
  return ops;
}

export function InlineDiffResolver({
  before,
  after,
  className,
  onChange,
}: InlineDiffResolverProps) {
  const ops = useMemo(() => groupOps(before, after), [before, after]);
  const changeIdxs = ops
    .map((op, idx) => (op.type === 'change' ? idx : -1))
    .filter((n) => n !== -1);
  const [decisions, setDecisions] = useState<Record<number, 'pending' | 'accept' | 'decline'>>(
    () => {
      const init: Record<number, 'pending' | 'accept' | 'decline'> = {};
      changeIdxs.forEach((i) => (init[i] = 'pending'));
      return init;
    },
  );

  const commit = (next: Record<number, 'pending' | 'accept' | 'decline'>) => {
    const merged = ops
      .map((op, idx) => {
        if (op.type === 'equal') return op.value;
        const d = next[idx];
        if (!d || d === 'pending') return op.before;
        return d === 'accept' ? op.after : op.before;
      })
      .join('');
    const allResolved = Object.values(next).every((v) => v !== 'pending');
    onChange(merged, allResolved);
  };

  const setDecision = (idx: number, decision: 'accept' | 'decline') => {
    setDecisions((prev) => {
      const next = { ...prev, [idx]: decision };
      commit(next);
      return next;
    });
  };

  const markerStyle = (rgba: string): React.CSSProperties => ({
    boxShadow: `inset 0 -0.35em 0 ${rgba}`,
    WebkitBoxDecorationBreak: 'clone' as any,
    boxDecorationBreak: 'clone' as any,
  });

  const clipMiddle = (text: string, max = 60) => {
    if (text.length <= max && !text.includes('\n')) return text;
    const head = text.slice(0, Math.floor(max / 2));
    const tail = text.slice(-Math.floor(max / 2));
    return `${head}…${tail}`;
  };

  return (
    <div
      className={cn('max-w-full min-w-0 break-words whitespace-pre-wrap', className)}
      style={{ overflowWrap: 'anywhere', wordBreak: 'break-word' }}
    >
      {ops.map((op, idx) => {
        if (op.type === 'equal') {
          return <span key={idx}>{op.value}</span>;
        }

        const state = decisions[idx];
        const m = op.after.match(/(\s*)$/);
        const trailing = m ? m[1] : '';
        const addCore = op.after.slice(0, op.after.length - trailing.length);

        if (state === 'accept') {
          return (
            <span key={idx}>
              <span className="px-1">{addCore}</span>
              {trailing && <span>{trailing}</span>}
            </span>
          );
        }
        if (state === 'decline') {
          return (
            <span key={idx}>
              <span className="px-1">{op.before}</span>
            </span>
          );
        }

        return (
          <span key={idx}>
            {op.before && (
              <span
                className={cn('align-baseline text-red-700 line-through dark:text-red-300')}
                title={op.before}
              >
                {clipMiddle(op.before)}
              </span>
            )}
            {addCore && (
              <span
                className={cn('align-baseline text-green-800 dark:text-green-200')}
                style={markerStyle('rgba(34,197,94,0.25)')}
              >
                {addCore}
              </span>
            )}
            {trailing && <span>{trailing}</span>}
            <span className="ml-1 inline-flex gap-1">
              <button
                type="button"
                aria-label="Accept change"
                onClick={() => setDecision(idx, 'accept')}
                className="inline-flex h-[1em] w-[1em] items-center justify-center rounded align-baseline leading-none text-green-700 hover:bg-green-500/20"
              >
                <Check className="h-[0.9em] w-[0.9em]" />
              </button>
              <button
                type="button"
                aria-label="Decline change"
                onClick={() => setDecision(idx, 'decline')}
                className="inline-flex h-[1em] w-[1em] items-center justify-center rounded leading-none text-red-700 hover:bg-red-500/20"
              >
                <X className="h-[0.9em] w-[0.9em]" />
              </button>
            </span>
          </span>
        );
      })}
    </div>
  );
}
export default InlineDiffResolver;
