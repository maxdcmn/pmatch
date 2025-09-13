import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function Home() {
  return (
    <div className="bg-background flex min-h-screen items-center justify-center">
      <div className="text-center">
        <h1 className="mb-4 font-mono text-4xl">
          pm<span className="pr-1 -tracking-[0.1em]">atch</span>
        </h1>
        <Button asChild>
          <Link href="/workspace">Enter Workspace</Link>
        </Button>
      </div>
    </div>
  );
}
