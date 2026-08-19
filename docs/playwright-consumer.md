# Playwright in a consumer repo — the in-repo half of the browser testing convention

The estate's browser testing convention (Homelab-Skills ADR 0017) has two
halves. The CI half — calling `playwright-test.yml`, the estate image pin and
lockstep, the ARC runner prerequisites — lives in the
[README](../README.md#playwright-testyml) and is deliberately not repeated
here. This document is the other half: what the inside of a consuming repo
looks like, so adopting browser testing is a copy from here rather than a
reverse-engineering of a sibling.

**`cshuttle/nmon` is the living reference.** Where this document and nmon
disagree, nmon has probably grown a lesson this document has not caught up
with — read its `playwright.config.js` header comments before assuming the
divergence is drift. This document exists so consumers make the same choices;
nmon exists to prove they work.

## What the reusable workflow assumes about your repo

`playwright-test.yml` checks out your repo and, at its **root**:

- reads `package.json` and `package-lock.json` (the `lockstep` job — so the
  Playwright pin must live in the **root** manifest, even when the app itself
  lives in a subdirectory; see the last section),
- runs `npm ci`, then your `e2e-command` (default `npm run test:e2e`),
- on failure, uploads `playwright-report/` and `test-results/` as the
  `playwright-report` artifact.

Everything below exists to satisfy that contract.

## npm conventions — the pin, the lockfile, the Renovate rule

**Pin `@playwright/test` exactly**, to the version the estate image tag
carries (`ghcr.io/cshuttle/playwright:v1.62.1-noble` → `1.62.1`):

```json
"devDependencies": {
  "@playwright/test": "1.62.1"
}
```

No `^`, no `~`. A range lets npm drift ahead of the image, and then
`playwright install` reaches for `cdn.playwright.dev` — a Microsoft CDN this
site measures at 2.2 MB/s, which timed out and failed CI outright on
2026-07-26 (nmon#76). The lockfile must agree with the manifest (run
`npm install` after editing, commit both); lockstep fails on a range, on a
manifest/lockfile mismatch, and on a pin that differs from the image tag.

**Disable Renovate's npm-side Playwright bumps** in the repo's
`renovate.json` — the image leads and npm follows, because npm publishes
ahead of the image:

```json
{
  "description": "The estate Playwright pin leads and npm follows (cshuttle/workflows playwright-test.yml; ADR 0017). Bump @playwright/test by hand in the same PR as the uses: tag bump — lockstep holds it red until they agree.",
  "matchPackageNames": ["@playwright/test", "playwright", "playwright-core"],
  "enabled": false
}
```

When Renovate walks your `uses:` tag forward after an estate pin bump, update
`package.json` and the lockfile in that same PR.

On CWS, run `npx playwright install chromium` once per machine for local and
agent loops (ADR 0017 — browsers co-located, never a remote endpoint). In CI
the browser ships inside the image; the workflow's `playwright install` step
is a deliberate no-op.

## Playwright config baseline

```ts
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import path from "node:path";

// The port is DERIVED FROM THE CHECKOUT PATH, not fixed (nmon#47): two
// checkouts of one repo — git worktrees, which agent workflows create
// routinely — sharing a fixed port plus `reuseExistingServer` silently run
// one tree's suite against the OTHER tree's server. Hashing the root gives
// every worktree its own port; TEST_PORT still wins.
const ROOT = path.dirname(fileURLToPath(import.meta.url));
const SLOT =
  parseInt(createHash("sha1").update(ROOT).digest("hex").slice(0, 4), 16) % 900;
const PORT = Number(process.env.TEST_PORT || 4300 + SLOT);

export default defineConfig({
  testDir: "./tests/e2e",
  testMatch: "**/*.spec.ts",
  forbidOnly: !!process.env.CI,
  retries: 0,
  // `html` writes playwright-report/, matching the workflow's failure
  // artifact glob; screenshots land in test-results/ (the glob's other half).
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `vite preview --port ${PORT} --strictPort`,
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: !process.env.CI,
  },
});
```

The `webServer` boots **built assets** via `vite preview`, so the script pair
is:

```json
"scripts": {
  "test:e2e": "npm run build && playwright test"
}
```

Testing `vite dev` instead would pass a production bundle that is broken —
the dev server transforms modules on the fly and masks build-only failures.
(nmon differs here by design: its app is unbundled, so its `webServer` runs
the same `server.js` production serves. Same principle — test what ships.)

Do not move the report paths: the workflow uploads `playwright-report/` and
`test-results/` on failure, and output written anywhere else silently
vanishes from the artifact.

## Test directory layout

```
tests/e2e/*.spec.ts   Playwright suites (testDir above)
tests/…               everything else — unit suites, other runners
```

Keep the Playwright glob disjoint from any other runner's. Playwright's
default `testMatch` also collects `**/*.test.{js,ts}`, which sweeps up
`node --test` and vitest files that have no `page` fixture and fail instantly
under the Playwright runner (nmon splits `*.spec.js` / `*.test.js` for
exactly this reason). The explicit `testDir` + `testMatch` pair above makes
the split structural.

## The starter smoke

The first test in every adopting repo is a shell-render smoke:

```ts
// tests/e2e/smoke.spec.ts
import { expect, test } from "@playwright/test";

test("the app shell renders", async ({ page }) => {
  const errors: Error[] = [];
  page.on("pageerror", (e) => errors.push(e));

  await page.goto("/");

  // A selector only the BOOTED APP produces — the static mount point
  // (`<div id="root">`) is served even when the bundle throws at import
  // time, so asserting it proves nothing. Assert a child the module graph
  // must execute to create; prefer the most distinctive stable element the
  // app owns (a brand block, an app bar) over a bare `#root > *`.
  await expect(page.locator("#root > *").first()).toBeVisible();

  // No uncaught exceptions. THIS is the assertion that catches a
  // white-screen bundle error — a bare HTTP 200 (or a title check) passes
  // while the page renders nothing. Handled fetch failures (an absent
  // backend logging to console) do not trip it; only real page errors do.
  expect(errors, errors.map(String).join("\n")).toEqual([]);
});
```

Never assert a bare HTTP 200. Every failure mode worth catching — a manifest
that didn't copy, a `const` hoisted above its definition, a module that
throws at import — serves its files with a 200 and renders a white screen.
The selector proves the app executed; the `pageerror` listener proves it
executed cleanly.

The smoke needs no backend. A frontend whose API is absent should still
execute its module graph and render *something it owns* (a shell, an error
state); assert that. Route-mocking the backend (nmon mocks every Netdata
call) is the next step when the suite grows past the smoke, not a smoke
prerequisite.

## When the app lives in a subdirectory

Lockstep reads the **root** `package.json`, and the workflow's `npm ci` runs
at the root — so a repo whose frontend lives in a subdirectory (Topology:
`frontend/`) keeps a root-level e2e harness:

- root `package.json` + lockfile carrying only `@playwright/test` (the exact
  pin) and the e2e script; `playwright.config.ts` and `tests/e2e/` at the
  root beside it,
- the e2e script reaches into the app directory to install, build and
  preview:

```json
"scripts": {
  "test:e2e": "npm --prefix frontend ci && npm --prefix frontend run build && playwright test"
}
```

with the config's `webServer.command` set to
`npm --prefix frontend run preview -- --port … --strictPort`. The app's own
`package.json` stays untouched apart from a `preview` script; do not convert
the repo to npm workspaces just for this — the existing CI's `working-directory`
assumptions would all move.
