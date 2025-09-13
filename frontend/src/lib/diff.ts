export type DiffSegment = {
  value: string;
  type: 'equal' | 'added' | 'removed';
};

function tokenize(input: string): string[] {
  return input.match(/(\s+|[^\s]+)/g) ?? [];
}

function lcsTable(a: string[], b: string[]): number[][] {
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (a[i] === b[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  return dp;
}

export function diffWords(oldText: string, newText: string): DiffSegment[] {
  const a = tokenize(oldText);
  const b = tokenize(newText);
  const dp = lcsTable(a, b);

  const segments: DiffSegment[] = [];
  let i = 0,
    j = 0;

  const push = (type: DiffSegment['type'], value: string) => {
    if (!value) return;
    const last = segments[segments.length - 1];
    if (last && last.type === type) {
      last.value += value;
    } else {
      segments.push({ type, value });
    }
  };

  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push('equal', a[i]);
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      push('removed', a[i]);
      i++;
    } else {
      push('added', b[j]);
      j++;
    }
  }

  while (i < a.length) {
    push('removed', a[i]);
    i++;
  }
  while (j < b.length) {
    push('added', b[j]);
    j++;
  }

  return segments;
}
