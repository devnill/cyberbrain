---
id: aa666666-6666-6666-6666-666666666666
date: 2026-01-22T09:15:00
title: "Redis Pub-Sub vs Streams"
project: general
tags: ["redis", "pubsub", "streams"]
cb_source: hook-extraction
cb_created: 2026-01-22T09:15:00
---

## Redis Pub-Sub vs Streams

Pub/Sub is fire-and-forget: if no subscriber is listening, the message is lost. Streams persist messages and support consumer groups with acknowledgment.

Use Pub/Sub for: real-time notifications where message loss is acceptable.
Use Streams for: task queues, event logs, anything requiring at-least-once delivery.
