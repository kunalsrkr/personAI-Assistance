import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export function useInvestigations() {
  return useQuery({
    queryKey: ["investigations"],
    queryFn: api.listInvestigations,
    refetchInterval: (query) => {
      const items = query.state.data;
      const busy = items?.some((item) => item.status === "RUNNING" || item.status === "APPROVAL" || item.status === "PENDING");
      return busy ? 2000 : false;
    },
  });
}

export function useCreateInvestigation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      query,
      model,
      timeLimit,
      style,
      threadId,
    }: {
      query: string;
      model: string;
      timeLimit?: number;
      style?: string;
      threadId?: string;
    }) => api.createInvestigation(query, model, timeLimit ?? 45, style ?? "clear", threadId ?? ""),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["investigations"] });
    },
  });
}

export function useThreads() {
  return useQuery({
    queryKey: ["threads"],
    queryFn: api.listThreads,
    refetchInterval: 4000,
  });
}

export function useThread(id: string | undefined) {
  return useQuery({
    queryKey: ["threads", id],
    queryFn: () => api.getThread(id!),
    enabled: Boolean(id),
    refetchInterval: 4000,
  });
}

export function useInvestigation(id: string | undefined) {
  return useQuery({
    queryKey: ["investigations", id],
    queryFn: () => api.getInvestigation(id!),
    enabled: Boolean(id),
  });
}
