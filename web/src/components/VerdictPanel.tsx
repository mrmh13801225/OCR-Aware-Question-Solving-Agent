import type { BlockResult } from "../api";

type Verdict = "UNCHANGED" | "CHANGED" | "UNRESOLVED";

export function verdictOf(result: BlockResult): Verdict {
  if (result.unresolved) return "UNRESOLVED";
  return result.changed ? "CHANGED" : "UNCHANGED";
}

const VERDICT_STYLES: Record<Verdict, { stamp: string; ring: string; dot: string; text: string }> = {
  UNCHANGED: {
    stamp: "text-verified border-verified",
    ring: "border-verified",
    dot: "bg-verified",
    text: "text-verified",
  },
  CHANGED: {
    stamp: "text-proof border-proof",
    ring: "border-proof",
    dot: "bg-proof",
    text: "text-proof",
  },
  UNRESOLVED: {
    stamp: "text-suspect border-suspect",
    ring: "border-suspect",
    dot: "bg-suspect",
    text: "text-suspect",
  },
};

/** One verdict→color vocabulary shared by the verdict panel and batch cards. */
export function verdictColor(verdict: Verdict): string {
  return VERDICT_STYLES[verdict].text;
}

function Stamp({ verdict }: { verdict: Verdict }) {
  return (
    <span
      className={`inline-block -rotate-3 rounded border-2 px-3 py-1 font-mono text-sm font-bold tracking-widest ${VERDICT_STYLES[verdict].stamp}`}
    >
      {verdict}
    </span>
  );
}

export function VerdictPanel({ result }: { result: BlockResult }) {
  const verdict = verdictOf(result);
  const styles = VERDICT_STYLES[verdict];
  return (
    <section className="flex h-full flex-col gap-4 rounded border border-edge bg-panel p-5 shadow-panel">
      <h2 className="font-mono text-xs uppercase tracking-widest text-muted">Verdict</h2>
      <div className="flex items-center gap-4">
        <div
          className={`flex h-16 w-16 items-center justify-center rounded-full border-2 text-3xl font-bold ${styles.ring}`}
        >
          {result.answer}
        </div>
        <div className="flex flex-col gap-2">
          <Stamp verdict={verdict} />
          <div className="flex items-center gap-1 font-mono text-xs text-muted">
            {Array.from({ length: result.attempts }, (_, i) => (
              <span key={i} className={`h-2 w-2 rounded-full ${styles.dot}`} />
            ))}
            <span className="ml-2">
              {result.attempts} {result.attempts === 1 ? "attempt" : "attempts"}
            </span>
          </div>
        </div>
      </div>
      <pre className="mt-auto overflow-auto rounded bg-codebg p-3 font-mono text-xs leading-relaxed">
        {jsonLines(result).map((line, index) => (
          <JsonLine key={index} line={line} />
        ))}
      </pre>
    </section>
  );
}

interface JsonLine {
  indent: number;
  key?: string;
  value?: string;
  raw?: string;
}

/** Two-tone rendering: muted keys, ink string values, amber booleans/numbers. */
function jsonLines(result: BlockResult): JsonLine[] {
  const entries: [string, string | boolean | number][] = [
    ["answer", result.answer],
    ["question_text", result.question_text],
    ["changed", result.changed],
    ["original_ocr_text", result.original_ocr_text],
    ["unresolved", result.unresolved],
    ["attempts", result.attempts],
  ];
  const lines: JsonLine[] = [{ indent: 0, raw: "{" }];
  entries.forEach(([key, value], index) => {
    const comma = index < entries.length - 1 ? "," : "";
    lines.push({
      indent: 1,
      key: `"${key}": `,
      value: typeof value === "string" ? `"${value}${comma}"` : `${value}${comma}`,
    });
  });
  lines.push({ indent: 0, raw: "}" });
  return lines;
}

function JsonLine({ line }: { line: JsonLine }) {
  const pad = "  ".repeat(line.indent);
  if (line.raw !== undefined) {
    return <div className="text-muted">{pad + line.raw}</div>;
  }
  const isString = line.value?.startsWith('"');
  return (
    <div>
      <span className="text-muted">{pad + line.key}</span>
      <span className={isString ? "text-ink" : "text-suspect"}>{line.value}</span>
    </div>
  );
}
