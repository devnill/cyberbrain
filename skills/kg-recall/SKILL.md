---
name: kg-recall
description: Search the knowledge base from past Claude Code sessions and inject relevant context. Use when starting work on a topic you may have covered before, or when you need to fill in gaps about a project, decision, or error fix from a previous session.
allowed-tools: Bash, Read, Glob
---

# Knowledge Recall

Search for: $ARGUMENTS

## Process

1. Load the knowledge base configuration from `~/.claude/knowledge.json`
2. Resolve the vault path and any project-specific folder from `.claude/knowledge.local.json` in the current working directory (walk up from cwd)
3. Search for relevant documents using the query above
4. Read the top matching documents
5. Synthesize a concise context summary, citing each source document

## Search Strategy

Run these searches in order, combining results:

### Step 1: Get vault path from config
```bash
python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser('~/.claude/knowledge.json')))
print(cfg.get('vault_path', ''))
"
```

### Step 2: Search by keywords in summary and title (highest signal)
```bash
grep -r -l --include="*.md" -i "QUERY_TERMS" "$VAULT_PATH" 2>/dev/null | head -20
```

### Step 3: Search by tags
```bash
grep -r -l --include="*.md" "tags:.*QUERY_TERMS" "$VAULT_PATH" 2>/dev/null | head -10
```

### Step 4: Search in body content
```bash
grep -r -l --include="*.md" -i "QUERY_TERMS" "$VAULT_PATH" 2>/dev/null | head -20
```

### Step 5: Project-specific filter (if project config exists)
Prefer files from the project's `vault_folder` in the knowledge base.

### Step 6: Recency bias
Sort results by modification time and prefer files from the last 30 days.

## Reading and Synthesis

- Read up to **5 documents** (to stay within context budget)
- If a document's `summary` field alone is sufficient, you may skip reading the full body
- For each document read, note the `title`, `type`, `date`, and `project` fields
- Synthesize findings into a structured context block for the current session

## Output Format

Present findings as:

```
## Knowledge from previous sessions

### [Document title] (type: X, date: YYYY-MM-DD, project: Y)
[Key information extracted]

Source: [file path]

---

### [Document title] ...
```

If no relevant documents are found, say so clearly and suggest the user run `/compact` after the current session to start building the knowledge base.

## No Results

If the search returns nothing, respond:
"No matching knowledge found for '[query]'. The knowledge base may be empty or this topic hasn't been covered in a previous session. After your next /compact, relevant content will be extracted automatically."
