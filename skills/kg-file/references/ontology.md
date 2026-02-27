# Knowledge Graph Ontology Reference

This file defines the entity types, field schemas, relationship vocabulary, and domain taxonomy
for the personal knowledge graph. Claude should read this when generating notes for unfamiliar
entity types or when needing to verify valid field values.

---

## Entity Types and Schemas

### `project`
Active or historical work — a thing being built, repaired, learned, or done.

```yaml
---
id:           # optional slug: kebab-case unique identifier
type: project
title:        # human-readable name
domain:       # see domain taxonomy below
status:       # planning | active | blocked | complete | archived
priority:     # high | medium | low
phase:        # planning | build | test | deploy | maintain (for technical projects)
created:      # YYYY-MM-DD
updated:      # YYYY-MM-DD
confidence:   # high | medium | low
source:       # personal-experience | claude-context | documentation | ...
tags:
  - "#status/active"
tools-used:
  - "[[tool/example-tool]]"
related-projects:
  - "[[project/related]]"
open-problems:
  - "[[problem/something-broken]]"
---
```

Body: What is this project, what's the goal, what's the current state. Use wikilinks for all mentioned tools, concepts, and problems.


### `concept`
A principle, technique, method, or body of knowledge.

```yaml
---
type: concept
title:
domain:
parent-concept:   # "[[concept/broader-concept]]" if this is a subconcept
instances:        # projects or tools where this appears
  - "[[project/example]]"
related:
  - "[[concept/related-concept]]"
status:           # seedling | developing | evergreen
created:
updated:
confidence:       # high | medium | low
source:
tags:
---
```

Body: Brief definition (1-3 sentences). Practical application. Example in context with wikilinks.


### `tool`
A specific piece of hardware, software, app, library, or instrument.

```yaml
---
type: tool
title:
domain:
category:     # hardware | software | library | instrument | service
version:      # optional, for software
used-in:
  - "[[project/example]]"
related-tools:
  - "[[tool/similar-tool]]"
status:       # active | deprecated | evaluating
created:
updated:
confidence:
source:
tags:
---
```

Body: What it does. How you use it. Any gotchas or configuration notes. Wikilink to projects that use it.


### `decision`
A specific choice made, with its rationale captured.

```yaml
---
type: decision
title:
domain:
date-decided:   # YYYY-MM-DD
decision:       # one-line statement of what was decided
rationale:      # brief explanation — can also go in body
status:         # active | reversed | superseded
confidence:     # high | medium | low
source:         # personal-experience | research | recommendation | ...
caused-by:
  - "[[problem/what-prompted-this]]"
resolves:
  - "[[problem/what-this-fixes]]"
alternatives-considered:
  - "option A"
  - "option B"
superseded-by:  # "[[decision/newer-decision]]" if reversed
tags:
created:
---
```

Body: Context for the decision. Detailed rationale. What was tried before if relevant. Link to related problems and concepts.


### `insight`
A lesson learned, pattern noticed, or realization worth preserving.

```yaml
---
type: insight
title:
domain:
learned-from:   # "[[event/x]]" or "[[project/x]]" or "[[resource/x]]"
applies-to:
  - "[[concept/relevant-concept]]"
  - "[[project/relevant-project]]"
status:         # seedling | evergreen
confidence:     # high | medium | low
source:         # personal-experience | research | conversation | ...
created:
updated:
tags:
---
```

Body: The insight stated plainly (1-3 sentences). Why it matters. Where it applies. Wikilinks to supporting context.


### `problem`
An open issue, bug, unknown, or challenge.

```yaml
---
type: problem
title:
domain:
status:         # open | investigating | resolved | wont-fix
priority:       # high | medium | low
discovered:     # YYYY-MM-DD
resolved:       # YYYY-MM-DD (if resolved)
affects:
  - "[[project/affected-project]]"
caused-by:
  - "[[concept/root-cause]]"
resolved-by:    # "[[decision/fix]]" if resolved
related:
  - "[[problem/related-issue]]"
confidence:     # high | medium | low — how well is this problem understood?
source:
created:
updated:
tags:
  - "#priority/high"
---
```

Body: **Symptoms** — what you observe. **Context** — when/where it happens. **Possible Causes** — hypotheses. **Attempted Solutions** — what's been tried. Wikilinks throughout.


### `resource`
A book, article, documentation page, URL, video, or other external reference.

```yaml
---
type: resource
title:
domain:
format:       # book | article | documentation | video | course | forum-post | pdf
url:          # if online
author:       # optional
date:         # publication or access date
status:       # unread | reading | read | reference
confidence:   # high | medium | low — quality/reliability of this source
related-concepts:
  - "[[concept/covered-concept]]"
related-projects:
  - "[[project/used-for]]"
tags:
created:
---
```

Body: What this resource covers. Key takeaways if read. Specific sections of interest.


### `person`
A contact, collaborator, or person worth tracking.

```yaml
---
type: person
title:        # person's name
relationship: # collaborator | vendor | friend | family | mentor | community-member
domains-overlap:
  - amateur-radio
  - iOS-dev
contact:      # preferred contact method (optional)
last-contact: # YYYY-MM-DD
projects-shared:
  - "[[project/collaborative-project]]"
confidence:
source:
created:
updated:
tags:
---
```

Body: How you know them. What they're knowledgeable about. Notes from interactions. Wikilinks to shared projects or topics.


### `event`
A one-time or recurring happening worth capturing.

```yaml
---
type: event
title:
domain:
date:         # YYYY-MM-DD
duration:     # optional: "2 hours", "3 days"
location:     # optional: "[[place/x]]" or plain text
participants:
  - "[[person/x]]"
produced:     # notes, decisions, or insights this event generated
  - "[[insight/x]]"
  - "[[decision/x]]"
status:       # upcoming | completed | recurring
created:
tags:
---
```

Body: What happened. What was learned. Link to any decisions or insights it produced.


### `claude-context`
A structured snapshot of what Claude knows about you for a specific domain. Used to seed new sessions.

```yaml
---
type: claude-context
title:        # e.g., "Claude Context — Amateur Radio"
domain:
last-updated: # YYYY-MM-DD
confidence:   # how current and accurate is this context?
source:       # claude-memory | manual
tags:
  - "#review/monthly"
---
```

Body template:
```markdown
## Active Projects
- [[project/x]] — one-line status

## Key Concepts in Play
- [[concept/x]] — why it's relevant

## Open Problems
- [[problem/x]] — brief description

## Recent Decisions
- [[decision/x]] — summary

## Background Context
[anything Claude should know about your setup, constraints, preferences in this domain]
```


### `domain`
A broad area of knowledge or practice.

```yaml
---
type: domain
title:        # e.g., "Amateur Radio"
status:       # active | dormant | archived
related-domains:
  - "[[domain/electronics]]"
tags:
created:
---
```

Body: Brief description of what this domain covers for you. Key projects and concepts in it.


### `skill`
A capability you have or are developing.

```yaml
---
type: skill
title:
domain:
level:        # beginner | intermediate | advanced | expert
status:       # learning | practicing | proficient | dormant
related-concepts:
  - "[[concept/underlying-concept]]"
applied-in:
  - "[[project/where-used]]"
created:
updated:
tags:
---
```

Body: What this skill involves. How you've developed it. Where you apply it.


### `place`
A physical or logical location.

```yaml
---
type: place
title:
category:     # home | workspace | vendor | site | online
address:      # optional
related-projects:
  - "[[project/based-here]]"
tags:
created:
---
```

---

## Relationship Vocabulary

Use these terms consistently in frontmatter arrays and in the prose around wikilinks:

| Relationship | Meaning | Common usage |
|---|---|---|
| `is-a` | Taxonomy / type hierarchy | concept → parent-concept |
| `part-of` | Composition | tool is part of a project setup |
| `uses` | Dependency | project uses tool or concept |
| `causes` | Causal chain | problem causes decision |
| `resolves` | Problem closure | decision resolves problem |
| `depends-on` | Prerequisite | project depends-on concept mastery |
| `related-to` | Loose association | fallback when no better type fits |
| `instance-of` | Specific example of | project is instance-of concept |
| `learned-from` | Source of insight | insight learned-from event or resource |
| `applies-to` | Scope of relevance | insight applies-to concept or project |
| `produced` | Output relationship | event produced insight or decision |
| `supersedes` | Replaces | new decision supersedes old one |
| `conflicts-with` | Tension | two approaches in conflict |

---

## Domain Taxonomy

Use these values for the `domain` field. Add new ones as needed — keep them kebab-case.

```
amateur-radio
electronics
programming
iOS-dev
web-dev
woodworking
landscaping
home
automotive
health
personal
finance
productivity
```

When a note spans multiple domains, use the most specific one and add others as tags: `#domain/electronics #domain/amateur-radio`.

---

## Status Values by Type

| Type | Valid statuses |
|---|---|
| project | planning, active, blocked, complete, archived |
| concept | seedling, developing, evergreen |
| tool | active, deprecated, evaluating |
| decision | active, reversed, superseded |
| insight | seedling, evergreen |
| problem | open, investigating, resolved, wont-fix |
| resource | unread, reading, read, reference |
| event | upcoming, completed, recurring |
| skill | learning, practicing, proficient, dormant |
| domain | active, dormant, archived |

---

## Example Notes

### Example: `insight`

**Path**: `insight/fft-window-size-affects-ctcss-accuracy.md`

```markdown
---
type: insight
title: FFT window size directly controls CTCSS detection accuracy
domain: amateur-radio
learned-from: "[[project/ham-repeater-build]]"
applies-to:
  - "[[concept/fft-analysis]]"
  - "[[concept/ctcss-tone-detection]]"
  - "[[project/ham-repeater-build]]"
status: evergreen
confidence: high
source: personal-experience
created: 2025-01-20
tags: []
---

A larger FFT window improves frequency resolution, which is critical for distinguishing closely
spaced CTCSS tones (e.g., 100.0 Hz vs 103.5 Hz). However, it increases latency — so there is a
direct tradeoff between detection accuracy and gate response time.

The threshold that worked reliably in [[project/ham-repeater-build]] was a 512-point FFT at 8kHz
sample rate, giving ~15.6 Hz resolution — sufficient for the CTCSS band.

This insight resolved the [[problem/ctcss-false-triggers]] by eliminating overlap between
adjacent tone bins.
```

---

### Example: `decision`

**Path**: `decision/use-arduino-fft-over-mt8870.md`

```markdown
---
type: decision
title: Use Arduino FFT library over dedicated MT8870 DTMF chip for tone detection
domain: amateur-radio
date-decided: 2025-01-15
decision: Use Arduino with Goertzel FFT algorithm instead of dedicated MT8870 chip
status: active
confidence: high
source: personal-experience
caused-by:
  - "[[problem/ctcss-detection-accuracy]]"
resolves:
  - "[[problem/ctcss-detection-accuracy]]"
alternatives-considered:
  - "MT8870 DTMF decoder chip — hardware, fast, but limited to DTMF, not CTCSS"
  - "Dedicated PL-259 tone decoder module — less flexible, harder to tune"
created: 2025-01-15
tags: []
---

The [[tool/mt8870-chip]] handles DTMF tones well but is not designed for CTCSS frequencies.
The [[concept/goertzel-algorithm]] running on [[tool/arduino-uno]] gives full control over
target frequencies and threshold tuning, at the cost of slightly higher CPU usage.

This was validated empirically — false trigger rate dropped from ~12% to <1% after switching.
The added flexibility also allows future support for multiple tone plans without hardware changes.
```

---

### Example: `claude-context`

**Path**: `claude-context/amateur-radio.md`

```markdown
---
type: claude-context
title: Claude Context — Amateur Radio
domain: amateur-radio
last-updated: 2025-02-25
confidence: high
source: claude-memory
tags:
  - "#review/monthly"
---

## Active Projects
- [[project/ham-repeater-build]] — Anytone AT-778UV radios, ID-O-Matic IV controller, Arduino CTCSS detection; currently in test phase
- [[project/mobile-hf-antenna]] — planning phase, evaluating screwdriver vs. EFHW options

## Key Concepts in Play
- [[concept/ctcss-tone-detection]] — core to repeater access control
- [[concept/goertzel-algorithm]] — FFT method used for tone detection on Arduino
- [[concept/repeater-linking]] — considering EchoLink integration later

## Open Problems
- [[problem/squelch-tail-noise]] — brief noise burst at end of each transmission, cause unclear
- [[problem/ctcss-latency]] — gate delay is ~300ms, target is <150ms

## Recent Decisions
- [[decision/use-arduino-fft-over-mt8870]] — Arduino Goertzel over hardware DTMF chip
- [[decision/id-o-matic-iv-controller]] — chose over homebrew controller for reliability

## Background Context
Callsign is [CALLSIGN]. Operating in Colorado, 2m/70cm. All hardware lives on the workbench
in the basement. Prefer to build rather than buy where feasible. Have oscilloscope, bench
power supply, and soldering station. Anytone radios are the primary radios for this repeater.
```
