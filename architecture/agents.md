# Agent architecture

Planned agents (not implemented in Sprint 0):

- Supervisor
- Analytics
- Document
- Security
- Recommendation
- Research (optional, mocked locally)

The LLM is one component inside a controlled runtime. Agents must not access databases directly; they go through MCP.
