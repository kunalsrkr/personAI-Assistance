import type { EvaluationSummary, Investigation, SecuritySummary, TopicThread } from "../types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  listInvestigations: () => request<Investigation[]>("/api/v1/investigations"),
  listModels: () => request<{ models: string[]; default: string | null }>("/api/v1/models"),
  createInvestigation: (query: string, model: string, timeLimit: number, style: string, threadId = "") =>
    request<Investigation>("/api/v1/investigations", {
      method: "POST",
      body: JSON.stringify({ query, model, time_limit: timeLimit, style, thread_id: threadId }),
    }),
  listThreads: () => request<{ threads: TopicThread[] }>("/api/v1/threads"),
  getThread: (id: string) => request<TopicThread>(`/api/v1/threads/${id}`),
  restoreThread: (id: string, checkpointId: string) =>
    request<TopicThread>(`/api/v1/threads/${id}/restore`, {
      method: "POST",
      body: JSON.stringify({ checkpoint_id: checkpointId }),
    }),
  getInvestigation: (id: string) => request<Investigation>(`/api/v1/investigations/${id}`),
  choose: (id: string, choiceId: string, note = "") =>
    request<Investigation>(`/api/v1/investigations/${id}/choice`, {
      method: "POST",
      body: JSON.stringify({ choice_id: choiceId, note }),
    }),
  retry: (id: string, choiceId: string) =>
    request<Investigation>(`/api/v1/investigations/${id}/retry`, {
      method: "POST",
      body: JSON.stringify({ choice_id: choiceId }),
    }),
  getTrace: (id: string) => request<{ spans: unknown[] }>(`/api/v1/investigations/${id}/trace`),
  getSources: (id: string) =>
    request<{ sources: unknown[] }>(`/api/v1/investigations/${id}/sources`),
  getSecurityEvents: () => request<SecuritySummary>("/api/v1/security/events"),
  getEvaluations: () => request<EvaluationSummary>("/api/v1/evaluations"),
  getAgents: () => request<{ agents: Array<{ id: string; status: string }> }>("/api/v1/agents"),
};
