import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useCreateInvestigation, useInvestigations } from "../hooks/useInvestigations";

export function CommandCenterPage() {
  const [query, setQuery] = useState(
    "Search the web for recent information about the Model Context Protocol and summarize it.",
  );
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const navigate = useNavigate();
  const { data: investigations, isLoading } = useInvestigations();
  const createInvestigation = useCreateInvestigation();

  useEffect(() => {
    void api.listModels().then((payload) => {
      setModels(payload.models);
      setModel(payload.default ?? payload.models[0] ?? "");
    });
  }, []);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const created = await createInvestigation.mutateAsync({ query, model });
    navigate(`/investigation/${created.id}`);
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <form onSubmit={onSubmit} className="space-y-4 rounded-xl border border-slate-800 bg-slate-900/60 p-6">
        <label className="block text-sm text-slate-300">Ask your enterprise question</label>
        <textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          rows={4}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-sm outline-none focus:border-cyan-500"
        />
        <label className="block text-sm text-slate-300" htmlFor="model">
          Ollama model
        </label>
        <select
          id="model"
          value={model}
          onChange={(event) => setModel(event.target.value)}
          className="w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-2 text-sm"
        >
          {models.length === 0 ? <option value="">No local models found</option> : null}
          {models.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          disabled={createInvestigation.isPending}
          className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-medium text-slate-950 disabled:opacity-50"
        >
          {createInvestigation.isPending ? "Creating…" : "Run Investigation"}
        </button>
        {createInvestigation.isError ? (
          <p className="text-sm text-rose-400">Could not reach the API. Start the FastAPI backend on port 8000.</p>
        ) : null}
      </form>

      <section>
        <h2 className="mb-3 text-sm uppercase tracking-wide text-slate-400">Recent Investigations</h2>
        {isLoading ? <p className="text-slate-400">Loading…</p> : null}
        {!isLoading && !investigations?.length ? (
          <p className="text-slate-500">No investigations yet. Sprint 0 stores them in API memory.</p>
        ) : null}
        <ul className="space-y-2">
          {investigations?.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => navigate(`/investigation/${item.id}`)}
                className="flex w-full items-center justify-between rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-3 text-left hover:border-slate-600"
              >
                <span className="truncate pr-4">{item.query}</span>
                <span className="shrink-0 text-xs text-cyan-300">
                  {item.status} · {item.step_count} steps
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
