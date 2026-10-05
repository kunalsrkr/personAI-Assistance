import { useEffect, useState } from "react";
import { ArrowLeftRight, Gauge, Library, MessageSquare, Shield } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { ControlsProvider, useControls, type AnswerStyle } from "../controls";

const links = [
  { to: "/", label: "Ask", icon: MessageSquare },
  { to: "/library", label: "Library", icon: Library },
  { to: "/funnel", label: "Funnel", icon: ArrowLeftRight },
];

const quiet = [
  { to: "/security", label: "Security", icon: Shield },
  { to: "/evaluation", label: "Checks", icon: Gauge },
];

const times = [30, 45, 60];
const styles: Array<{ id: AnswerStyle; label: string }> = [
  { id: "brief", label: "Short" },
  { id: "clear", label: "Clear" },
  { id: "full", label: "Full" },
];

export function AppShell() {
  return (
    <ControlsProvider>
      <Frame />
    </ControlsProvider>
  );
}

function Frame() {
  const controls = useControls();
  const [phoneUrl, setPhoneUrl] = useState("");

  useEffect(() => {
    void fetch("/lan.json")
      .then((response) => response.json())
      .then((payload: { url?: string }) => {
        if (payload.url) setPhoneUrl(payload.url);
      })
      .catch(() => undefined);
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden md:flex">
      <aside className="border-b border-stone-800 bg-stone-950 px-3 py-3 md:fixed md:inset-y-0 md:flex md:w-72 md:flex-col md:border-b-0 md:border-r md:px-4 md:py-4">
        <p className="text-xs tracking-[0.28em] text-amber-200/80">ASTERIA</p>
        <p className="mt-1 hidden text-sm text-stone-400 md:block">Ask, then steer the result.</p>
        <nav className="mt-3 flex flex-wrap gap-2 md:mt-5 md:flex-col">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.to === "/"}
              className={({ isActive }) =>
                `flex min-h-11 items-center gap-2 rounded-2xl px-3 py-2 text-sm ${
                  isActive ? "bg-amber-200 text-stone-950" : "text-stone-300 hover:bg-stone-900"
                }`
              }
            >
              <link.icon size={16} />
              {link.label}
            </NavLink>
          ))}
        </nav>

        <details className="mt-3 space-y-4 border-t border-stone-800 pt-3 md:hidden">
          <summary className="cursor-pointer py-2 text-sm text-stone-300">Controls</summary>
          <ControlsBlock controls={controls} />
        </details>
        <div className="mt-6 hidden space-y-4 border-t border-stone-800 pt-5 md:block">
          <ControlsBlock controls={controls} />
        </div>
        <div className="mt-4 flex flex-wrap gap-3 text-xs text-stone-500 md:mt-auto md:flex-col">
          {quiet.map((link) => (
            <NavLink key={link.to} to={link.to} className="hover:text-stone-300">
              {link.label}
            </NavLink>
          ))}
          {phoneUrl ? <p className="break-all">Phone: {phoneUrl}</p> : null}
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-3 py-4 md:ml-72 md:px-8 md:py-6">
        <Outlet />
      </main>
    </div>
  );
}

function ControlsBlock({ controls }: { controls: ReturnType<typeof useControls> }) {
  return (
    <>
      <label className="block text-xs text-stone-400">
        Model
        <select
          value={controls.model}
          onChange={(event) => controls.setModel(event.target.value)}
          className="mt-1 w-full rounded-xl border border-stone-700 bg-stone-900 px-3 py-3 text-base text-stone-100 md:py-2 md:text-sm"
        >
          {controls.models.length === 0 ? <option value="">No local models</option> : null}
          {controls.models.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>
      <div>
        <p className="text-xs text-stone-400">Stay in front</p>
        <p className="mt-1 text-[11px] leading-4 text-stone-500">After this, a slow answer keeps working in the session.</p>
        <div className="mt-1 grid grid-cols-3 gap-1">
          {times.map((seconds) => (
            <button
              key={seconds}
              type="button"
              onClick={() => controls.setTimeLimit(seconds)}
              className={`min-h-11 rounded-xl py-2 text-sm ${
                controls.timeLimit === seconds ? "bg-amber-200 text-stone-950" : "bg-stone-900 text-stone-300"
              }`}
            >
              {seconds}s
            </button>
          ))}
        </div>
      </div>
      <div>
        <p className="text-xs text-stone-400">Answer length</p>
        <div className="mt-1 grid grid-cols-3 gap-1">
          {styles.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => controls.setStyle(item.id)}
              className={`min-h-11 rounded-xl py-2 text-sm ${
                controls.style === item.id ? "bg-emerald-200 text-stone-950" : "bg-stone-900 text-stone-300"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
