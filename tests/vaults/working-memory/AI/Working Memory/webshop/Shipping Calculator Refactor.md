---
id: wm-b5555555-5555-5555-5555-555555555555
date: 2026-03-01T09:00:00
type: insight
scope: project
title: "Shipping Calculator Refactor"
project: webshop
tags: ["shipping", "refactor", "architecture", "webshop"]
related: ["[[Checkout Flow Redesign Plan]]"]
summary: "Current shipping calculator has hardcoded carrier rules; needs strategy pattern to support pluggable carriers"
cb_source: hook-extraction
cb_created: 2026-03-01T09:00:00
cb_ephemeral: true
cb_review_after: REVIEW_DATE_SOON_5
---

## Shipping Calculator Refactor

### Current State

The shipping calculator has carrier-specific logic hardcoded in a single function with nested if/else for FedEx, UPS, and USPS. Adding a new carrier (DHL for international) requires modifying the core function.

### Proposed Architecture

```python
class ShippingCarrier(Protocol):
    def calculate_rate(self, package: Package, destination: Address) -> ShippingRate: ...
    def estimate_delivery(self, origin: Address, destination: Address) -> DateRange: ...

class CarrierRegistry:
    def register(self, name: str, carrier: ShippingCarrier) -> None: ...
    def get_rates(self, package: Package, destination: Address) -> list[ShippingRate]: ...
```

### Benefits

- New carriers added by implementing the protocol + registering
- Each carrier can be tested independently
- Carrier-specific API integrations are isolated
