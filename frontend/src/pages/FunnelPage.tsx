import { FormEvent, useEffect, useState } from "react";
import { MediaPlayer, PlayerState, mediaKind, queuePlayback } from "../components/MediaPlayer";

type Entry = {
  name: string;
  kind: "dir" | "file";
  group?: string;
  bytes: number;
  path: string;
  modified?: string;
  movie?: boolean;
  subtitles?: number;
};
type Hit = { root: number; path: string; name: string; type: string };
type InboxFile = { name: string; bytes: number };

export function FunnelPage() {
  const [root, setRoot] = useState(0);
  const [path, setPath] = useState("");
  const [parent, setParent] = useState("");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [inbox, setInbox] = useState<InboxFile[]>([]);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [status, setStatus] = useState("");
  const [phoneUrl, setPhoneUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [player, setPlayer] = useState<PlayerState | null>(null);

  function playEntry(name: string, fileRoot: number, filePath: string) {
    void queuePlayback(name, fileRoot, filePath, setPlayer);
  }

  async function loadInbox() {
    const response = await fetch("/api/v1/funnel/inbox");
    const payload = (await response.json()) as { files: InboxFile[] };
    setInbox(payload.files);
  }

  async function loadFolder(nextRoot = root, nextPath = path) {
    const response = await fetch(`/api/v1/funnel/browse?root=${nextRoot}&path=${encodeURIComponent(nextPath)}`);
    if (!response.ok) {
      setStatus("That folder could not be opened.");
      return;
    }
    const payload = (await response.json()) as { parent: string; entries: Entry[] };
    setRoot(nextRoot);
    setPath(nextPath);
    setParent(payload.parent);
    setEntries(payload.entries);
    setHits([]);
  }

  useEffect(() => {
    void loadFolder(0, "");
    void loadInbox();
    void fetch("/lan.json")
      .then((response) => response.json())
      .then((payload: { url?: string }) => {
        if (payload.url) setPhoneUrl(payload.url);
      })
      .catch(() => undefined);
  }, []);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 2) return;
    setBusy(true);
    setStatus("Looking through this computer.");
    try {
      const response = await fetch(`/api/v1/funnel/search?q=${encodeURIComponent(query.trim())}`);
      const payload = (await response.json()) as { results: Hit[] };
      setHits(payload.results);
      setStatus(payload.results.length ? "" : "No file name matched.");
    } finally {
      setBusy(false);
    }
  }

  async function sendToComputer(file: File) {
    setBusy(true);
    setStatus("Sending to this computer.");
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/v1/funnel/inbox", { method: "POST", body });
      if (!response.ok) {
        setStatus("The file could not be saved on this computer.");
        return;
      }
      const payload = (await response.json()) as { name: string };
      setStatus(`${payload.name} is on the Desktop, in the Asteria folder.`);
      await loadInbox();
    } finally {
      setBusy(false);
    }
  }

  const crumbs = path ? path.split("/") : [];

  return (
    <div className="mx-auto max-w-6xl">
      <p className="text-xs tracking-[0.22em] text-amber-200/80">FUNNEL</p>
      <h2 className="mt-1 text-2xl text-stone-100">Phone and this computer</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-stone-400">
        Send a file, a movie, or a whole movie folder with its subtitles to the phone. A file from the phone is saved in the Asteria folder on the Desktop.
        {phoneUrl ? ` On the phone, open ${phoneUrl}/funnel.` : ""}
      </p>

      <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="rounded-3xl bg-stone-900 p-4">
          <div className="flex flex-wrap items-center gap-2 text-sm break-words">
            <button type="button" onClick={() => void loadFolder(root, "")} className="text-amber-200">
              This computer
            </button>
            {crumbs.map((crumb, index) => {
              const next = crumbs.slice(0, index + 1).join("/");
              return (
                <span key={next} className="flex items-center gap-2">
                  <span className="text-stone-600">/</span>
                  <button type="button" onClick={() => void loadFolder(root, next)} className="max-w-40 truncate text-stone-200">
                    {crumb}
                  </button>
                </span>
              );
            })}
          </div>
          <form onSubmit={onSearch} className="mt-3 flex flex-wrap gap-2">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Find a file by name"
              className="min-w-0 flex-1 basis-40 rounded-xl border border-stone-700 bg-stone-950 px-3 py-3 text-base md:py-2 md:text-sm"
            />
            <button type="submit" disabled={busy} className="min-h-11 rounded-xl bg-amber-200 px-4 py-2 text-sm text-stone-950">
              Find
            </button>
          </form>
          {player ? <MediaPlayer player={player} onClose={() => setPlayer(null)} /> : null}
          {hits.length ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              {hits.map((hit) => (
                <article key={`${hit.root}-${hit.path}`} className="rounded-2xl bg-stone-950 p-4">
                  <p className="text-[10px] uppercase tracking-[0.16em] text-rose-200">{hit.type}</p>
                  <p className="mt-2 truncate text-sm text-stone-100">{hit.name}</p>
                  <div className="mt-3 flex flex-wrap gap-x-3 gap-y-2 text-sm">
                    <button type="button" className="min-h-11 text-stone-400" onClick={() => void loadFolder(hit.root, hit.path.split("/").slice(0, -1).join("/"))}>
                      Show folder
                    </button>
                    <PlayButton name={hit.name} onPlay={() => void playEntry(hit.name, hit.root, hit.path)} />
                    <a className="inline-flex min-h-11 items-center text-amber-200" href={`/api/v1/funnel/file?root=${hit.root}&path=${encodeURIComponent(hit.path)}`}>
                      Send to phone
                    </a>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {path ? (
                <button type="button" onClick={() => void loadFolder(root, parent)} className="rounded-2xl border border-dashed border-stone-700 px-4 py-5 text-left text-sm text-stone-400">
                  Up one folder
                </button>
              ) : null}
              {entries.map((entry) => (
                <article key={entry.path} className={`rounded-2xl p-4 ${entry.movie ? "bg-rose-950/50 ring-1 ring-rose-300/30" : "bg-stone-950"}`}>
                  <p className="text-[10px] uppercase tracking-[0.16em] text-amber-200/80">
                    {entry.movie ? "Movie folder" : entry.group || entry.kind}
                    {entry.subtitles ? ` · ${entry.subtitles} subtitle${entry.subtitles === 1 ? "" : "s"}` : ""}
                  </p>
                  {entry.kind === "dir" ? (
                    <button type="button" onClick={() => void loadFolder(root, entry.path)} className="mt-2 block w-full truncate text-left text-sm text-stone-100">
                      {entry.name}
                    </button>
                  ) : (
                    <p className="mt-2 truncate text-sm text-stone-100">{entry.name}</p>
                  )}
                  <p className="mt-1 text-xs text-stone-500">
                    {entry.kind === "file" ? formatSize(entry.bytes) : "Folder"}
                    {entry.modified ? ` · ${entry.modified.slice(0, 10)}` : ""}
                  </p>
                  <div className="mt-3 flex flex-wrap gap-x-3 gap-y-2 text-sm">
                    {entry.kind === "file" ? (
                      <>
                        <PlayButton name={entry.name} onPlay={() => void playEntry(entry.name, root, entry.path)} />
                        <a className="inline-flex min-h-11 items-center text-amber-200" href={`/api/v1/funnel/file?root=${root}&path=${encodeURIComponent(entry.path)}`}>
                          Send to phone
                        </a>
                      </>
                    ) : (
                      <a className="inline-flex min-h-11 items-center text-amber-200" href={`/api/v1/funnel/folder?root=${root}&path=${encodeURIComponent(entry.path)}`}>
                        {entry.movie ? "Send movie folder" : "Send folder"}
                      </a>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="rounded-3xl bg-stone-900 p-4">
          <h3 className="text-sm text-stone-100">To this computer</h3>
          <p className="mt-1 text-xs text-stone-500">A file chosen here, including from the phone camera, is saved in Desktop/Asteria.</p>
          <label className="mt-3 block rounded-2xl border border-dashed border-stone-700 px-4 py-6 text-center text-sm text-stone-300">
            Choose a file on this phone or computer
            <input
              type="file"
              className="mt-3 block w-full text-xs"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void sendToComputer(file);
                event.target.value = "";
              }}
            />
          </label>
          <ul className="mt-4 space-y-2">
            {inbox.map((file) => (
              <li key={file.name} className="flex items-center justify-between gap-3 rounded-2xl bg-stone-950 px-3 py-2">
                <span className="min-w-0 truncate text-sm">{file.name}</span>
                <a className="shrink-0 text-xs text-amber-200" href={`/api/v1/funnel/inbox/${encodeURIComponent(file.name)}`}>
                  Open
                </a>
              </li>
            ))}
            {!inbox.length ? <li className="text-sm text-stone-500">Nothing has been sent to the computer yet.</li> : null}
          </ul>
          {status ? <p className="mt-3 text-sm text-amber-100">{status}</p> : null}
        </section>
      </div>
    </div>
  );
}

function PlayButton({ name, onPlay }: { name: string; onPlay: () => void }) {
  if (!mediaKind(name)) return null;
  return (
    <button type="button" className="inline-flex min-h-11 items-center text-emerald-200" onClick={onPlay}>
      Play
    </button>
  );
}

function formatSize(bytes: number) {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (bytes >= 1024 * 1024) return `${Math.ceil(bytes / (1024 * 1024))} MB`;
  return `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
}
