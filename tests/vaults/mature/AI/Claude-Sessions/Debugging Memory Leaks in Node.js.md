---
id: aa333333-3333-3333-3333-333333333333
date: 2026-01-15T16:00:00
type: problem
scope: general
title: "Debugging Memory Leaks in Node.js"
project: general
tags: ["nodejs", "memory-leak", "debugging", "performance"]
related: []
summary: "Event listener leak in WebSocket handler caused gradual memory growth; resolved by ensuring removeListener on disconnect"
cb_source: hook-extraction
cb_created: 2026-01-15T16:00:00
---

## Debugging Memory Leaks in Node.js

### Symptoms

- RSS grew 50MB/hour in production
- No OOM kills yet but trending toward container limit
- Heap snapshots showed growing count of `Listener` objects

### Investigation

1. Took heap snapshots at T=0 and T=30min
2. Compared retained objects — `EventEmitter` listener arrays growing
3. Traced to WebSocket `message` handler adding listeners to a shared event bus
4. Each connection added a listener; disconnections didn't remove them

### Fix

```javascript
ws.on('close', () => {
    eventBus.removeListener('update', handler);
});
```

### Prevention

- Set `EventEmitter.defaultMaxListeners = 20` to catch leaks early (warning at threshold)
- Add a metric for event listener count per emitter type
- Code review checklist: every `addListener` must have a corresponding `removeListener`
