# ADR-004: Playwright for Browser Automation

## Status

Proposed

## Context

Some job sources and ATS platforms require a real browser. The automation must be reliable, debuggable, and capable of detecting CAPTCHA/MFA before stopping.

## Decision

Use **Playwright** for browser automation, driven from Python workers.

## Alternatives Considered

* **Selenium:** Long-established but flakier and slower than Playwright.
* **Puppeteer:** Node-only; would force a JavaScript worker stack.
* **Scrapy + headless browser:** Good for crawling but less suited for interactive ATS flows.

## Advantages

* Modern API with auto-waiting and robust selectors.
* Excellent debugging tools (trace viewer, codegen).
* Supports multiple browsers (Chromium, Firefox, WebKit).
* Active maintenance and community.

## Disadvantages

* Heavy resource usage; requires containers with adequate memory.
* Automation can be detected by anti-bot systems. The project commits to stopping, not bypassing.

## Migration / Scaling Considerations

* Browser workers can be extracted into a separate service if resource needs grow.
* Use isolated sessions and external proxy rotation only for rate-limit compliance, not anti-bot evasion.
