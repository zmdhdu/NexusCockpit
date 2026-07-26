---
name: langfuse
description: Interact with Langfuse and access its documentation. Use when needing to (1) query or modify Langfuse data programmatically via the CLI — traces, prompts, datasets, scores, sessions, and any other API resource, (2) look up Langfuse documentation, concepts, integration guides, or SDK usage, or (3) understand how any Langfuse feature works.
allowed-tools:
  - WebFetch(domain:langfuse.com)
  - WebSearch
---

# Langfuse

This skill helps you use Langfuse effectively across all common workflows: instrumenting applications, migrating prompts, debugging traces, and accessing data programmatically.

## Core Principles

1. **Documentation First**: NEVER implement based on memory. Always fetch current docs before writing code (Langfuse updates frequently)
2. **Best Practices by Use Case**: Check the relevant reference file below for use-case-specific guidelines before implementing
3. **Use latest Langfuse versions**: Always use the latest version of Langfuse SDKs/APIs
4. **Framework integrations over manual instrumentation**: Use `@observe` decorator or CallbackHandler when available

## Instrumentation Best Practices

Every trace should have:
- **Model name**: captured for LLM calls
- **Token usage**: input/output tokens tracked
- **Descriptive names**: `chat-response`, not `trace-1`
- **Span hierarchy**: multi-step operations nested properly
- **Correct observation types**: `generation` for LLM, `agent` for subagents, `retriever` for lookups
- **Sensitive data masked**: PII excluded or masked
- **Trace input/output**: explicitly set, not all function args

Add context:
- `session_id` for conversation grouping
- `user_id` for user filtering
- `tags` for per-feature analytics
- `cockpit_id` / tenant identifiers for cost breakdown

## Multi-agent Systems

- Type subagent executions as `agent`, not `tool`/`span`
- Don't emit duplicate dispatch + execution nodes
- Nest recursively under the orchestrating span
- Name subagents distinctly from their task/role

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| No `flush()` in scripts | Call `langfuse.flush()` before exit |
| Flat traces | Use nested spans for distinct steps |
| Generic trace names | Use descriptive names |
| Logging sensitive data | Mask PII before tracing |
| Manual instrumentation when integration exists | Use `@observe` decorator |
| Langfuse import before env vars loaded | Import AFTER `load_dotenv()` |

## Documentation Access

- Full index: `https://langfuse.com/llms.txt`
- Individual pages: append `.md` to URL
- Search: `https://langfuse.com/api/search-docs?query=<query>`
