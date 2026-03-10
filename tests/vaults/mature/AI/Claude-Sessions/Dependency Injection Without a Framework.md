---
id: aaffffffff-ffff-ffff-ffff-ffffffffffff
date: 2026-01-28T14:00:00
type: insight
scope: general
title: "Dependency Injection Without a Framework"
project: general
tags: ["dependency-injection", "python", "architecture", "testing"]
related: []
summary: "Python's first-class functions and duck typing make DI frameworks unnecessary — constructor injection with protocols is sufficient"
cb_source: hook-extraction
cb_created: 2026-01-28T14:00:00
---

## Dependency Injection Without a Framework

In Python, you don't need a DI container. Constructor injection with typing.Protocol gives you everything a framework provides:

```python
from typing import Protocol

class EmailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...

class UserService:
    def __init__(self, email_sender: EmailSender):
        self._email = email_sender

# Production
service = UserService(SmtpEmailSender(config))

# Test
service = UserService(FakeEmailSender())
```

### Why Not a Framework

- Python's dynamic typing already provides late binding
- Protocols give you structural subtyping (duck typing with type checking)
- No magic: dependencies are explicit in the constructor signature
- No annotation scanning, no container configuration, no runtime resolution
