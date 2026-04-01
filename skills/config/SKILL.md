---
description: "Set up or reconfigure cyberbrain — vault path, note structure, and extraction preferences"
user-invocable: true
---

# Cyberbrain Config

You are executing the cyberbrain config skill. Follow the phases below. Detect whether this is a first-time setup or an existing installation, and branch accordingly.

## Phase 1: Detect Config State

Call `cb_configure()` with no arguments to read the current configuration.

- If the vault is **not configured** (vault_path is "(not configured)" or the directory does not exist): proceed to **Phase 2 — First-Run Setup**.
- If the vault **is configured** and the directory exists: proceed to **Phase 5 — Existing Config**.

## Phase 2 — First-Run Setup: Choose a Vault Location

Tell the user:

> "Welcome to cyberbrain. I'll walk you through a quick setup — it takes about a minute.
>
> First: where should cyberbrain store your notes? This folder becomes your knowledge vault. You can open it in Obsidian later to browse and search your notes visually (Obsidian is free and optional).
>
> Suggested location: `~/Documents/Cyberbrain`
>
> Press Enter to use that, or type a different path."

Wait for the user's response. If they press Enter or say "yes" or "default", use `~/Documents/Cyberbrain`. Otherwise use the path they provide.

Store this as `chosen_vault_path`.

## Phase 3 — First-Run Setup: Note Organization Interview

Ask the user this single question:

> "How do you like to organize your notes? (Pick the one that sounds most like you, or say 'skip' to use a standard layout.)
>
> 1. I don't really organize notes / I'm new to this
> 2. PARA — Projects, Areas, Resources, Archives
> 3. Flat / minimal — just dump everything in one place
> 4. Developer / project-focused — organized around code projects
> 5. I have my own system — let me describe it"

Wait for the user's response. Map their answer to a template:

- Option 1 or "skip" or no strong preference → `template = "para"` (PARA is a good starting point for beginners)
- Option 2 → `template = "para"`
- Option 3 → `template = "flat"`
- Option 4 → `template = "developer"`
- Option 5 → Ask one follow-up: "Briefly describe your system — I'll pick the closest template." Then map their description to `para`, `flat`, or `developer` using your judgment. If uncertain, default to `para`.

Store this as `chosen_template`.

Tell the user which template you selected and what folders it creates:
- `para`: Projects/, Areas/, Resources/, Archives/, AI/Claude-Sessions/, AI/Working Memory/
- `flat`: AI/Claude-Sessions/, AI/Working Memory/
- `developer`: Projects/, AI/Claude-Sessions/, AI/Working Memory/

## Phase 4 — First-Run Setup: Create Vault and Generate Vault Guide

### 4.1 Create the Vault

Call `cb_configure(create_vault=chosen_vault_path, template=chosen_template)`.

If the call fails because the directory is non-empty, call again with `force=True` and note this to the user.

### 4.2 Generate Vault CLAUDE.md (Analysis)

Call `cb_setup()` to analyze the vault structure. It returns a JSON object with a `questions` array and vault analysis.

Extract the questions from the returned JSON and present each one to the user in plain language — keep it brief, one question at a time if there are multiple. Collect their answers.

### 4.3 Generate Vault CLAUDE.md (Write)

Call `cb_setup(answers="<user answers>", write=True)` to generate and save the vault's CLAUDE.md.

### 4.4 Set Default Extraction Preferences

Call `cb_configure(reset_prefs=True)` to append the default extraction preferences to the vault CLAUDE.md.

### 4.5 Confirm Setup Complete

Tell the user:

> "Setup complete. Here's what was created:
>
> - Vault at: `<chosen_vault_path>`
> - Folder structure: `<chosen_template>` template
> - Vault guide (CLAUDE.md) generated — this tells cyberbrain how to file your notes
>
> Cyberbrain will now automatically capture knowledge from your Claude sessions. Notes appear in your vault after each session.
>
> Optional: open `<chosen_vault_path>` in Obsidian to browse your notes visually.
>
> To change any setting later, run `/cyberbrain:config` again."

## Phase 5 — Existing Config: Show and Edit

Display the current configuration by summarizing what `cb_configure()` returned. Keep the summary concise — show vault path, inbox folder, backend/model, and capture mode.

Then ask:

> "What would you like to change? Or say 'nothing' to exit.
>
> Options:
> - **vault** — change the vault path
> - **inbox** — change the subfolder where general notes go (current: `<inbox>`)
> - **backend** — change the extraction model or backend
> - **capture** — change capture mode (current: `<capture_mode>`; options: suggest / auto / manual)
> - **preferences** — view or update extraction preferences
> - **nothing** — exit"

Wait for the user's response and handle each option:

**vault**: Ask for the new vault path. Call `cb_configure(vault_path=<new_path>)`. Offer to run `cb_setup()` to regenerate the vault CLAUDE.md if this is a different vault.

**inbox**: Ask for the new inbox subfolder (e.g. `AI/Claude-Sessions`). Call `cb_configure(inbox=<new_inbox>)`.

**backend**: Explain the options briefly:
- `claude-code` (default) — uses your active Claude session; fastest
- `bedrock` — uses AWS Bedrock; requires AWS credentials
- `ollama` — uses local models; requires Ollama running locally

Ask which backend and, if not `claude-code`, which model. Backend changes are not yet supported via cb_configure. Tell the user to edit `~/.claude/cyberbrain/config.json` directly, setting the `"backend"` key to `"claude-code"`, `"bedrock"`, or `"ollama"`, and the `"model"` key to the desired model name.

**capture**: Explain the modes:
- `suggest` — cyberbrain offers to file notes before writing (default)
- `auto` — files notes immediately without asking
- `manual` — only files notes when you explicitly ask

Ask which mode. Call `cb_configure(capture_mode=<mode>)`.

**preferences**: Call `cb_configure(show_prefs=True)` and display the result. Ask if they want to update any preferences. If yes, collect their changes as natural language and call `cb_configure(set_prefs="<updated text>")`. To restore defaults, call `cb_configure(reset_prefs=True)`.

**nothing**: Say "No changes made." and exit.

After handling any option, ask if there is anything else to change, or exit if they indicate they are done.

## Error Handling

- If any tool call fails, surface the error message to the user and suggest a next step. Never fail silently.
- If the first `cb_setup()` call (without answers) fails, or if the second `cb_setup(answers=..., write=True)` call fails, tell the user the vault was created successfully but the vault guide could not be generated. Suggest running `/cyberbrain:config` again or calling `cb_setup()` manually.
- If `create_vault` fails for an unexpected reason (not a non-empty directory error), show the error and suggest the user verify the path is within their home directory.
