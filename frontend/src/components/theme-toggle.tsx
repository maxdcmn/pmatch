'use client';

import { useTheme } from 'next-themes';
import { useState, useEffect } from 'react';
import { Moon, Sun } from 'lucide-react';

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const isDark = (resolvedTheme ?? theme) === 'dark';
  const toggle = () => setTheme(isDark ? 'light' : 'dark');

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <button
        type="button"
        className="group text-foreground hover:text-muted-foreground inline-flex cursor-pointer items-center gap-1 font-mono text-sm transition-colors"
      >
        <span className="relative inline-block h-4 w-4">
          <Sun className="absolute inset-0 size-4" />
        </span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      className="group text-foreground hover:text-muted-foreground inline-flex cursor-pointer items-center gap-1 font-mono text-sm transition-colors"
    >
      <span className="relative inline-block h-4 w-4">
        <Sun className="absolute inset-0 size-4 scale-100 dark:scale-0" />
        <Moon className="absolute inset-0 size-4 scale-0 dark:scale-100" />
      </span>
    </button>
  );
}
