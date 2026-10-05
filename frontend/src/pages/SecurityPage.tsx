import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

const metrics = [
  ["Requests inspected", "inspected"],
  ["Allowed", "allowed"],
  ["Masked", "masked"],
  ["Blocked", "blocked"],
  ["Human approval", "human_approval"],
] as const;

export function SecurityPage() {
  const { data } = useQuery({ queryKey: ["security"], queryFn: api.getSecurityEvents });

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <h2 className="text-xl font-semibold">Security Control Center</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {metrics.map(([label, key]) => (
          <div key={key} className="rounded-lg border border-slate-800 bg-slate-900/50 p-4">
            <p className="text-xs text-slate-400">{label}</p>
            <p className="text-2xl">{data?.[key] ?? 0}</p>
          </div>
        ))}
      </div>
      <p className="text-slate-400">Security events are produced in Sprint 6. No PII processing is active yet.</p>
    </div>
  );
}
