import { Link, useParams } from "react-router-dom";
import { AgentFlow } from "../components/AgentFlow";
import { LinkedText, SourceTitle } from "../components/SourceLink";
import { useInvestigationStream } from "../hooks/useInvestigationStream";
import type { InvestigationSource } from "../types";

export function InvestigationPage() {
  const { id } = useParams();
  const { query, status, hint, thinking, answer, sources, stages } = useInvestigationStream(id);
  const data = query.data;
  const liveStatus = status === "PENDING" ? data?.status || status : status;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Investigation</h2>
        {id ? (
          <Link to={`/agents?id=${id}`} className="text-sm text-cyan-300">
            Open agent graph
          </Link>
        ) : null}
      </div>
      {!id ? <p className="text-slate-400">Start an investigation from the Command Center.</p> : null}
      {id && query.isLoading && !hint ? <p className="text-slate-400">Connecting…</p> : null}
      {data ? (
        <div className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-6">
          <p className="text-sm text-slate-400">STATUS: {liveStatus}</p>
          <p className="text-sm">
            Iteration {data.iteration}/{data.max_iterations}
            {data.model ? ` · Model ${data.model}` : ""}
          </p>
          <p>{data.query}</p>
          {hint ? (
            <p className="rounded-lg border border-cyan-500/30 bg-cyan-500/10 px-3 py-2 text-sm text-cyan-100">{hint}</p>
          ) : null}
          <AgentFlow stages={stages.length ? stages : data.stages || []} variant="embedded" />
          {thinking ? (
            <p className="max-h-28 overflow-auto whitespace-pre-wrap text-xs leading-5 text-slate-500">{thinking}</p>
          ) : null}
          {answer || data.final_answer ? (
            <p className="whitespace-pre-wrap text-sm leading-6">
              <LinkedText text={answer || data.final_answer || ""} />
            </p>
          ) : (
            <p className="text-sm text-slate-400">Evidence will appear here before the full answer.</p>
          )}
          <EvidenceList sources={sources.length ? sources : data.sources || []} />
        </div>
      ) : null}
    </div>
  );
}

function EvidenceList({ sources }: { sources: InvestigationSource[] }) {
  if (!sources.length) return null;
  return (
    <div className="space-y-2">
      <h3 className="text-sm uppercase tracking-wide text-slate-400">Evidence</h3>
      <ul className="space-y-2 text-sm text-slate-300">
        {sources.map((source) => (
          <li key={source.source_id} className="rounded-lg border border-slate-800 px-3 py-2">
            <p className="text-xs uppercase tracking-wide text-cyan-300">{source.origin || "Source"}</p>
            <SourceTitle source={source} linkedClassName="text-cyan-200 underline" plainClassName="" />
            {source.excerpt ? <p className="text-slate-400">{source.excerpt}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
