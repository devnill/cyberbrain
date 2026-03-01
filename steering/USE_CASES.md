# Use Cases

This document describes concrete scenarios in which the knowledge-graph system is used. Each use case specifies the actor, the situation, the interaction, and the outcome. These are intended to make tangible what the project does and what needs it fills.

Where a specific interface is named (e.g. `/kg-recall`), it refers to the current implementation. The goal being served is more durable than the mechanism.

---

## UC1: Resuming a project after a break

**Actor:** Developer
**Related goals:** G3, G5, G6

**Situation:** A developer worked heavily on a service three months ago and is returning to it now. They remember the general shape of what they built but have forgotten the specific decisions made along the way — why a particular database schema was chosen, what a non-obvious configuration flag does, what a failing test turned out to mean.

**Interaction:**
```
/kg-recall authentication token expiry
/kg-recall database schema decisions
```
The system searches the vault for notes tagged or containing these terms and injects the top matches into the session.

**Outcome:** Within a minute of starting the session, the developer has the relevant prior decisions and gotchas in context. The LLM can reason from them. The session proceeds as a continuation rather than a restart. The developer does not re-read source code to reconstruct why decisions were made.

---

## UC2: Debugging a recurring error

**Actor:** Developer
**Related goals:** G6, G3

**Situation:** A cryptic runtime error appears — one the developer has seen before but can't immediately place. Last time it took two hours to isolate and fix.

**Interaction:**
```
/kg-recall "connection refused" postgres
```
The vault contains an `error-fix` beat from a previous session describing the exact root cause: a misconfigured connection pool timeout interacting with a firewall rule.

**Outcome:** The developer finds the beat in seconds. The fix is applied in minutes. The two-hour debugging session does not recur.

---

## UC3: Capturing a decision mid-session

**Actor:** Developer
**Related goals:** G1, G4, G8

**Situation:** Deep in a debugging session, the developer realizes something important about the system's behavior — a non-obvious interaction between two components that explains a class of bugs. They want to capture this while it's fresh, without breaking their flow.

**Interaction:**
```
/kg-file The retry logic in the job queue interacts with the idempotency check —
retries within the 30s window are silently dropped by design, not a bug
```

**Outcome:** The insight is filed immediately as an `insight` beat, tagged and routed to the project vault. The developer continues working. Six months later, when a colleague investigates why retried jobs occasionally seem to disappear, the note surfaces.

---

## UC4: Session compaction without knowledge loss

**Actor:** Developer
**Related goals:** G2, G1

**Situation:** A long session is approaching context limits. The developer is about to run `/compact`. The session contains architectural decisions, two bug fixes, a reference to an external API's quirky behavior, and an unresolved question about caching strategy.

**Interaction:** The developer runs `/compact`. The PreCompact hook fires automatically before truncation. `extract_beats.py` processes the full transcript and extracts:
- 2 `decision` beats (architectural choices made)
- 2 `error-fix` beats (bugs diagnosed and fixed)
- 1 `reference` beat (external API behavior)
- 1 `task` beat (the unresolved caching question)

All six are filed to the vault. Compaction proceeds.

**Outcome:** The session's intellectual output is preserved in full. The compacted session loses transcript history but not the knowledge it contained. The developer can compact aggressively throughout long sessions without sacrificing learning.

---

## UC5: Cross-project pattern reuse

**Actor:** Developer
**Related goals:** G3, G5, G6

**Situation:** A developer starts a new project that requires async background job processing. They've solved this before in a different project but don't remember the details of what worked and what didn't.

**Interaction:**
```
/kg-recall async job queue workers
/kg-recall celery redis retry
```

The vault returns several beats from previous projects: a decision beat documenting why a particular queue library was chosen over alternatives, a problem-solution beat about race conditions in concurrent workers, an error-fix beat about Redis connection handling under load.

**Outcome:** The developer bootstraps the new project with three sessions' worth of validated knowledge from past work. They avoid approaches that didn't work and start from a known-good baseline.

---

## UC6: LLM proactively injects prior context at session start

**Actor:** LLM (inside a Claude Code session)
**Related goals:** G3, G5

**Situation:** A new session begins on a known project. The LLM can detect from the working directory and project name that this project has accumulated history in the vault.

**Interaction:** The LLM proactively runs:
```
/kg-recall [project-relevant terms from working directory or recent task]
```
before beginning substantive work, without being asked to do so.

**Outcome:** The session begins with the LLM already aware of prior decisions, recurring issues, and established patterns. The user does not need to re-brief the LLM on context they've established before. This is analogous to an engineer reviewing their own notes before a meeting.

---

## UC7: Backfilling from historical sessions

**Actor:** Developer (one-time setup)
**Related goals:** G5, G1

**Situation:** A developer has been using Claude.ai or Claude Code for months before installing the knowledge-graph system. They have a rich history of sessions containing valuable decisions and fixes, none of which are in the vault.

**Interaction:**
```bash
python scripts/import-desktop-export.py \
  --export ~/Downloads/conversations.json \
  --cwd ~/code/my-project
```
The import script processes hundreds of conversations, extracts beats from each, and files them to the vault.

**Outcome:** The vault is bootstrapped with months of historical knowledge. Prior work is now searchable and injectable into future sessions. The developer gains the benefit of the system retroactively.

---

## UC8: Filing external knowledge at the moment of discovery

**Actor:** Developer
**Related goals:** G4, G6

**Situation:** While reading documentation or browsing Stack Overflow, a developer encounters a useful solution, a non-obvious API behavior, or a constraint worth remembering. Normally this is bookmarked or forgotten.

**Interaction:**
```
/kg-file strftime %Y-%m-%dT%H:%M:%S produces timezone-naive strings in Python;
use .isoformat() with timezone.utc for ISO 8601 with offset
```

**Outcome:** The fact is filed as a `reference` beat, tagged `[python, datetime, timezone, iso8601]`, and stored in the vault. The next time the developer encounters a datetime formatting issue, it surfaces in search.

---

## UC9: Generating a vault CLAUDE.md for consistent autofile

**Actor:** Developer (setup)
**Related goals:** G8, G4

**Situation:** A developer has enabled `autofile: true` and wants the system to file beats intelligently into their Obsidian vault rather than dumping everything into a flat inbox folder. The autofile LLM needs to understand their vault's structure and conventions to make good decisions.

**Interaction:**
```
/kg-claude-md
```
The skill walks the vault's folder structure, samples existing notes, and generates a `CLAUDE.md` at the vault root describing the developer's filing conventions: which folders exist, what goes in each, tag naming patterns, whether to prefer extending existing notes.

**Outcome:** The autofile system makes filing decisions that match the developer's actual vault organization. New beats are routed to the right folders and either extend existing notes or create appropriately placed new ones. The vault grows coherently rather than fragmenting.

---

## UC10: Daily journal as passive work log

**Actor:** Developer
**Related goals:** G1, G5

**Situation:** A developer wants a lightweight record of what they worked on and learned each day, without maintaining a manual journal.

**Configuration:** `daily_journal: true` in `~/.claude/knowledge.json`

**Interaction:** None required. Each compaction fires the PreCompact hook, which extracts beats and appends a dated entry to the journal noting which beats were filed, what project they're from, and their titles.

**Outcome:** Over time, the journal accumulates a navigable record of work and learning. The developer can look back at a date and see what was worked on, what decisions were made, and what was discovered — without having written any of it manually.

---

## UC11: Querying the vault programmatically (LLM-to-vault)

**Actor:** LLM or automated pipeline
**Related goals:** G3, G9

**Situation:** An LLM agent working on a multi-step task needs to check whether a particular approach has been attempted before, or whether a relevant configuration is documented in the vault.

**Interaction:** Via the MCP server (Claude Desktop integration), the agent calls `kg_recall` as a tool:
```
kg_recall(query="redis cache eviction policy", max_results=3)
```
The tool returns matching vault notes as structured content.

**Outcome:** The LLM can consult the vault as part of its reasoning process, not just at session start but mid-task whenever relevant context is needed. The vault functions as an external memory store accessible to any LLM interface that has MCP support.

---

## UC12: Reviewing what was learned during a difficult investigation

**Actor:** Developer (post-session review)
**Related goals:** G1, G5

**Situation:** A developer has just concluded a difficult debugging session that took several hours and touched many parts of the system. They ran `/compact` partway through, so beats were captured. Now they want to review what the session produced.

**Interaction:** The developer opens Obsidian and navigates to their project's Claude-Notes folder. They see the beats filed from the session: an `error-fix` describing the root cause, two `insight` beats about non-obvious system behavior discovered along the way, and a `task` beat flagging a fragility to address.

**Outcome:** The session's work is documented in a form they can read, share, and build on. The difficult session produced not just a fixed bug but a durable record of how the system actually works.

---

## UC24: Using a local LLM to eliminate API costs and keep data on-device

**Actor:** Developer
**Related goals:** G16, G17

**Situation:** A developer uses the system heavily — multiple compactions per day, periodic enrichment runs, large import backlogs. The accumulated API cost is noticeable. Separately, they work on a client project where sending session content to a third-party API isn't appropriate.

**Interaction:** They configure the system to use a local backend:
```json
{
  "backend": "ollama",
  "ollama_model": "mistral",
  "ollama_url": "http://localhost:11434"
}
```
All subsequent extraction, autofile, and enrichment calls go to the locally-running model. No content leaves the machine. No API calls are made.

**Outcome:** The developer's daily usage costs nothing in API fees. Client project sessions are processed entirely locally. The vault grows at the same rate as before, with somewhat different extraction quality — acceptable given the tradeoff. When quality matters more than cost (e.g. a complex autofile decision), the user can switch back to a cloud model per-project via `knowledge.local.json`.

---

## UC13: Capturing knowledge from a session that ends without compaction

**Actor:** Developer
**Related goals:** G2, G12

**Situation:** A developer spends an hour debugging a tricky configuration issue, figures it out, and closes the terminal. They never ran `/compact`. The PreCompact hook never fired. Under the current system, the session's knowledge is gone.

**Interaction:** The system detects that the session has ended (or the user manually triggers extraction after closing) and runs extraction on the transcript before it's no longer accessible.

**Outcome:** The configuration fix is captured as an `error-fix` beat even though no compaction occurred. The developer doesn't need to remember to compact in order to preserve what they learned.

---

## UC14: Knowledge available across all devices

**Actor:** Developer
**Related goals:** G11, G3

**Situation:** A developer debugs a problem on their work laptop on Thursday evening. The vault receives an `error-fix` beat. On Saturday morning, on their personal laptop, they encounter the same class of problem on a different project.

**Interaction:**
```
/kg-recall [error description]
```
The beat from Thursday's work session surfaces, even though it was captured on a different machine.

**Outcome:** The vault functions as a single source of truth across devices. The developer doesn't think about which machine captured what — they think about the knowledge, not its origin.

---

## UC15: Periodic re-import to keep the vault current

**Actor:** Developer
**Related goals:** G5, G1

**Situation:** A developer installs the knowledge-graph system and backfills from their Anthropic data export. Three months pass. New Claude Desktop sessions have accumulated. The import state file tracks which conversations were already processed.

**Interaction:**
```bash
python scripts/import-desktop-export.py \
  --export ~/Downloads/conversations-new.json
```
The script checks the state file, skips already-processed conversations, and processes only the new ones.

**Outcome:** The vault stays current with minimal effort. Re-running the import is safe and idempotent — already-ingested sessions are not processed twice, and the vault does not accumulate duplicates.

---

## UC16: Deduplication when a conversation is imported more than once

**Actor:** Developer
**Related goals:** G5, G7

**Situation:** A developer runs the import script on a conversations export. Later, they export again from Claude.ai and the new export contains conversations that overlap with the previous import (e.g., a resumed conversation that was partially processed before). They run the import again.

**Interaction:** The system detects the overlap via session IDs in the state file. The already-processed conversations are skipped. No duplicate beats are created for sessions that were already imported.

**Outcome:** The vault remains clean regardless of how many times the import is run or how much overlap exists between exports. The developer can run imports confidently without auditing for duplicates afterward.

---

## UC17: Reviewing and correcting a miscategorized beat

**Actor:** Developer
**Related goals:** G13, G7

**Situation:** After a compaction, the developer glances at the newly filed beats in Obsidian. One beat was filed as a `task` when it's clearly a `decision`. Another was routed to the general inbox instead of the project folder. A third extended the wrong note.

**Interaction:** The developer corrects the type in the note's frontmatter, moves the file to the correct folder, and edits the extended note to remove the erroneous insertion. Optionally, they use `/kg-file` to re-file the corrected content.

**Outcome:** The vault is corrected with minimal friction. The developer can trust that their vault reflects what actually happened, not just what the LLM guessed. Over time, the developer may tune the autofile prompt or vault CLAUDE.md to prevent the same classes of errors from recurring.

---

## UC18: Importing ChatGPT conversation history

**Actor:** Developer
**Related goals:** G4, G9, G5

**Situation:** A developer has used ChatGPT for years and has a rich history of technical conversations — debugging sessions, architecture discussions, code reviews — in their ChatGPT export. This knowledge currently lives outside the vault.

**Interaction:**
```bash
python scripts/import-chatgpt-export.py \
  --export ~/Downloads/chatgpt-conversations.json
```
The script parses the ChatGPT export format, extracts conversation text, and feeds it through the same beat extraction pipeline used for Claude sessions.

**Outcome:** Years of ChatGPT conversations contribute beats to the vault. The developer's externalized memory is not limited to Claude sessions — it reflects the full history of their LLM-assisted work, regardless of which product it came from.

---

## UC19: Capturing beats from Claude on mobile

**Actor:** Developer
**Related goals:** G11, G12, G4

**Situation:** The developer uses Claude heavily on their phone — debugging ideas, exploring solutions, talking through problems. These are real working sessions that produce real decisions and insights. They happen throughout the day: on the train, between meetings, away from the desk. Currently this entire class of session produces no vault beats.

This is not a nice-to-have edge case. Mobile Claude sessions are a primary interface and a significant source of knowledge that the current system is blind to.

**Interaction:** Either automatically (via a hook or scheduled sync that processes Claude.ai session history) or manually (via an export or browser-accessible interface that feeds the transcript to the extraction pipeline). The specific mechanism is a spike (SP4, SP5), but the outcome requirement is firm.

**Outcome:** Sessions held on a phone are treated identically to sessions held in Claude Code. Beats are extracted, tagged, scoped, and filed to the vault. The developer doesn't lose the intellectual output of mobile sessions just because they happened on a different interface.

---

## UC20: Semantic retrieval when keyword search fails

**Actor:** Developer
**Related goals:** G14, G3

**Situation:** A developer wants to recall how they handled a particular problem, but they can't remember the specific terminology used in the original session. The words they'd naturally search for don't appear in the relevant notes.

**Interaction:**
```
/kg-recall how do we deal with users losing their session
```
A keyword search returns nothing — the relevant notes use terms like "JWT expiry", "token invalidation", and "auth middleware", none of which appear in the query. A semantic search finds them anyway by matching on meaning.

**Outcome:** The developer retrieves the relevant context without needing to guess the exact terminology used when the note was created. Recall works the way human memory works — by concept, not by exact phrasing.

---

## UC21: Retrieving context without exhausting the context window

**Actor:** LLM (inside a session)
**Related goals:** G14, G3

**Situation:** Before starting work on a large feature, the LLM runs a broad recall query. The vault contains 15 notes that are at least partially relevant. Loading all 15 in full would consume a significant chunk of the context window before any actual work is done.

**Interaction:** The retrieval layer returns structured summaries and excerpts for each matching note, with links to full content. The LLM reads the summaries, identifies the 3 most relevant, and loads only those in full.

**Outcome:** The session begins with useful context injected efficiently. The remaining context window is available for the actual work. Retrieval does not compete with reasoning for context budget.

---

## UC22: Auto-enriching manually-written Obsidian notes

**Actor:** Developer
**Related goals:** G15, G7

**Situation:** A developer has been adding rough notes to Obsidian directly — quick thoughts, clippings from documentation, meeting takeaways, snippets. These notes have no frontmatter, inconsistent tags or none at all, and no type classification. They exist in the vault but are effectively invisible to the system's recall mechanisms.

**Interaction:**
```
/kg-enrich
```
The skill scans the vault for notes missing required frontmatter fields. For each, it reads the note content and generates: a `type` classification, a `summary`, `tags`, and `scope`. It writes the enriched frontmatter back to the file.

**Outcome:** The rough notes are now first-class beats. They appear in recall results, can be autofile-routed if moved, and are injectable into LLM context. The developer's manual additions contribute to the vault's value without requiring manual tagging discipline.

---

## UC23: Reviewing Obsidian as the human interface layer

**Actor:** Developer
**Related goals:** G15, G13

**Situation:** After a week of productive sessions, the developer opens Obsidian to review what's been captured. They read through recent beats, spot a few that are misfiled or have vague tags, and add a few notes of their own about upcoming work and open questions.

**Interaction:** Direct in Obsidian. No skill required. The developer edits notes in place, adds new ones freehand, reorganizes folders, and links related notes using Obsidian's wikilink syntax.

**Outcome:** Obsidian serves as the human-facing review and curation layer — the place where the developer interacts with the vault on their own terms, not just as a passive recipient of LLM-extracted beats. The vault reflects both automated capture and deliberate human curation. The next enrichment run will normalize any new freehand notes they added.
