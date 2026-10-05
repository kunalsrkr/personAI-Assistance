import { useEffect, useState } from "react";
import type { ClarifyChoice, InvestigationSource, InvestigationStage, InvestigationStatus } from "../types";
import { useInvestigation } from "./useInvestigations";

type StreamState = {
  status: InvestigationStatus;
  hint: string;
  thinking: string;
  answer: string;
  sources: InvestigationSource[];
  stages: InvestigationStage[];
  clarify: { prompt: string; choices: ClarifyChoice[]; step: number; total: number; seconds: number } | null;
  review: { prompt: string; choices: ClarifyChoice[] } | null;
  deadline: string | null;
  parked: boolean;
};

const empty: StreamState = {
  status: "PENDING",
  hint: "",
  thinking: "",
  answer: "",
  sources: [],
  stages: [],
  clarify: null,
  review: null,
  deadline: null,
  parked: false,
};

export function useInvestigationStream(id: string | undefined) {
  const query = useInvestigation(id);
  const [stream, setStream] = useState<StreamState>(empty);

  useEffect(() => {
    setStream(empty);
    if (!id) return;
    let answer = "";
    let thinking = "";
    const sources: InvestigationSource[] = [];
    const stages: InvestigationStage[] = [];
    let cancelled = false;
    const source = new EventSource(`/api/v1/investigations/${id}/events`);

    source.onmessage = (message) => {
      if (cancelled) return;
      const event = JSON.parse(message.data) as {
        type: string;
        text?: string;
        channel?: string;
        status?: InvestigationStatus;
        hint?: string;
        final_answer?: string | null;
        thinking?: string;
        sources?: InvestigationSource[];
        stages?: InvestigationStage[];
        stage?: InvestigationStage;
        source?: InvestigationSource;
        prompt?: string;
        choices?: ClarifyChoice[];
        step?: number;
        total?: number;
        seconds?: number;
        deadline?: string;
        review_prompt?: string;
        review_choices?: ClarifyChoice[];
      };
      if (event.type === "ping") return;
      if (event.type === "hint" && event.text) {
        setStream((current) => ({ ...current, hint: event.text || "", status: "RUNNING", clarify: null }));
      }
      if (event.type === "park") {
        setStream((current) => ({
          ...current,
          parked: true,
          hint: event.text || "Still working. You can ask the next question.",
          status: "RUNNING",
        }));
      }
      if (event.type === "clock" && event.deadline) {
        setStream((current) => ({ ...current, deadline: event.deadline || null, status: "RUNNING" }));
      }
      if (event.type === "clarify" && event.prompt && event.choices) {
        setStream((current) => ({
          ...current,
          status: "APPROVAL",
          hint: event.prompt || "",
          deadline: null,
          clarify: {
            prompt: event.prompt || "",
            choices: event.choices || [],
            step: event.step || 1,
            total: event.total || 1,
            seconds: event.seconds || 20,
          },
        }));
      }
      if (event.type === "stage" && event.stage) {
        const next = event.stage;
        const index = stages.findIndex((item) => item.id === next.id);
        if (index >= 0) stages[index] = next;
        else stages.push(next);
        setStream((current) => ({ ...current, stages: [...stages], status: "RUNNING" }));
      }
      if (event.type === "evidence" && event.source) {
        if (!sources.some((item) => item.source_id === event.source?.source_id)) {
          sources.push(event.source);
        }
        setStream((current) => ({ ...current, sources: [...sources], status: "RUNNING" }));
      }
      if (event.type === "token" && event.text) {
        if (event.channel === "think") thinking += event.text;
        else answer += event.text;
        setStream((current) => ({
          ...current,
          answer,
          thinking,
          status: "RUNNING",
        }));
      }
      if (event.type === "done") {
        setStream({
          status: event.status || "COMPLETED",
          hint: event.hint || "Answer ready.",
          thinking: event.thinking || thinking,
          answer: event.final_answer || answer,
          sources: event.sources || sources,
          stages: event.stages || stages,
          clarify: null,
          review:
            event.review_prompt && event.review_choices
              ? { prompt: event.review_prompt, choices: event.review_choices }
              : null,
          deadline: null,
          parked: false,
        });
        source.close();
      }
    };

    source.onerror = () => {
      if (!cancelled) source.close();
    };

    return () => {
      cancelled = true;
      source.close();
    };
  }, [id]);

  return { query, ...stream };
}
