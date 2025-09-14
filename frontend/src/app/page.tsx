import Link from 'next/link';
import { ArrowRight, CheckCircle2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from '@/components/theme-toggle';
import { AnimatedMap } from '@/components/animated-map';

export default function Home() {
  return (
    <div className="bg-background relative min-h-screen px-1">
      <header className="relative z-10 mx-auto mb-12 flex w-full max-w-6xl items-center justify-between px-6 py-4">
        <div className="flex items-center gap-8">
          <Link href="/">
            <span className="font-mono text-lg">
              pm<span className="pr-1 -tracking-[0.1em]">atch</span>
            </span>
          </Link>
        </div>
        <div className="flex items-center gap-1 sm:gap-2">
          <ThemeToggle />
        </div>
      </header>
      <main className="bg-background border-border mx-auto w-full max-w-3xl border-2 p-6">
        <section className="mb-6">
          <div className="grid grid-cols-1 items-center gap-6 md:grid-cols-2 md:gap-6">
            <div className="relative">
              <h1 className="leading-tightest relative z-10 font-mono text-4xl tracking-tight sm:text-5xl md:text-6xl">
                Experience matching: easy, precise
              </h1>
              <p className="text-muted-foreground mt-4 max-w-xl text-sm text-pretty sm:text-base">
                Let pmatch generate personalized outreach messages and start meaningful
                collaborations.
              </p>
              <div className="mt-6 flex flex-wrap items-center gap-3">
                <Button
                  asChild
                  size="lg"
                  variant="outline"
                  className="rounded-none border-2 border-emerald-600 text-emerald-700 hover:bg-emerald-600 hover:text-white dark:border-emerald-400 dark:text-emerald-300 dark:hover:bg-emerald-400 dark:hover:text-black"
                >
                  <Link href="/workspace" className="inline-flex items-center">
                    Enter Workspace
                    <ArrowRight className="ml-2 size-4" />
                  </Link>
                </Button>
              </div>
              <ul className="text-foreground mt-6 grid gap-2 text-sm">
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400" />{' '}
                  Tailored contact proposals
                </li>
                <li className="flex items-center gap-2">
                  <CheckCircle2 className="size-4 text-emerald-600 dark:text-emerald-400" /> Yet
                  another LLM agent
                </li>
              </ul>
            </div>
            <div className="border-border relative h-full min-h-[320px] border-2 md:min-h-[420px]">
              <AnimatedMap />
            </div>
          </div>
        </section>
        <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Step num={1} title="Drop" desc="Upload your CV, papers or paste notes." />
          <Step num={2} title="Chat" desc="Ask questions and refine direction." />
          <Step num={3} title="Compile" desc="Export a crisp contact brief." />
        </section>
      </main>
    </div>
  );
}

function Step({ num, title, desc }: { num: number; title: string; desc: string }) {
  return (
    <div className="border-border border-2 p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="flex size-6 items-center justify-center border-2 border-emerald-600 text-[11px] font-bold text-emerald-700 dark:border-emerald-400 dark:text-emerald-300">
          {num}
        </span>
        <span className="text-sm font-medium">{title}</span>
      </div>
      <p className="text-muted-foreground text-sm">{desc}</p>
    </div>
  );
}
