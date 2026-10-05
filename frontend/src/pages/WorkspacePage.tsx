import { FormEvent, useEffect, useRef, useState } from "react";
import { Mic, Volume2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { AgentFlow } from "../components/AgentFlow";
import { MediaPlayer, PlayerState, queuePlayback } from "../components/MediaPlayer";
import { LinkedText, SourceTitle } from "../components/SourceLink";
import { useControls } from "../controls";
import { ASK_LANGUAGES, hasVoice, listen, savedLanguage, speakText, stopSpeaking, translateText, type AskLanguage } from "../speech";
import { useQueryClient } from "@tanstack/react-query";
import { useCreateInvestigation, useThread, useThreads } from "../hooks/useInvestigations";
import { useInvestigationStream } from "../hooks/useInvestigationStream";

export function WorkspacePage() {
  const controls = useControls();
  const [params, setParams] = useSearchParams();
  const id = params.get("id") || undefined;
  const threadId = params.get("thread") || undefined;
  const [query, setQuery] = useState("");
  const [choosing, setChoosing] = useState("");
  const [site, setSite] = useState("");
  const [kept, setKept] = useState("");
  const [left, setLeft] = useState<number | null>(null);
  const [chooseLeft, setChooseLeft] = useState(20);
  const [player, setPlayer] = useState<PlayerState | null>(null);
  const [language, setLanguage] = useState<AskLanguage>(savedLanguage);
  const [hear, setHear] = useState(() => localStorage.getItem("asteria-hear") === "1");
  const [listening, setListening] = useState(false);
  const [voiceNote, setVoiceNote] = useState("");
  const [heard, setHeard] = useState("");
  const [spoken, setSpoken] = useState<{ id: string; text: string } | null>(null);
  const [voiceReady, setVoiceReady] = useState(() => hasVoice(savedLanguage().speech));
  const listenRef = useRef<{ stop: () => void } | null>(null);
  const spokenFor = useRef("");
  const queryClient = useQueryClient();
  const { data: threadList } = useThreads();
  const { data: topic } = useThread(threadId);
  const createInvestigation = useCreateInvestigation();
  const live = useInvestigationStream(id);
  const data = live.query.data;
  const running = live.status === "RUNNING";
  const sources = live.sources.length ? live.sources : data?.sources || [];
  const answer = live.answer || data?.final_answer || "";
  const stages = live.stages.length ? live.stages : data?.stages || [];
  const budget = data?.time_limit || controls.timeLimit;

  useEffect(() => {
    if (!live.deadline || !running) return;
    const end = new Date(live.deadline).getTime();
    const tick = () => setLeft(Math.max(0, Math.ceil((end - Date.now()) / 1000)));
    tick();
    const timer = window.setInterval(tick, 250);
    return () => window.clearInterval(timer);
  }, [live.deadline, running]);

  useEffect(() => {
    if (!live.clarify) return;
    const seconds = live.clarify.seconds || 20;
    const started = Date.now();
    const tick = () => setChooseLeft(Math.max(0, seconds - Math.round((Date.now() - started) / 1000)));
    tick();
    const timer = window.setInterval(tick, 250);
    return () => window.clearInterval(timer);
  }, [live.clarify]);

  useEffect(() => {
    if (live.status !== "COMPLETED") return;
    void queryClient.invalidateQueries({ queryKey: ["threads"] });
  }, [live.status, id, queryClient]);

  useEffect(() => {
    const refresh = () => setVoiceReady(hasVoice(language.speech));
    refresh();
    window.speechSynthesis?.addEventListener("voiceschanged", refresh);
    return () => window.speechSynthesis?.removeEventListener("voiceschanged", refresh);
  }, [language.speech]);

  useEffect(() => {
    if (live.status !== "COMPLETED" || !id || !answer) return;
    if (language.id === "en") {
      setSpoken({ id, text: answer });
      return;
    }
    let cancel = false;
    void translateText(answer, "en", language.id)
      .then((text) => {
        if (!cancel) setSpoken({ id, text });
      })
      .catch(() => {
        if (!cancel) setSpoken({ id, text: answer });
      });
    return () => {
      cancel = true;
    };
  }, [live.status, id, answer, language.id]);

  useEffect(() => {
    if (!hear || !id || spoken?.id !== id || !spoken.text) return;
    if (spokenFor.current === id) return;
    spokenFor.current = id;
    speakText(spoken.text, language.speech);
  }, [hear, id, spoken, language.speech]);

  async function send(text: string) {
    stopSpeaking();
    spokenFor.current = "";
    const created = await createInvestigation.mutateAsync({
      query: text,
      model: controls.model,
      timeLimit: controls.timeLimit,
      style: controls.style,
      threadId,
    });
    setParams({ thread: created.thread_id || threadId || "", id: created.id });
    setQuery("");
    setSpoken(null);
  }

  async function prepare(text: string) {
    const trimmed = text.trim();
    if (trimmed.length < 3) return;
    if (language.id === "en") {
      setHeard("");
      await send(trimmed);
      return;
    }
    setVoiceNote(`Translating from ${language.label}…`);
    try {
      const english = await translateText(trimmed, language.id, "en");
      setHeard(trimmed);
      setVoiceNote("");
      await send(english);
    } catch (error) {
      setVoiceNote(error instanceof Error ? error.message : "Translation stopped.");
      setHeard(trimmed);
      await send(trimmed);
    }
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    await prepare(query);
  }

  async function onMic() {
    if (listenRef.current) {
      listenRef.current.stop();
      return;
    }
    setVoiceNote(`Listening in ${language.label}. Click Stop when you finish.`);
    setListening(true);
    const session = listen(language.speech, (partial) => setQuery(partial), setVoiceNote);
    listenRef.current = session;
    try {
      const spokenText = (await session.done).trim();
      listenRef.current = null;
      setListening(false);
      setQuery(spokenText);
      setVoiceNote("");
      await prepare(spokenText);
    } catch (error) {
      listenRef.current = null;
      setListening(false);
      setVoiceNote(error instanceof Error ? error.message : "The microphone stopped.");
    }
  }

  async function restore(checkpointId: string) {
    if (!threadId) return;
    await api.restoreThread(threadId, checkpointId);
    void queryClient.invalidateQueries({ queryKey: ["threads"] });
  }

  async function pick(choiceId: string, note = "") {
    if (!id) return;
    setChoosing(choiceId);
    try {
      await api.choose(id, choiceId, note);
      setSite("");
    } finally {
      setChoosing("");
    }
  }

  async function retry(choiceId: string) {
    if (!id) return;
    if (choiceId === "keep") {
      setKept(id);
      return;
    }
    setChoosing(choiceId);
    try {
      const created = await api.retry(id, choiceId);
      if (created.id !== id) setParams({ id: created.id });
    } finally {
      setChoosing("");
    }
  }

  const voiced = spoken && spoken.id === id ? spoken.text : "";
  const fraction = left === null ? 1 : Math.max(0, Math.min(1, left / budget));
  const stillWorking = Boolean(id) && running && (live.parked || left === 0);

  return (
    <div className="mx-auto grid max-w-6xl items-start gap-6 xl:grid-cols-[minmax(0,1fr)_17rem]">
      <div className="min-w-0">
      <form onSubmit={onSubmit}>
        <textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          rows={3}
          placeholder="List Hindi movies, songs, or images, or ask about files, mail, the weather, or a paper"
          className="w-full resize-none rounded-3xl border border-stone-700 bg-stone-900/80 px-5 py-4 text-base outline-none focus:border-amber-200"
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="min-w-0 text-xs text-stone-500">
            Language
            <select
              value={language.id}
              onChange={(event) => {
                const next = ASK_LANGUAGES.find((item) => item.id === event.target.value) || ASK_LANGUAGES[0];
                setLanguage(next);
                localStorage.setItem("asteria-language", next.id);
                stopSpeaking();
                spokenFor.current = "";
              }}
              className="ml-2 min-h-11 rounded-full border border-stone-700 bg-stone-900 px-3 text-sm text-stone-100"
            >
              {ASK_LANGUAGES.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => void onMic()}
            className={`inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm ${listening ? "bg-rose-300 text-stone-950" : "bg-stone-800 text-stone-100"}`}
          >
            <Mic size={16} />
            {listening ? "Stop" : "Mic"}
          </button>
          <button
            type="button"
            onClick={() => {
              const next = !hear;
              setHear(next);
              localStorage.setItem("asteria-hear", next ? "1" : "0");
              if (!next) stopSpeaking();
              else if (spoken?.text) {
                spokenFor.current = spoken.id;
                speakText(spoken.text, language.speech);
              }
            }}
            className={`inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm ${hear ? "bg-emerald-200 text-stone-950" : "bg-stone-800 text-stone-100"}`}
          >
            <Volume2 size={16} />
            {hear ? "Voice on" : "Voice"}
          </button>
          <LinkedInConnect />
          <button
            type="submit"
            disabled={createInvestigation.isPending}
            className="ml-auto min-h-11 rounded-full bg-amber-200 px-5 py-2 text-sm font-medium text-stone-950 disabled:opacity-50"
          >
            {createInvestigation.isPending ? "Starting" : "Ask"}
          </button>
        </div>
        {params.get("linkedin") === "connected" ? (
          <p className="mt-2 text-xs text-emerald-200">LinkedIn is connected. A paper question that asks to post will publish the draft.</p>
        ) : null}
        {params.get("linkedin") === "error" ? (
          <p className="mt-2 text-xs text-rose-200">LinkedIn did not connect. {params.get("reason") || "Try Connect LinkedIn again."}</p>
        ) : null}
        <p className="mt-2 min-w-0 break-words text-xs text-stone-500">
          {voiceNote || `${controls.model || "Local model"} · ${controls.timeLimit}s · ${controls.style}`}
          {language.id === "en" ? "" : ` · ${language.label} is translated to English, then the answer comes back in ${language.label}.`}
        </p>
      </form>

      <div className="mt-4 xl:hidden">
        <ThreadList
          threads={threadList?.threads}
          activeId={threadId}
          onOpen={(next, investigationId) => setParams(investigationId ? { thread: next, id: investigationId } : { thread: next })}
          onNew={() => setParams({})}
        />
      </div>

      {id || topic ? (
        <section className="mt-8">
          {topic?.turns?.length ? (
            <div className="mb-6 space-y-3">
              {(answer && topic.turns.at(-1)?.text === answer ? topic.turns.slice(0, -2) : topic.turns).map((turn, index) => (
                <article key={`${turn.at}-${index}`} className={`rounded-2xl px-4 py-3 ${turn.role === "user" ? "bg-stone-800" : "bg-stone-900"}`}>
                  <p className="text-[10px] uppercase tracking-[0.16em] text-amber-200/80">{turn.role === "user" ? "You" : "Thread"}</p>
                  <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-stone-100">
                    <LinkedText text={turn.text} />
                  </p>
                </article>
              ))}
            </div>
          ) : null}
          {topic?.checkpoints?.length ? (
            <div className="mb-5 flex flex-wrap gap-2">
              {topic.checkpoints.map((point) => (
                <button
                  key={point.id}
                  type="button"
                  onClick={() => void restore(point.id)}
                  className={`rounded-full px-3 py-2 text-xs ${point.id === topic.active_checkpoint ? "bg-amber-200 text-stone-950" : "bg-stone-900 text-stone-300"}`}
                >
                  {point.label}
                </button>
              ))}
            </div>
          ) : null}
          {heard ? <p className="break-words text-sm text-stone-400">Heard in {language.label}: {heard}</p> : null}
          {id ? <p className="break-words text-lg text-stone-100">{data?.query}</p> : null}

          {stillWorking ? (
            <p className="mt-5 rounded-2xl bg-stone-900 px-4 py-3 text-sm text-amber-100">
              Still working. It stays in this session and will show Completed with the answer. You can ask the next question now.
            </p>
          ) : live.deadline && (running || live.clarify) ? (
            <div className="mt-5">
              <div className="flex justify-between gap-3 text-xs text-stone-400">
                <span className="min-w-0 truncate">{live.hint || "Working"}</span>
                <span className="shrink-0">{left === null ? budget : left}s in front</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-stone-800">
                <div className="h-full rounded-full bg-amber-200 transition-all" style={{ width: `${fraction * 100}%` }} />
              </div>
            </div>
          ) : null}

          <AnimatePresence mode="wait">
            {live.clarify ? (
              <motion.div
                key={live.clarify.prompt}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="mt-5 rounded-3xl bg-amber-200 p-5 text-stone-950"
              >
                <div className="flex items-center justify-between text-xs">
                  <span>
                    Question {live.clarify.step} of {live.clarify.total}
                  </span>
                  <span>{chooseLeft}s to choose</span>
                </div>
                <p className="mt-2 text-xl">{live.clarify.prompt}</p>
                {live.clarify.choices.some((choice) => choice.id === "site_custom") ? (
                  <input
                    value={site}
                    onChange={(event) => setSite(event.target.value)}
                    placeholder="Site name, such as weather.com"
                    className="mt-4 w-full rounded-2xl border border-stone-950/20 bg-white px-4 py-3 text-sm text-stone-950"
                  />
                ) : null}
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {live.clarify.choices.map((choice) => (
                    <button
                      key={choice.id}
                      type="button"
                      disabled={Boolean(choosing) || (choice.id === "site_custom" && site.trim().length < 2)}
                      onClick={() => void pick(choice.id, choice.id === "site_custom" ? site : "")}
                      className="rounded-2xl bg-stone-950/90 px-4 py-3 text-left text-sm text-stone-50 hover:bg-stone-950 disabled:opacity-40"
                    >
                      {choosing === choice.id ? "Using this" : choice.label}
                    </button>
                  ))}
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>

          {answer ? (
            <div className="mt-5">
              <p className="whitespace-pre-wrap text-[15px] leading-7 text-stone-100">
                <LinkedText text={voiced || answer} />
                {running ? <span className="ml-1 inline-block h-4 w-0.5 animate-pulse bg-amber-200 align-middle" /> : null}
              </p>
              {language.id !== "en" && live.status === "COMPLETED" && !voiced ? (
                <p className="mt-2 text-xs text-amber-100">Turning the answer into {language.label}…</p>
              ) : null}
              {voiced ? (
                <button
                  type="button"
                  onClick={() => speakText(voiced, language.speech)}
                  className="mt-3 inline-flex min-h-11 items-center gap-2 text-sm text-emerald-200"
                >
                  <Volume2 size={16} />
                  Hear answer
                </button>
              ) : null}
              {voiced && language.id !== "en" && !voiceReady ? (
                <p className="mt-2 text-xs text-stone-500">
                  This browser has no {language.label} voice installed, so the reading uses another voice. Add {language.label} speech in Windows language settings to hear it clearly.
                </p>
              ) : null}
            </div>
          ) : id && !live.clarify && !live.query.isError ? (
            <p className="mt-5 text-sm text-stone-400">{live.hint || data?.hint || "Connecting"}</p>
          ) : null}

          {live.review && kept !== id ? (
            <div className="mt-5 rounded-3xl border border-amber-200/40 p-5">
              <p className="text-lg text-stone-100">{live.review.prompt}</p>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {live.review.choices.map((choice) => (
                  <button
                    key={choice.id}
                    type="button"
                    disabled={Boolean(choosing)}
                    onClick={() => void retry(choice.id)}
                    className="rounded-2xl bg-stone-900 px-4 py-3 text-left text-sm text-stone-100 hover:bg-stone-800"
                  >
                    {choosing === choice.id ? "Starting again" : choice.label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <div className="mt-6">
            <AgentFlow stages={stages} variant="embedded" />
          </div>
          {stages.length ? (
            <p className="mt-3 text-xs text-stone-500">{stages.map((stage) => stage.label).join("  ·  ")}</p>
          ) : null}

          {sources.length ? (
            <div className="mt-4 grid gap-2">
              {sources.map((source) => (
                <article key={source.source_id} className="rounded-2xl bg-stone-900 px-4 py-3">
                  <p className="text-[10px] uppercase tracking-[0.16em] text-emerald-300">{source.origin || "Source"}</p>
                  <SourceTitle
                    source={source}
                    linkedClassName="text-sm text-emerald-200 underline decoration-emerald-200/40 underline-offset-2"
                    plainClassName="text-sm text-stone-100"
                  />
                  {source.excerpt ? <p className="mt-1 line-clamp-3 text-xs leading-5 text-stone-400">{source.excerpt}</p> : null}
                  {source.play_path && source.play_root != null ? (
                    <button
                      type="button"
                      className="mt-3 inline-flex min-h-11 items-center text-sm text-emerald-200"
                      onClick={() => void queuePlayback(source.title, source.play_root as number, source.play_path || "", setPlayer)}
                    >
                      Play
                    </button>
                  ) : null}
                </article>
              ))}
            </div>
          ) : null}
          {player ? <MediaPlayer player={player} onClose={() => setPlayer(null)} /> : null}
        </section>
      ) : (
        <>
          <p className="mt-10 text-sm text-stone-500">
            The model and answer length sit in the side panel. After the time you chose, a slow answer keeps working in this session so the next question can start.
          </p>
          <div className="mt-6">
            <AgentFlow stages={[]} variant="embedded" />
          </div>
        </>
      )}
      </div>
      <aside className="hidden min-w-0 xl:block">
        <ThreadList
          threads={threadList?.threads}
          activeId={threadId}
          onOpen={(next, investigationId) => setParams(investigationId ? { thread: next, id: investigationId } : { thread: next })}
          onNew={() => setParams({})}
        />
      </aside>
    </div>
  );
}

function LinkedInConnect() {
  const [status, setStatus] = useState<{ connected: boolean; name: string } | null>(null);
  useEffect(() => {
    let cancel = false;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 4000);
    void fetch("/api/v1/linkedin/status", { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((body: { connected?: boolean; name?: string } | null) => {
        if (!cancel && body) setStatus({ connected: Boolean(body.connected), name: body.name || "" });
        else if (!cancel) setStatus({ connected: false, name: "" });
      })
      .catch(() => {
        if (!cancel) setStatus({ connected: false, name: "" });
      })
      .finally(() => window.clearTimeout(timer));
    return () => {
      cancel = true;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, []);
  if (!status) return <span className="inline-flex min-h-11 items-center px-2 text-sm text-stone-500">LinkedIn</span>;
  if (status.connected) {
    return (
      <span className="inline-flex min-h-11 items-center rounded-full bg-stone-800 px-4 text-sm text-emerald-200">
        LinkedIn connected{status.name ? ` · ${status.name}` : ""}
      </span>
    );
  }
  const back = encodeURIComponent(`${window.location.origin}/`);
  return (
    <a href={`/api/v1/linkedin/connect?return_to=${back}`} className="inline-flex min-h-11 items-center rounded-full bg-stone-800 px-4 text-sm text-stone-100">
      Connect LinkedIn
    </a>
  );
}

function ThreadList({
  threads,
  activeId,
  onOpen,
  onNew,
}: {
  threads: Array<{ id: string; title: string; memory: string; latest_investigation_id: string; checkpoints: Array<{ id: string }> }> | undefined;
  activeId?: string;
  onOpen: (id: string, investigationId: string) => void;
  onNew: () => void;
}) {
  return (
    <div className="rounded-3xl bg-stone-900 p-3">
      <div className="flex items-center justify-between gap-2 px-1">
        <p className="text-xs tracking-[0.16em] text-amber-200/80">THREADS</p>
        <button type="button" onClick={onNew} className="min-h-11 text-xs text-amber-200">
          New thread
        </button>
      </div>
      <ul className="mt-2 space-y-2">
        {(threads || []).map((item) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onOpen(item.id, item.latest_investigation_id)}
              className={`w-full rounded-2xl px-3 py-3 text-left ${item.id === activeId ? "bg-stone-100 text-stone-950" : "bg-stone-950 text-stone-200"}`}
            >
              <span className="block break-words text-sm">{item.title}</span>
              <span className={`mt-1 block text-[11px] ${item.id === activeId ? "text-stone-600" : "text-stone-500"}`}>
                {item.checkpoints.length} checkpoint{item.checkpoints.length === 1 ? "" : "s"}
              </span>
              {item.memory ? (
                <span className={`mt-1 block line-clamp-2 text-xs ${item.id === activeId ? "text-stone-600" : "text-stone-400"}`}>{item.memory}</span>
              ) : null}
            </button>
          </li>
        ))}
        {!threads?.length ? <li className="px-2 py-3 text-sm text-stone-500">A new thread starts with the next question.</li> : null}
      </ul>
    </div>
  );
}
