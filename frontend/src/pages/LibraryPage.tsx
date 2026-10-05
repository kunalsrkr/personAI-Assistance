import { FormEvent, useEffect, useRef, useState } from "react";

type LibraryItem = {
  id: string;
  kind: string;
  original_name: string;
  mime: string;
  bytes: number;
  source: string;
  note: string;
  transcript_id: string;
  created_at: string;
  relative_path?: string;
};

type Transcript = { transcript_id: string; media_id: string; text: string; method: string } | null;

export function LibraryPage() {
  const fileInput = useRef<HTMLInputElement>(null);
  const preview = useRef<HTMLVideoElement>(null);
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [note, setNote] = useState("");
  const [mode, setMode] = useState<"idle" | "audio" | "video" | "photo">("idle");
  const [status, setStatus] = useState("");
  const [openTranscript, setOpenTranscript] = useState<Transcript>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const words = useRef<string[]>([]);
  const discard = useRef(false);

  async function refresh() {
    const response = await fetch("/api/v1/library/items");
    const payload = (await response.json()) as { items: LibraryItem[] };
    setItems(payload.items);
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!preview.current || !stream.current || mode === "idle" || mode === "audio") return;
    preview.current.srcObject = stream.current;
    void preview.current.play();
  }, [mode]);

  async function send(blob: Blob, filename: string, kind: string, source: string, transcript = "") {
    const body = new FormData();
    body.append("file", blob, filename);
    body.append("kind", kind);
    body.append("source", source);
    body.append("note", note);
    body.append("transcript", transcript);
    const response = await fetch("/api/v1/library/items", { method: "POST", body });
    if (!response.ok) {
      setStatus(await response.text());
      return;
    }
    setNote("");
    setStatus("Saved to the library.");
    await refresh();
  }

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    const files = fileInput.current?.files;
    if (!files?.length) return;
    for (const file of files) {
      await send(file, file.name, kindFor(file), "upload");
    }
    if (fileInput.current) fileInput.current.value = "";
  }

  async function startCapture(next: "audio" | "video" | "photo") {
    setStatus("");
    words.current = [];
    const media = await navigator.mediaDevices.getUserMedia({
      audio: next !== "photo",
      video: next !== "audio",
    });
    stream.current = media;
    if (next === "photo") {
      setMode("photo");
      return;
    }
    const mime = next === "audio" ? "audio/webm" : "video/webm";
    const mediaRecorder = new MediaRecorder(media, MediaRecorder.isTypeSupported(mime) ? { mimeType: mime } : undefined);
    const recognition = listen();
    const chunks: Blob[] = [];
    mediaRecorder.ondataavailable = (item) => {
      if (item.data.size) chunks.push(item.data);
    };
    mediaRecorder.onstop = () => {
      recognition?.stop();
      const skipped = discard.current;
      discard.current = false;
      stopTracks();
      if (skipped) return;
      const blob = new Blob(chunks, { type: mediaRecorder.mimeType || mime });
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      void send(blob, `${next}-${stamp}.webm`, next, "capture", words.current.join(" ").trim());
    };
    recorder.current = mediaRecorder;
    mediaRecorder.start();
    setMode(next);
  }

  function takePhoto() {
    const video = preview.current;
    if (!video) return;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth || 1280;
    canvas.height = video.videoHeight || 720;
    canvas.getContext("2d")?.drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return;
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      void send(blob, `photo-${stamp}.jpg`, "image", "capture");
      stopTracks();
      setMode("idle");
    }, "image/jpeg", 0.9);
  }

  function stopRecording() {
    recorder.current?.stop();
    setMode("idle");
  }

  function stopTracks() {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    if (preview.current) preview.current.srcObject = null;
  }

  function listen() {
    const Speech = (window as unknown as { SpeechRecognition?: new () => SpeechRec; webkitSpeechRecognition?: new () => SpeechRec })
      .SpeechRecognition || (window as unknown as { webkitSpeechRecognition?: new () => SpeechRec }).webkitSpeechRecognition;
    if (!Speech) return null;
    const recognition = new Speech();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      words.current = [];
      for (let index = 0; index < event.results.length; index += 1) {
        words.current.push(event.results[index][0].transcript);
      }
    };
    recognition.start();
    return recognition;
  }

  async function showTranscript(id: string) {
    const response = await fetch(`/api/v1/library/items/${id}`);
    const payload = (await response.json()) as { transcript: Transcript };
    setOpenTranscript(payload.transcript);
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <div>
        <p className="text-[11px] uppercase tracking-[0.22em] text-amber-200/80">Library</p>
        <h2 className="mt-1 text-2xl font-medium text-white">Upload or capture</h2>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">
          Files, photos, audio, and video are stored in the library with metadata and an embedding. A recording keeps its transcript in a separate file linked to the media.
        </p>
      </div>

      <form onSubmit={onUpload} className="space-y-3 rounded-3xl border border-white/10 bg-slate-900/60 p-4">
        <input
          ref={fileInput}
          type="file"
          multiple
          accept="image/*,audio/*,video/*,.pdf,.txt,.md,.docx,.csv"
          className="block w-full max-w-full text-sm text-slate-300 file:mr-3 file:rounded-full file:border-0 file:bg-amber-200 file:px-4 file:py-3 file:text-sm file:font-medium file:text-stone-950"
        />
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Place or note. A place becomes part of the saved file name"
          className="w-full rounded-2xl border border-slate-700 bg-slate-950 px-4 py-3 text-base md:text-sm"
        />
        <div className="flex flex-wrap gap-2">
          <button type="submit" className="rounded-2xl bg-amber-200 px-4 py-3 text-sm font-medium text-stone-950">
            Upload
          </button>
          <button type="button" onClick={() => void startCapture("photo")} className="rounded-2xl border border-white/15 px-4 py-3 text-sm">
            Take photo
          </button>
          <button type="button" onClick={() => void startCapture("audio")} className="rounded-2xl border border-white/15 px-4 py-3 text-sm">
            Record audio
          </button>
          <button type="button" onClick={() => void startCapture("video")} className="rounded-2xl border border-white/15 px-4 py-3 text-sm">
            Record video
          </button>
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <CaptureInput label="Phone camera" accept="image/*" capture="environment" kind="image" onFile={(file) => void send(file, file.name, "image", "capture")} />
          <CaptureInput label="Phone microphone" accept="audio/*" capture="user" kind="audio" onFile={(file) => void send(file, file.name, "audio", "capture")} />
          <CaptureInput label="Phone video" accept="video/*" capture="environment" kind="video" onFile={(file) => void send(file, file.name, "video", "capture")} />
        </div>
        {status ? <p className="text-sm text-amber-100">{status}</p> : null}
      </form>

      {mode !== "idle" ? (
        <div className="rounded-3xl border border-amber-200/30 bg-amber-200/10 p-4">
          <video ref={preview} className={`mb-3 w-full rounded-2xl bg-black ${mode === "audio" ? "hidden" : ""}`} muted playsInline />
          <p className="text-sm text-white">{mode === "photo" ? "Frame the photo, then capture." : `Recording ${mode}. Speak normally so a transcript can be saved.`}</p>
          <div className="mt-3 flex gap-2">
            {mode === "photo" ? (
              <button type="button" onClick={takePhoto} className="rounded-2xl bg-white px-4 py-2 text-sm text-slate-950">
                Capture
              </button>
            ) : (
              <button type="button" onClick={stopRecording} className="rounded-2xl bg-white px-4 py-2 text-sm text-slate-950">
                Stop and save
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                discard.current = true;
                if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
                else stopTracks();
                setMode("idle");
              }}
              className="rounded-2xl border border-white/20 px-4 py-2 text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      <ul className="grid gap-3 sm:grid-cols-2">
        {items.map((item) => (
          <li key={item.id} className="rounded-3xl border border-white/10 bg-stone-950 p-4">
            {item.kind === "image" ? (
              <img src={`/api/v1/library/items/${item.id}/file`} alt={item.original_name} className="mb-3 h-36 w-full rounded-2xl object-cover" />
            ) : null}
            <p className="text-[10px] uppercase tracking-[0.16em] text-amber-200">{item.kind} · {item.source}</p>
            <p className="mt-1 break-words text-sm text-white">{item.original_name}</p>
            <p className="text-xs text-slate-500">{Math.ceil(item.bytes / 1024)} KB</p>
            {item.relative_path ? <p className="mt-1 break-all text-xs text-stone-500">{item.relative_path}</p> : null}
            {item.note ? <p className="mt-2 text-sm text-slate-300">{item.note}</p> : null}
            {item.transcript_id ? (
              <button type="button" onClick={() => void showTranscript(item.id)} className="mt-3 text-sm text-amber-200">
                Open linked transcript
              </button>
            ) : null}
          </li>
        ))}
      </ul>
      {openTranscript ? (
        <article className="rounded-3xl border border-white/10 p-4">
          <p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">
            Transcript {openTranscript.transcript_id} · media {openTranscript.media_id} · {openTranscript.method}
          </p>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-200">{openTranscript.text || "No words captured yet. The transcript file is linked and waiting."}</p>
        </article>
      ) : null}
    </div>
  );
}

function CaptureInput({
  label,
  accept,
  capture,
  onFile,
}: {
  label: string;
  accept: string;
  capture: "environment" | "user";
  kind: string;
  onFile: (file: File) => void;
}) {
  return (
    <label className="rounded-2xl border border-dashed border-white/15 px-3 py-3 text-center text-xs text-slate-300">
      {label}
      <input
        type="file"
        accept={accept}
        capture={capture}
        className="mt-2 block w-full text-xs"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) onFile(file);
          event.target.value = "";
        }}
      />
    </label>
  );
}

function kindFor(file: File) {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("audio/")) return "audio";
  if (file.type.startsWith("video/")) return "video";
  return "file";
}

type SpeechRec = {
  continuous: boolean;
  interimResults: boolean;
  onresult: (event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void;
  start: () => void;
  stop: () => void;
};
