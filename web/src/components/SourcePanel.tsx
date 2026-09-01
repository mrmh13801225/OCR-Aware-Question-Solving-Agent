import { useState } from "react";
import { hasChanges, wordDiff } from "../wordDiff";

type Tab = "ocr" | "image";

export function SourcePanel({
  imageUrl,
  ocrText,
  finalQuestionText,
  fileName,
}: {
  imageUrl: string | null;
  ocrText: string | null;
  finalQuestionText: string | null;
  fileName: string | null;
}) {
  const [tab, setTab] = useState<Tab>("image");
  return (
    <section className="flex h-full flex-col gap-3 rounded border border-edge bg-panel p-5 shadow-panel">
      <h2 className="font-mono text-xs uppercase tracking-widest text-muted">Source block</h2>
      {fileName && <p className="font-mono text-xs text-muted">{fileName}</p>}
      <div className="flex gap-2">
        <TabButton active={tab === "image"} onClick={() => setTab("image")}>
          Image
        </TabButton>
        <TabButton active={tab === "ocr"} onClick={() => setTab("ocr")} disabled={!ocrText}>
          OCR text
        </TabButton>
      </div>
      <div className="flex-1 overflow-auto rounded bg-codebg p-3">
        {tab === "image" && imageUrl && (
          <img
            src={imageUrl}
            alt="scanned question block"
            className="mx-auto max-h-full rounded shadow-scan"
          />
        )}
        {tab === "ocr" && ocrText && (
          <OcrText ocrText={ocrText} finalQuestionText={finalQuestionText} />
        )}
        {!imageUrl && <p className="text-sm text-muted">No image loaded.</p>}
      </div>
    </section>
  );
}

/**
 * The original OCR text; words the correction changed carry the amber
 * highlighter — the proofreader's "this looked wrong" mark (§9.3).
 */
function OcrText({
  ocrText,
  finalQuestionText,
}: {
  ocrText: string;
  finalQuestionText: string | null;
}) {
  if (!finalQuestionText) {
    return (
      <p dir="rtl" className="whitespace-pre-wrap font-farsi text-base leading-loose text-ink">
        {ocrText}
      </p>
    );
  }
  const changes = wordDiff(ocrText, finalQuestionText);
  if (!hasChanges(changes)) {
    return (
      <p dir="rtl" className="whitespace-pre-wrap font-farsi text-base leading-loose text-ink">
        {ocrText}
      </p>
    );
  }
  return (
    <p dir="rtl" className="whitespace-pre-wrap font-farsi text-base leading-loose text-ink">
      {changes.map((change, index) => {
        if (change.type === "same") {
          return <span key={index}>{change.text} </span>;
        }
        if (change.type === "removed") {
          return (
            <mark key={index} className="rounded bg-suspect/30 px-0.5 text-ink">
              {change.text}{" "}
            </mark>
          );
        }
        return (
          <span key={index} className="text-suspect">
            {change.text}{" "}
          </span>
        );
      })}
    </p>
  );
}

function TabButton({
  active,
  onClick,
  disabled,
  children,
}: {
  active: boolean;
  onClick: () => void;
  disabled?: boolean;
  children: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded px-3 py-1 font-mono text-xs uppercase tracking-wide ${
        active ? "bg-suspect text-bg" : "bg-codebg text-muted hover:text-ink"
      } disabled:opacity-40`}
    >
      {children}
    </button>
  );
}
