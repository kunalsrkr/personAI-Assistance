# Asteria Enterprise AI Command Center

Local enterprise GenAI / agentic AI platform for learning, implementation, and interview preparation.

The LLM is not the application. It is one component inside a controlled AI runtime.

## Sprint 0 (current)

Foundation only — no agents yet:

- React + TypeScript + Vite + Tailwind UI
- FastAPI API gateway
- PostgreSQL and Redis (Docker)
- Ollama runtime (Windows host, not a Compose service)
- Repository layout for later sprints

Full plan: `architecture/asteria_ai_platform_build_plan.md`

## Local run (this machine)

Postgres, Redis, and the API run in Docker. The UI runs on the host with Vite (not in a container).

Ollama is expected on the Windows host. Compose does not start a second Ollama container. The API container reaches it at `http://host.docker.internal:11434`.

If the model is missing on the host:

```powershell
ollama pull llama3.2
```

From the repo root:

```powershell
cd C:\Users\kunal\work\AI_Platform
docker compose up -d
```

In another terminal:

```powershell
cd C:\Users\kunal\work\AI_Platform\frontend
npm install
npm run dev
```

- UI: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Implementation order

1. Synthetic dataset  
2. PostgreSQL  
3. RAG  
4. FastAPI  
5. MCP  
6. Single agent  
7. Supervisor  
8. Multi-agent  
9. A2A  
10. Harness  
11. Loop engineering  
12. Security  
13. Observability  
14. Evaluation  
15. UI polish  

Do not start with the full multi-agent system.
