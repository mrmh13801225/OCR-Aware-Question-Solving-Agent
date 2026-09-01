import { useState } from "react";

type Tab = "ocr" | "image";

export function SourcePanel({
  imageUrl,
  ocrText,
  fileName,
}: {
  imageUrl: string | null;
  ocrText: string | null;
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
          <p dir="rtl" className="whitespace-pre-wrap font-farsi text-base leading-loose text-ink">
            {ocrText}
          </p>
        )}
        {!imageUrl && <p className="text-sm text-muted">No image loaded.</p>}
      </div>
    </section>
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
