# Knowledge Graph Memory Management System
## Project Overview & Decision Points

---

## Problem Statement

Long-running Claude CLI sessions suffer from two compounding issues: **context window exhaustion** and **degraded reasoning quality** as the compaction process kicks in. Current compaction logic squeezes the full context down to major beats, but this is lossy — nuance and detail get discarded, and the system develops "context anxiety" as it approaches its limits.

The goal is to replace heavy reliance on compaction with a structured **ingest and retrieval** system. Instead of compressing everything at the end, meaningful information is extracted continuously, stored persistently in a human-readable format, and pulled back in on demand when relevant — keeping context lean and purposeful.

A secondary goal is better management of work produced across sessions, creating a reusable knowledge base that grows over time.

---

## System Architecture Overview

The system is split into two phases:

**Phase 1 — Ingest**: Extract meaningful "beats" from an ongoing session, enrich them with structured metadata, and store them as markdown documents compatible with Obsidian.

**Phase 2 — Retrieval**: Use a tool (likely an MCP server or skill) to query the knowledge base and surface relevant context into a new session on demand, reducing the need to reload full conversation history.

---

## Design Principles

- **Human-readable first**: All stored content is markdown, readable and editable without special tooling.
- **Obsidian-compatible**: Front matter metadata follows YAML conventions, usable in Obsidian workflows.
- **Domain-agnostic**: The schema should work across varied projects and topics without being tied to a specific domain.
- **Structured but flexible**: Front matter follows a consistent schema, but tagging and categorization remain adaptable.

---

## Open Decision Points

### 1. What is a "Beat"?
What granularity makes sense for an extractable unit? Options include:
- A single insight or decision
- A problem-solution pair
- A completed task or subtask
- A phase or milestone within a larger project

### 2. Front Matter Schema
What fields belong in the metadata? Which are required vs. optional? Candidates include:
- Timestamp / date
- Session or conversation ID
- Topic or domain tags
- Type of content (decision, task, insight, reference, etc.)
- Related beats or dependencies
- Status or outcome

### 3. Signal vs. Noise
What criteria determine whether something is worth storing vs. discarded? How does the ingest process distinguish meaningful content from conversational filler?

### 4. Retrieval Mechanism
How should the system determine what's relevant to pull into a new session?
- Semantic / vector search
- Keyword or tag matching
- Hierarchical topic structure
- A combination of the above

### 5. Ingest Trigger
Should extraction happen:
- Automatically and continuously during a session?
- Manually at defined breakpoints?
- At session end as a structured review?

### 6. Tooling Integration
Should ingest and retrieval live as:
- An MCP server
- A Claude skill
- A standalone script with CLI hooks
- Some combination?

---

*Generated: 2026-02-25 — Working draft, subject to revision as design decisions are made.*
