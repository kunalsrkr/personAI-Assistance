export type InvestigationStatus =
  | "PENDING"
  | "RUNNING"
  | "COMPLETED"
  | "APPROVAL"
  | "FAILED";

export type Investigation = {
  id: string;
  query: string;
  status: InvestigationStatus;
  iteration: number;
  max_iterations: number;
  started_at: string;
  completed_at: string | null;
  final_answer: string | null;
  thinking?: string;
  hint?: string;
  confidence: number | null;
  step_count: number;
  model?: string | null;
  time_limit?: number;
  deadline_at?: string | null;
  sources?: InvestigationSource[];
  stages?: InvestigationStage[];
  clarify_prompt?: string;
  clarify_choices?: ClarifyChoice[];
  thread_id?: string;
};

export type ThreadTurn = { role: string; text: string; at: string };
export type ThreadCheckpoint = { id: string; label: string; at: string };
export type TopicThread = {
  id: string;
  title: string;
  memory: string;
  turns: ThreadTurn[];
  checkpoints: ThreadCheckpoint[];
  active_checkpoint: string;
  latest_investigation_id: string;
  updated_at: string;
};

export type ClarifyChoice = {
  id: string;
  label: string;
};

export type InvestigationSource = {
  source_id: string;
  title: string;
  excerpt: string;
  origin?: string;
  url?: string;
  play_root?: number | null;
  play_path?: string;
};

export type InvestigationStage = {
  id: string;
  label: string;
  status: string;
  detail?: string;
};

export type SecuritySummary = {
  inspected: number;
  allowed: number;
  masked: number;
  blocked: number;
  human_approval: number;
  events: Array<{ action: string; detail: string }>;
};

export type EvaluationSummary = {
  rag: { recall_at_5: number | null; mrr: number | null };
  answer_quality: { faithfulness: number | null; citation_accuracy: number | null };
  agent_reliability: { task_success: number | null; tool_success: number | null };
  security: {
    prompt_injection_blocked: number | null;
    pii_leakage: number | null;
    unauthorized_tools_blocked: number | null;
  };
  message: string;
};
