import type { WordChange } from "../wordDiff";
import { hasChanges, wordDiff } from "../wordDiff";

/**
 * One word-diff renderer for both consumers: RetryLoopPanel's red-ink
 * proofreading marks and SourcePanel's amber highlighter differ only in the
 * classes they give removed/added words.
 */
export function DiffWords({
  previous,
  current,
  rtl,
  className,
  removedClassName,
  addedClassName,
}: {
  previous: string;
  current: string;
  rtl?: boolean;
  className: string;
  removedClassName: string;
  addedClassName: string;
}) {
  const changes: WordChange[] = wordDiff(previous, current);
  if (!hasChanges(changes)) {
    return (
      <p dir={rtl ? "rtl" : "auto"} className={className}>
        {current}
      </p>
    );
  }
  return (
    <p dir={rtl ? "rtl" : "auto"} className={className}>
      {changes.map((change, index) => {
        if (change.type === "same") {
          return <span key={index}>{change.text} </span>;
        }
        if (change.type === "removed") {
          return (
            <span key={index} className={removedClassName}>
              {change.text}{" "}
            </span>
          );
        }
        return (
          <span key={index} className={addedClassName}>
            {change.text}{" "}
          </span>
        );
      })}
    </p>
  );
}
