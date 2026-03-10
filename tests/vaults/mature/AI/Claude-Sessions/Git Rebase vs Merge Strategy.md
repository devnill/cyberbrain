---
id: aa222222-aaaa-aaaa-aaaa-aaaaaaaaaaaa
date: 2026-02-27T09:00:00
type: decision
scope: general
title: "Git Rebase vs Merge Strategy"
project: general
tags: ["git", "branching", "workflow", "decision"]
related: []
summary: "Adopted rebase-before-merge strategy for feature branches to maintain a linear main branch history"
cb_source: hook-extraction
cb_created: 2026-02-27T09:00:00
---

## Git Rebase vs Merge Strategy

### Decision

Rebase feature branches onto main before merging. Use squash merge for the final merge to main.

### Workflow

1. Branch from main
2. Work on feature branch (multiple commits OK)
3. Before PR: `git rebase main` (resolve conflicts once)
4. PR review
5. Squash merge to main (one commit per feature)

### Why

- Linear main branch history (easy to bisect, easy to read)
- Squash merge keeps main clean (no WIP commits)
- Force-push to feature branch is safe (nobody else works on it)

### Rules

- Never rebase main or shared branches
- Always rebase before requesting review (avoid merge conflict in PR)
- Squash merge message should reference the PR number
