import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function EvaluationPage() {
  const { data } = useQuery({ queryKey: ["evaluations"], queryFn: api.getEvaluations });

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h2 className="text-xl font-semibold">Evaluation</h2>
      <p className="text-slate-400">{data?.message}</p>
      <pre className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs text-slate-300">
        {JSON.stringify(data ?? {}, null, 2)}
      </pre>
    </div>
  );
}
