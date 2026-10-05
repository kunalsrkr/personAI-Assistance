export type AskLanguage = {
  id: string;
  label: string;
  speech: string;
};

export const ASK_LANGUAGES: AskLanguage[] = [
  { id: "en", label: "English", speech: "en-IN" },
  { id: "hi", label: "Hindi", speech: "hi-IN" },
  { id: "bn", label: "Bengali", speech: "bn-IN" },
  { id: "mr", label: "Marathi", speech: "mr-IN" },
  { id: "ta", label: "Tamil", speech: "ta-IN" },
  { id: "te", label: "Telugu", speech: "te-IN" },
  { id: "kn", label: "Kannada", speech: "kn-IN" },
  { id: "ml", label: "Malayalam", speech: "ml-IN" },
  { id: "ja", label: "Japanese", speech: "ja-JP" },
];

type SpeechResultList = ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;

type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((event: { resultIndex: number; results: SpeechResultList }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

function recognitionCtor(): (new () => Recognition) | null {
  const host = window as Window & {
    SpeechRecognition?: new () => Recognition;
    webkitSpeechRecognition?: new () => Recognition;
  };
  return host.SpeechRecognition || host.webkitSpeechRecognition || null;
}

function mimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) return "audio/webm;codecs=opus";
  if (MediaRecorder.isTypeSupported("audio/webm")) return "audio/webm";
  if (MediaRecorder.isTypeSupported("audio/mp4")) return "audio/mp4";
  return "";
}

async function transcribeBlob(blob: Blob, lang: string): Promise<string> {
  const body = new FormData();
  const suffix = blob.type.includes("mp4") ? "m4a" : "webm";
  body.append("audio", blob, `speech.${suffix}`);
  body.append("language", lang.slice(0, 2));
  const response = await fetch("/api/v1/transcribe", { method: "POST", body });
  if (!response.ok) {
    let detail = "";
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail || "";
    } catch {
      detail = "";
    }
    throw new Error(detail || "This computer recorded the question but could not turn it into text.");
  }
  const payload = (await response.json()) as { text?: string };
  return payload.text?.trim() || "";
}

export function listen(
  lang: string,
  onPartial: (text: string) => void,
  onStatus?: (text: string) => void,
): { stop: () => void; done: Promise<string> } {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    return {
      stop() {},
      done: Promise.reject(new Error("Use Chrome on this computer to record. The phone page needs a secure address before the mic can open.")),
    };
  }

  let settled = false;
  let stopped = false;
  let cloudDown = false;
  let micDown = !navigator.mediaDevices?.getUserMedia;
  let cloudText = "";
  let requestStop = () => {};
  let recorder: MediaRecorder | null = null;
  let stream: MediaStream | null = null;
  let timer = 0;
  let audio: AudioContext | null = null;
  const chunks: Blob[] = [];
  const Ctor = recognitionCtor();
  const recognition = Ctor ? new Ctor() : null;

  const done = new Promise<string>((resolve, reject) => {
    const finish = (text: string) => {
      if (settled) return;
      const trimmed = text.trim();
      if (!trimmed) return;
      settled = true;
      cleanup();
      resolve(trimmed);
    };
    const giveUp = (message: string) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(new Error(message));
    };
    const cleanup = () => {
      window.clearInterval(timer);
      try {
        recognition?.abort();
      } catch {
        /* already stopped */
      }
      stream?.getTracks().forEach((track) => track.stop());
      void audio?.close();
    };
    const transcribeRecording = () => {
      if (settled) return;
      if (cloudText) {
        finish(cloudText);
        return;
      }
      const blob = new Blob(chunks, { type: recorder?.mimeType || "audio/webm" });
      if (blob.size < 800) {
        giveUp("No speech was heard. Speak, then click Stop.");
        return;
      }
      onStatus?.("Turning speech into text. The first time can take a minute.");
      void transcribeBlob(blob, lang)
        .then((text) => {
          if (text) finish(text);
          else giveUp("No speech was heard. Speak, then click Stop.");
        })
        .catch((error: unknown) => {
          giveUp(error instanceof Error ? error.message : "Speech recognition stopped.");
        });
    };
    const beginRecording = (live: MediaStream) => {
      stream = live;
      const mime = mimeType();
      recorder = mime ? new MediaRecorder(live, { mimeType: mime }) : new MediaRecorder(live);
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onstop = () => transcribeRecording();
      recorder.start(250);
      const context = new AudioContext();
      audio = context;
      void context.resume();
      const source = context.createMediaStreamSource(live);
      const analyser = context.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      let loudTicks = 0;
      let heard = false;
      let quiet = 0;
      timer = window.setInterval(() => {
        if (settled || stopped) return;
        analyser.getByteTimeDomainData(samples);
        let energy = 0;
        for (const sample of samples) {
          const value = (sample - 128) / 128;
          energy += value * value;
        }
        const level = Math.sqrt(energy / samples.length);
        if (level > 0.045) {
          loudTicks += 1;
          quiet = 0;
          if (loudTicks >= 3) heard = true;
        } else {
          loudTicks = 0;
          if (heard) {
            quiet += 200;
            if (quiet >= 1600 && recorder && recorder.state === "recording") {
              stopped = true;
              recorder.stop();
            }
          }
        }
      }, 200);
    };

    if (recognition) {
      recognition.lang = lang;
      recognition.interimResults = true;
      recognition.continuous = true;
      recognition.onresult = (event) => {
        let text = "";
        for (let index = 0; index < event.results.length; index += 1) {
          text += event.results[index][0]?.transcript || "";
        }
        cloudText = text.trim();
        if (cloudText) onPartial(cloudText);
      };
      recognition.onerror = (event) => {
        if (settled) return;
        if (event.error === "not-allowed" && !stream) {
          micDown = true;
          if (cloudDown || !recorder) giveUp("Allow the microphone for this page, then try the mic again.");
          return;
        }
        if (event.error === "network" || event.error === "service-not-allowed") {
          cloudDown = true;
          onStatus?.("Listening on this computer. Click Stop when you finish.");
          if (micDown) giveUp("Allow the microphone for this page, then try the mic again.");
        }
      };
      try {
        recognition.start();
      } catch {
        onStatus?.("Listening on this computer. Click Stop when you finish.");
      }
    }

    navigator.mediaDevices
      .getUserMedia({ audio: true })
      .then((live) => {
        if (settled) {
          live.getTracks().forEach((track) => track.stop());
          return;
        }
        beginRecording(live);
        onStatus?.(cloudDown ? "Listening on this computer. Click Stop when you finish." : "Listening. Click Stop when you finish.");
      })
      .catch(() => {
        micDown = true;
        if (cloudDown || !recognition) giveUp("Allow the microphone for this page, then try the mic again.");
      });

    requestStop = () => {
      stopped = true;
      if (recorder && recorder.state === "recording") recorder.stop();
      else if (cloudText) finish(cloudText);
      else window.setTimeout(() => transcribeRecording(), 300);
    };
  });

  return {
    stop() {
      requestStop();
    },
    done,
  };
}

type BuiltInTranslator = {
  availability: (options: { sourceLanguage: string; targetLanguage: string }) => Promise<string>;
  create: (options: { sourceLanguage: string; targetLanguage: string }) => Promise<{ translate: (text: string) => Promise<string> }>;
};

function within<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => resolve(null), ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      () => {
        window.clearTimeout(timer);
        resolve(null);
      },
    );
  });
}

async function translateLocal(text: string, source: string, target: string): Promise<string | null> {
  const host = window as Window & { Translator?: BuiltInTranslator };
  if (!host.Translator?.availability) return null;
  const state = await within(host.Translator.availability({ sourceLanguage: source, targetLanguage: target }), 400);
  if (state !== "available") return null;
  const translator = await within(host.Translator.create({ sourceLanguage: source, targetLanguage: target }), 800);
  if (!translator) return null;
  return within(translator.translate(text), 1500);
}

export async function translateText(text: string, source: string, target: string): Promise<string> {
  if (source === target) return text;
  const local = await translateLocal(text, source, target).catch(() => null);
  if (local?.trim()) return local.trim();
  const response = await fetch("/api/v1/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, source, target }),
  });
  if (!response.ok) throw new Error("Translation did not finish. The question was kept in the original language.");
  const payload = (await response.json()) as { text?: string };
  if (!payload.text?.trim()) throw new Error("Translation came back empty.");
  return payload.text.trim();
}

export function speakText(text: string, lang: string) {
  if (!window.speechSynthesis || !text.trim()) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text.slice(0, 3500));
  utterance.lang = lang;
  utterance.rate = 1;
  const voice = window.speechSynthesis.getVoices().find((item) => item.lang.toLowerCase().startsWith(lang.slice(0, 2).toLowerCase()));
  if (voice) utterance.voice = voice;
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking() {
  window.speechSynthesis?.cancel();
}

export function hasVoice(lang: string): boolean {
  const prefix = lang.slice(0, 2).toLowerCase();
  return window.speechSynthesis?.getVoices().some((item) => item.lang.toLowerCase().startsWith(prefix)) ?? false;
}

export function savedLanguage(): AskLanguage {
  const stored = localStorage.getItem("asteria-language") || "en";
  return ASK_LANGUAGES.find((item) => item.id === stored) || ASK_LANGUAGES[0];
}
