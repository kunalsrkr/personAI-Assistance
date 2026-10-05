import type { ReactNode } from "react";
import type { InvestigationSource } from "../types";

export function httpSourceUrl(source: Pick<InvestigationSource, "url" | "source_id">): string {
  const candidates = [source.url, source.source_id];
  for (const candidate of candidates) {
    const raw = (candidate || "").trim();
    if (/^https?:\/\//i.test(raw)) return raw;
  }
  return "";
}

export function LinkedText({ text }: { text: string }) {
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const match of text.matchAll(/https?:\/\/[^\s<>"']+/gi)) {
    const raw = match[0];
    const start = match.index ?? 0;
    const href = raw.replace(/[),.;:]+$/g, "");
    if (start > cursor) nodes.push(text.slice(cursor, start));
    nodes.push(
      <a key={`${start}-${href}`} href={href} target="_blank" rel="noreferrer" className="underline decoration-current/40 underline-offset-2">
        {href}
      </a>,
    );
    const tail = raw.slice(href.length);
    if (tail) nodes.push(tail);
    cursor = start + raw.length;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return <>{nodes}</>;
}

export function SourceTitle({
  source,
  linkedClassName,
  plainClassName,
}: {
  source: Pick<InvestigationSource, "title" | "url" | "source_id">;
  linkedClassName: string;
  plainClassName: string;
}) {
  const href = httpSourceUrl(source);
  if (!href) return <p className={plainClassName}>{source.title}</p>;
  return (
    <a href={href} target="_blank" rel="noreferrer" className={linkedClassName}>
      {source.title || href}
    </a>
  );
}
