import { Link, useParams } from "react-router-dom";
import { SourceTitle } from "../components/SourceLink";
import { useInvestigationStream } from "../hooks/useInvestigationStream";
import { useInvestigations } from "../hooks/useInvestigations";

export function EvidencePage() {
  const { id: routeId } = useParams();
  const { data: investigations } = useInvestigations();
  const id = routeId || investigations?.[0]?.id;
  const { query, sources, hint } = useInvestigationStream(id);
  const shown = sources.length ? sources : query.data?.sources || [];

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h2 className="text-xl font-semibold">Evidence</h2>
      <p className="text-slate-400">
        {query.data ? query.data.query : "Evidence from the latest investigation shows up here while the search is still running."}
      </p>
      {hint ? <p className="text-sm text-cyan-200">{hint}</p> : null}
      {!shown.length ? <p className="text-sm text-slate-500">No evidence yet.</p> : null}
      <ul className="space-y-2">
        {shown.map((source) => (
          <li key={source.source_id} className="rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm">
            <p className="text-xs uppercase tracking-wide text-cyan-300">{source.origin || "Source"}</p>
            <SourceTitle source={source} linkedClassName="text-cyan-200 underline" plainClassName="" />
            {source.excerpt ? <p className="mt-1 text-slate-400">{source.excerpt}</p> : null}
          </li>
        ))}
      </ul>
      {id ? (
        <Link to={`/investigation/${id}`} className="text-sm text-cyan-300">
          Back to the investigation
        </Link>
      ) : null}
    </div>
  );
}
