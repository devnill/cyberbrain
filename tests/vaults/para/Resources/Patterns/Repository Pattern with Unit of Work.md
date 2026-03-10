---
id: b4c5d6e7-8f9a-0b1c-2d3e-f4a5b6c7d8e9
date: 2026-02-01T09:15:00
type: insight
scope: general
title: "Repository Pattern with Unit of Work"
project: patterns
tags: ["repository-pattern", "unit-of-work", "architecture", "database"]
related: []
summary: "Combining repository pattern with unit of work enables transaction boundaries at the service layer without leaking database concerns"
cb_source: hook-extraction
cb_created: 2026-02-01T09:15:00
---

## Repository Pattern with Unit of Work

### Key Insight

The repository pattern alone doesn't solve transaction management. Each repository method creates its own database session, making multi-repository transactions impossible without coupling services to the database layer.

The unit of work pattern solves this by owning the database session and providing it to repositories:

```python
class UnitOfWork:
    def __enter__(self):
        self.session = SessionFactory()
        self.users = UserRepository(self.session)
        self.orders = OrderRepository(self.session)
        return self

    def __exit__(self, *args):
        self.session.rollback()
        self.session.close()

    def commit(self):
        self.session.commit()
```

### Benefits

- Transaction boundaries are explicit at the service layer
- Repositories don't know about transactions
- Testing: swap the UoW for an in-memory implementation
- No ORM session leaking into service code
