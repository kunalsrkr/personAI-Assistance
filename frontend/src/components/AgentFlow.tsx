import { useEffect, useMemo, useRef, useState } from "react";
import type { InvestigationStage } from "../types";

type Props = {
  stages: InvestigationStage[];
  variant?: "studio" | "embedded";
};

const tone = {
  running: { ink: "#7dd3fc", glow: "rgba(125,211,252,0.45)", label: "Live" },
  completed: { ink: "#6ee7b7", glow: "rgba(110,231,183,0.28)", label: "Done" },
  failed: { ink: "#fb7185", glow: "rgba(251,113,133,0.35)", label: "Stopped" },
  waiting: { ink: "#94a3b8", glow: "rgba(148,163,184,0.2)", label: "Waiting" },
} as const;

export function AgentFlow({ stages, variant = "studio" }: Props) {
  const embedded = variant === "embedded";
  const frame = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [active, setActive] = useState<string | null>(null);
  const layout = useMemo(() => place(stages, embedded), [stages, embedded]);

  useEffect(() => {
    const node = frame.current;
    if (!node) return;
    const fit = () => {
      const available = Math.max(node.clientWidth - (embedded ? 8 : 48), 280);
      setScale(Math.min(embedded ? 0.92 : 1, available / layout.width));
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(node);
    return () => observer.disconnect();
  }, [layout.width, embedded]);

  const selected = stages.find((stage) => stage.id === active) || stages.find((stage) => stage.status === "running") || stages.at(-1);

  return (
    <div
      className={
        embedded
          ? "agent-scene overflow-hidden rounded-2xl border border-white/10 bg-[#070b14]"
          : "agent-scene relative min-h-[680px] overflow-hidden rounded-[28px] border border-white/10 bg-[#070b14] shadow-[0_40px_80px_-48px_rgba(0,0,0,0.8)]"
      }
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_0%,rgba(56,189,248,0.16),transparent_32%),radial-gradient(circle_at_90%_100%,rgba(16,185,129,0.12),transparent_28%)]" />
      <div className="pointer-events-none absolute inset-0 opacity-40 [background-image:linear-gradient(rgba(148,163,184,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.08)_1px,transparent_1px)] [background-size:42px_42px] [mask-image:linear-gradient(180deg,#000,transparent_88%)]" />
      {!embedded ? (
        <div className="relative z-10 flex items-end justify-between gap-4 px-6 pt-6">
          <div>
            <p className="text-[11px] uppercase tracking-[0.28em] text-cyan-200/70">Live path</p>
            <h3 className="mt-1 text-lg font-medium text-white">{stages.length ? `${stages.length} steps` : "Waiting"}</h3>
          </div>
          <div className="flex gap-3 text-[11px] text-slate-400">
            <Legend swatch="bg-cyan-300" label="Live" />
            <Legend swatch="bg-emerald-300" label="Done" />
            <Legend swatch="bg-slate-500" label="Waiting" />
          </div>
        </div>
      ) : null}
      <div ref={frame} className={embedded ? "relative h-[220px] sm:h-[360px]" : "relative h-[460px]"}>
        <div className="pointer-events-none absolute left-1/2 top-[62%] h-28 w-[68%] -translate-x-1/2 rounded-[100%] bg-cyan-400/15 blur-3xl" />
        {!stages.length ? (
          <p className="absolute inset-0 grid place-items-center px-8 text-center text-sm text-slate-400">
            The graph appears as soon as the first tool starts.
          </p>
        ) : (
          <div
            className="agent-board absolute left-1/2 top-1/2"
            style={{
              width: layout.width,
              height: layout.height,
              marginLeft: -layout.width / 2,
              marginTop: -layout.height / 2,
              transform: `rotateX(${embedded ? 10 : 16}deg) scale(${scale})`,
            }}
          >
            <svg className="absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
              {layout.edges.map((edge) => (
                <g key={edge.id}>
                  <path d={edge.d} className="agent-edge" stroke="rgba(125,211,252,0.18)" strokeWidth="8" />
                  <path
                    d={edge.d}
                    className={`agent-edge ${edge.live ? "is-live" : ""}`}
                    stroke={edge.live ? "#7dd3fc" : "#6ee7b7"}
                    strokeWidth="2"
                    opacity={edge.live ? 1 : 0.8}
                  />
                  {edge.live ? (
                    <circle r="3.5" fill="#e0f2fe">
                      <animateMotion dur="1.5s" repeatCount="indefinite" path={edge.d} />
                    </circle>
                  ) : null}
                </g>
              ))}
            </svg>
            {layout.nodes.map((node) => {
              const paint = tone[node.stage.status as keyof typeof tone] || tone.waiting;
              const on = selected?.id === node.stage.id;
              return (
                <button
                  key={node.stage.id}
                  type="button"
                  onClick={() => setActive(node.stage.id)}
                  className={`agent-card absolute rounded-2xl border px-3.5 py-3 text-left ${node.stage.status === "running" ? "is-running" : ""}`}
                  style={{
                    left: node.x,
                    top: node.y,
                    width: layout.cardWidth,
                    height: layout.cardHeight,
                    borderColor: on ? paint.ink : "rgba(255,255,255,0.08)",
                    boxShadow: on ? `0 24px 40px -24px rgba(0,0,0,.9), 0 0 0 1px ${paint.ink}, 0 0 32px ${paint.glow}` : undefined,
                  }}
                >
                  <span className="absolute inset-y-3 left-0 w-0.5 rounded-full" style={{ background: paint.ink }} />
                  <span className="flex items-center justify-between gap-2 pl-2">
                    <span className="font-mono text-[10px] tracking-[0.18em] text-slate-500">{node.index}</span>
                    <span className="inline-flex items-center gap-1.5 text-[10px] uppercase tracking-[0.16em]" style={{ color: paint.ink }}>
                      <span className="relative grid h-2 w-2 place-items-center">
                        {node.stage.status === "running" ? (
                          <span className="agent-pulse absolute h-2 w-2 rounded-full" style={{ background: paint.ink }} />
                        ) : null}
                        <span className="h-1.5 w-1.5 rounded-full" style={{ background: paint.ink }} />
                      </span>
                      {paint.label}
                    </span>
                  </span>
                  <span className="mt-3 flex items-center gap-2 pl-2 text-cyan-100/80">
                    <Glyph id={node.stage.id} />
                    <span className="truncate text-sm font-medium text-white">{node.stage.label}</span>
                  </span>
                  <span className="mt-1 line-clamp-2 pl-2 text-xs leading-4 text-slate-400">{node.stage.detail || node.stage.status}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>
      {!embedded && selected ? (
        <div className="relative z-10 mx-6 mb-6 flex items-start justify-between gap-6 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
          <div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{selected.status}</p>
            <p className="mt-1 text-sm text-white">{selected.label}</p>
            <p className="mt-1 text-sm text-slate-400">{selected.detail || "Waiting for this step."}</p>
          </div>
          <Mark id={selected.id} />
        </div>
      ) : null}
    </div>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${swatch}`} />
      {label}
    </span>
  );
}

function Mark({ id }: { id: string }) {
  return (
    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/10 bg-white/[0.04] text-cyan-200">
      <Glyph id={id} />
    </span>
  );
}

function Glyph({ id }: { id: string }) {
  const kind = id.startsWith("read") ? "read" : id;
  if (kind === "search" || kind === "web") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="12" cy="12" r="8" />
        <path d="M4 12h16M12 4c2.5 2.4 2.5 13.6 0 16M12 4c-2.5 2.4-2.5 13.6 0 16" />
      </svg>
    );
  }
  if (kind === "model") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M12 3l1.6 5.2L19 10l-5.4 1.8L12 17l-1.6-5.2L5 10l5.4-1.8L12 3z" />
      </svg>
    );
  }
  if (kind === "read" || kind === "document" || kind === "file") {
    return (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M7 3.5h7l5 5V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5a1 1 0 0 1 1-1z" />
        <path d="M14 3.5V9h5" />
      </svg>
    );
  }
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="6" cy="12" r="2" />
      <circle cx="18" cy="7" r="2" />
      <circle cx="18" cy="17" r="2" />
      <path d="M8 12h6M16.2 8.4 8.8 11M16.2 15.6 8.8 13" />
    </svg>
  );
}

function place(stages: InvestigationStage[], embedded: boolean) {
  const cardWidth = embedded ? 188 : 248;
  const cardHeight = embedded ? 108 : 132;
  const gapX = embedded ? 40 : 88;
  const gapY = embedded ? 54 : 78;
  const cols = stages.length <= 1 ? 1 : stages.length <= 4 ? Math.min(stages.length, embedded ? 3 : 4) : embedded ? 3 : 4;
  const rows = Math.max(1, Math.ceil(stages.length / cols));
  const width = cols * cardWidth + (cols - 1) * gapX;
  const height = rows * cardHeight + Math.max(0, rows - 1) * gapY;
  const nodes = stages.map((stage, index) => {
    const row = Math.floor(index / cols);
    const column = index % cols;
    const visualColumn = row % 2 === 0 ? column : cols - 1 - column;
    return {
      stage,
      index: String(index + 1).padStart(2, "0"),
      x: visualColumn * (cardWidth + gapX),
      y: row * (cardHeight + gapY),
    };
  });
  const edges = nodes.slice(1).map((node, index) => {
    const from = nodes[index];
    const sameRow = from.y === node.y;
    const forward = node.x >= from.x;
    const x1 = sameRow ? from.x + (forward ? cardWidth : 0) : from.x + cardWidth / 2;
    const y1 = sameRow ? from.y + cardHeight / 2 : from.y + cardHeight;
    const x2 = sameRow ? node.x + (forward ? 0 : cardWidth) : node.x + cardWidth / 2;
    const y2 = sameRow ? node.y + cardHeight / 2 : node.y;
    const d = sameRow
      ? `M ${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}`
      : `M ${x1} ${y1} C ${x1} ${y1 + 36}, ${x2} ${y2 - 36}, ${x2} ${y2}`;
    return {
      id: `${from.stage.id}-${node.stage.id}`,
      d,
      live: from.stage.status === "running" || node.stage.status === "running",
    };
  });
  return { nodes, edges, width, height, cardWidth, cardHeight };
}
