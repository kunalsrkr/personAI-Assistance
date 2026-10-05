# Security architecture

Target model (later sprints):

- Classification: PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED
- PII detection, masking, tokenization
- Prompt-injection defense on retrieved documents
- Human approval for high-value financial actions
- Security MCP and audit events

Sprint 0 has no security gateway yet. Do not send production or real PII into this local stack.
