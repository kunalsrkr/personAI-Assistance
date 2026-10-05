import { useEffect, useRef, useState } from "react";
import Hls from "hls.js";

export type PlayerState = {
  name: string;
  url: string;
  kind: "video" | "audio" | "image";
  stream?: boolean;
  note?: string;
};

export function mediaKind(name: string): "video" | "audio" | "image" | "" {
  const ext = name.split(".").pop()?.toLowerCase() || "";
  if (["mp4", "mkv", "mov", "m4v", "webm", "avi"].includes(ext)) return "video";
  if (["mp3", "wav", "m4a", "ogg", "aac", "flac"].includes(ext)) return "audio";
  if (["jpg", "jpeg", "png", "gif", "webp"].includes(ext)) return "image";
  return "";
}

function phoneNeedsStream(name: string) {
  const ext = name.split(".").pop()?.toLowerCase() || "";
  return ext === "mkv" || ext === "avi";
}

export async function queuePlayback(name: string, fileRoot: number, filePath: string, setPlayer: (player: PlayerState) => void) {
  const kind = mediaKind(name);
  if (!kind) return;
  const direct = `/api/v1/funnel/play?root=${fileRoot}&path=${encodeURIComponent(filePath)}`;
  if (kind === "video" && phoneNeedsStream(name)) {
    setPlayer({ name, url: "", kind, stream: true, note: "Preparing this movie so it can play here." });
    const response = await fetch(`/api/v1/funnel/play/session?root=${fileRoot}&path=${encodeURIComponent(filePath)}`, { method: "POST" });
    const payload = (await response.json().catch(() => ({}))) as { playlist?: string; mode?: string; detail?: string };
    if (!response.ok || !payload.playlist) {
      setPlayer({ name, url: "", kind, stream: true, note: payload.detail || "This movie could not be prepared." });
      return;
    }
    setPlayer({
      name,
      url: payload.playlist,
      kind,
      stream: true,
      note: payload.mode === "copy" ? "Same picture. Nothing is saved on the phone." : "Converting this file so it can play here.",
    });
    return;
  }
  setPlayer({ name, url: direct, kind, note: "Playing the original file." });
}

export function MediaPlayer({ player, onClose }: { player: PlayerState; onClose: () => void }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 max-h-[78vh] overflow-auto border-t border-stone-700 bg-stone-950 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shadow-2xl">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-center justify-between gap-3 text-sm text-stone-200">
          <p className="min-w-0 truncate">{player.name}</p>
          <button type="button" className="min-h-11 shrink-0 px-2 text-amber-200" onClick={onClose}>
            Close
          </button>
        </div>
        {player.kind === "video" && player.url ? <Movie url={player.url} stream={player.stream} /> : null}
        {player.kind === "audio" && player.url ? <audio key={player.url} controls autoPlay className="mt-2 w-full" src={player.url} /> : null}
        {player.kind === "image" && player.url ? (
          <img key={player.url} alt={player.name} className="mt-2 max-h-[46vh] w-full object-contain" src={player.url} />
        ) : null}
        {player.note ? <p className="mt-2 text-xs leading-5 text-stone-400">{player.note}</p> : null}
      </div>
    </div>
  );
}

function Movie({ url, stream }: { url: string; stream?: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    setError("");
    let hls: Hls | null = null;
    const fail = () => setError("This could not play here. In the Funnel, use Send to phone and open it in the phone video app.");
    if (stream && Hls.isSupported()) {
      hls = new Hls({ manifestLoadingMaxRetry: 8 });
      hls.loadSource(url);
      hls.attachMedia(video);
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) fail();
      });
    } else {
      video.src = url;
      video.onerror = fail;
    }
    return () => {
      hls?.destroy();
      video.onerror = null;
      video.removeAttribute("src");
      video.load();
    };
  }, [url, stream]);

  return (
    <div>
      <video ref={videoRef} controls playsInline preload="metadata" className="mt-2 max-h-[46vh] w-full bg-black" />
      <button
        type="button"
        className="mt-2 min-h-11 rounded-xl bg-emerald-200 px-4 text-sm font-medium text-stone-950"
        onClick={() => void videoRef.current?.play()}
      >
        Start
      </button>
      {error ? <p className="mt-2 text-sm text-rose-200">{error}</p> : null}
    </div>
  );
}
