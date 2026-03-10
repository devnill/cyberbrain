# Work Item 024: Add orient-prompt and CLAUDE.md guidance to cb_setup

## Objective

Update `cb_setup` completion output to inform users about the orient-prompt requirement for Desktop proactive recall and generate a CLAUDE.md recall instruction snippet for Claude Code projects, addressing WI-020 findings MR3/MI2.

## Complexity

Medium

## Dependencies

None

## File Scope

- `mcp/tools/setup.py` (modify) — add guidance to completion output

## Acceptance Criteria

- [ ] `cb_setup` completion output includes a section explaining that Claude Desktop proactive recall requires selecting the orient prompt (connectors menu > cyberbrain > orient) at each session start
- [ ] `cb_setup` completion output includes a CLAUDE.md snippet users can add to Claude Code projects to enable proactive recall (e.g., "When the user mentions a topic, call cb_recall to check for relevant notes")
- [ ] The guidance is appended after the existing vault CLAUDE.md generation, not replacing it
- [ ] The orient-prompt guidance mentions the specific UI path: "plus button > connectors > cyberbrain > orient"
- [ ] All existing tests pass

## Implementation Notes

- `setup.py` has a two-phase flow. The guidance should be appended to the phase 2 completion message (after vault CLAUDE.md is generated)
- Keep the guidance concise — this is tool output that the LLM will relay to the user
- The CLAUDE.md snippet should be fenced in a code block so the user can copy-paste it
- Example snippet: `## Cyberbrain\nWhen the user mentions a topic you have notes about, call cb_recall to check for relevant context. When you learn something worth remembering, call cb_file to save it.`
