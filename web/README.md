# QueueCraft Control Room frontend

React 19.3.1 / React DOM 19.3.1, TypeScript 7.0.2, Vite 8.3.5, React plugin 6.1.2. Dependencies are pinned in package.json and package-lock.json. Requires a compatible modern Node runtime; this build was verified with Node 24.15.0 and npm 11.12.1.

## Commands

```sh
npm ci
npm test
npm run typecheck
npm run build
npm run dev
```

The local dev server binds to 127.0.0.1:5174 and proxies API/documentation/research paths to 127.0.0.1:8774. The production build is web/dist and is served by the Python app on the same origin. See the root project instructions for starting the backend and reproducing training.

## Implemented surfaces

- Real server examples and model metadata; connection/model errors with retry.
- Five-method comparison with asynchronous polling, cancellation, partial method results and actual runtime/status/bound display.
- Schedule selection, SVG Gantt, keyboard-selectable operations and a table alternative.
- Decision replay and candidate/model-feature inspection; reduced motion uses manual steps.
- Duration changes explicitly mark previous results stale.
- Validated JSON imports, including exported report instance roundtrip; max 128 KiB. Unknown fields, invalid indices/IDs and aggregate operation limits are rejected.
- Timed JSON export from the actual run endpoint. Imports are not used for model training.
- Readable frozen-test/OOD results, paired win/tie/loss counts, confidence intervals and CP-SAT comparison. Intervals containing zero are labeled explicitly.
- Responsive layout, visible focus, labeled controls, empty/loading/error/unavailable states and own-brand local SVG favicon.

## Verification boundary

Six import/schema unit tests passed after a recorded failing baseline. Production typecheck and bundle build passed. The live API contract was checked with a real small-workshop comparison. The final build has 252.49 kB JavaScript (78.54 kB gzip), 18.14 kB CSS (4.61 kB gzip) and an SVG favicon.

Root integration owns desktop/mobile browser verification and screenshots. No Lighthouse score, screen-reader certification or browser compatibility guarantee is claimed by these unit/build checks. The frontend workstream did not operate a browser session.
