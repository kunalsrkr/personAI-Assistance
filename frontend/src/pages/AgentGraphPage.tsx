import { useSearchParams } from "react-router-dom";
import { AgentFlow } from "../components/AgentFlow";
import { useInvestigations } from "../hooks/useInvestigations";
import { useInvestigationStream } from "../hooks/useInvestigationStream";

export function AgentGraphPage() {
  const [params] = useSearchParams();
  const requested = params.get("id") || undefined;
  const { data: investigations } = useInvestigations();
  const id = requested || investigations?.[0]?.id;
  const { query, stages, hint, status } = useInvestigationStream(id);
  const shown = stages.length ? stages : query.data?.stages || [];

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-[0.28em] text-cyan-200/70">Command surface</p>
          <h2 className="mt-1 text-2xl font-medium text-white">How this answer was built</h2>
        </div>
        <p className="max-w-xl text-sm text-slate-400">
          {query.data?.query || "Run an investigation to see each tool move from waiting to done."}
        </p>
      </div>
      {hint ? <p className="text-sm text-cyan-100">{hint}</p> : null}
      <p className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{status}</p>
      <AgentFlow stages={shown} />
    </div>
  );
}
