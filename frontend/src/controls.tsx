import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api/client";

export type AnswerStyle = "brief" | "clear" | "full";

type Controls = {
  models: string[];
  model: string;
  setModel: (model: string) => void;
  timeLimit: number;
  setTimeLimit: (seconds: number) => void;
  style: AnswerStyle;
  setStyle: (style: AnswerStyle) => void;
};

const ControlsContext = createContext<Controls | null>(null);

export function ControlsProvider({ children }: { children: ReactNode }) {
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [timeLimit, setTimeLimit] = useState(45);
  const [style, setStyle] = useState<AnswerStyle>("clear");

  useEffect(() => {
    void api.listModels().then((payload) => {
      setModels(payload.models);
      setModel(payload.default ?? payload.models[0] ?? "");
    });
  }, []);

  return (
    <ControlsContext.Provider value={{ models, model, setModel, timeLimit, setTimeLimit, style, setStyle }}>
      {children}
    </ControlsContext.Provider>
  );
}

export function useControls() {
  const value = useContext(ControlsContext);
  if (!value) throw new Error("Controls are missing");
  return value;
}
