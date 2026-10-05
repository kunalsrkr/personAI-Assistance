import os from "node:os";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

function lanAddresses(): string[] {
  const ips: string[] = [];
  for (const entries of Object.values(os.networkInterfaces())) {
    for (const entry of entries ?? []) {
      const family = entry.family as string | number;
      if ((family === "IPv4" || family === 4) && !entry.internal) ips.push(entry.address);
    }
  }
  return ips;
}

function lanPlugin(): Plugin {
  return {
    name: "asteria-lan",
    configureServer(server) {
      server.middlewares.use("/lan.json", (_req, res) => {
        const port = server.config.server.port || 5173;
        const ips = lanAddresses();
        const ip = ips.find((item) => item.startsWith("192.168.")) || ips.find((item) => item.startsWith("10.")) || ips[0];
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ ips, port, url: ip ? `http://${ip}:${port}` : "" }));
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), lanPlugin()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        timeout: 0,
        proxyTimeout: 0,
      },
      "/health": "http://127.0.0.1:8000",
    },
  },
});
