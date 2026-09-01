export interface WordChange {
  type: "same" | "removed" | "added";
  text: string;
}

/**
 * Word-level LCS diff. Powers the proofreading views: red-ink marks in the
 * retry-loop cards (removed = struck original, added = replacement) and the
 * amber highlighter on suspect OCR words (removed/changed words). Persian
 * text splits on whitespace like any other script — the diff never
 * reorders, so RTL rendering is unaffected.
 */
export function wordDiff(previous: string, current: string): WordChange[] {
  const a = previous.split(/\s+/).filter(Boolean);
  const b = current.split(/\s+/).filter(Boolean);
  const lcs = lcsLengths(a, b);
  const changes: WordChange[] = [];
  let i = a.length;
  let j = b.length;
  const tail: WordChange[] = [];
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      tail.push({ type: "same", text: a[i - 1] });
      i -= 1;
      j -= 1;
    } else if (j > 0 && (i === 0 || lcs[i][j - 1] >= lcs[i - 1][j])) {
      tail.push({ type: "added", text: b[j - 1] });
      j -= 1;
    } else {
      tail.push({ type: "removed", text: a[i - 1] });
      i -= 1;
    }
  }
  changes.push(...tail.reverse());
  return mergeRuns(changes);
}

function lcsLengths(a: string[], b: string[]): number[][] {
  const table: number[][] = Array.from({ length: a.length + 1 }, () =>
    new Array<number>(b.length + 1).fill(0),
  );
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      table[i][j] =
        a[i - 1] === b[j - 1] ? table[i - 1][j - 1] + 1 : Math.max(table[i - 1][j], table[i][j - 1]);
    }
  }
  return table;
}

/** Collapse alternating removed/added runs into one marked run each. */
function mergeRuns(changes: WordChange[]): WordChange[] {
  const merged: WordChange[] = [];
  for (const change of changes) {
    const last = merged[merged.length - 1];
    if (last && last.type === change.type) {
      last.text = `${last.text} ${change.text}`;
    } else {
      merged.push({ ...change });
    }
  }
  return merged;
}

export function hasChanges(changes: WordChange[]): boolean {
  return changes.some((change) => change.type !== "same");
}
