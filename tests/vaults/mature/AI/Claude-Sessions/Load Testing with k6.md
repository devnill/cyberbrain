---
id: aa212121-2121-2121-2121-212121212121
date: 2026-02-25T14:00:00
type: reference
scope: general
title: "Load Testing with k6"
project: general
tags: ["load-testing", "k6", "performance", "testing"]
related: ["[[Monitoring Service Level Objectives]]"]
summary: "k6 load testing patterns including ramp-up profiles, thresholds, and integration with CI/CD"
cb_source: hook-extraction
cb_created: 2026-02-25T14:00:00
---

## Load Testing with k6

### Basic Script

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 100 },  // ramp up
    { duration: '5m', target: 100 },  // sustain
    { duration: '2m', target: 0 },    // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const res = http.get('https://api.example.com/health');
  check(res, { 'status 200': (r) => r.status === 200 });
  sleep(1);
}
```

### CI Integration

- Run load tests in CI against staging after every deployment
- Fail the pipeline if thresholds are breached
- Store results in Grafana Cloud k6 for trend analysis
