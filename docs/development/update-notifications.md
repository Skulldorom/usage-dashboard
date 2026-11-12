# Update notification architecture

The authenticated shell owns one `useUpdateStatus` hook and shares its result with
desktop and mobile footers. The hook receives the running backend version from
the existing `/auth/status` metadata. `VITE_APP_VERSION` remains the embedded
frontend version. Missing or incompatible artifacts suppress release notices;
neither version is invented or taken from package-tooling metadata.

## Browser release service

`frontend/src/lib/releaseCheck.js` owns the fixed GitHub latest-release endpoint,
validation, request coalescing and cache access. It bypasses `api.js` to ensure
admin-session headers never reach GitHub. Requests omit credentials and referrers,
reject redirects, bypass HTTP caching, and have a five-second AbortController
timeout covering headers and streamed body consumption. Response size is bounded
to 256 KiB, preserving the former backend's request protections.

The service validates a non-placeholder stable semantic version, explicit
`draft: false` and `prerelease: false`, the exact official release-page URL,
the expected repository's numeric GitHub API release URL, and a valid UTC
publication timestamp no later than the browser clock. Only normalized validated
fields and their successful check time are saved. Untrusted raw response bodies,
release notes and assets are never persisted or rendered. Cache reads repeat
validation and require a non-future check time less than 15 minutes old.

Stable comparisons reuse `appVersion.js` and BigInt core ordering, including large
version components. Frontend and backend versions must match completely except
for an optional leading `v`; build suffixes and development SHAs still matter.
Development/prerelease artifacts may show a stable alternative without asserting
a development commit is older.

## Lifecycle and storage

The initial check waits 2.5 seconds and skips hidden tabs. Further checks occur
on visibility changes or a new authenticated mount, subject to the cache and a
separate one-minute failure deadline. There is no polling interval or scheduled
retry. A single expiry timeout clears a displayed record without a network call.

localStorage was chosen over sessionStorage because verified results, failure
backoff and dismissals should survive reloads and be shared across same-origin
tabs. An in-memory fallback uses the same expiration rules if storage is blocked.
Storage events update mounted views. If a pending check returns no result (for
example, a Web Lock miss), the hook re-reads the validated cache before clearing
its state so a late null cannot erase a synchronized result. This does not extend
the original verification deadline or revive expired/failed cache entries.
This cache contains no credentials.

A shared in-flight promise coalesces calls within a page. Optional Web Locks with
`ifAvailable` prevent concurrent cold-tab fetches; the other tab receives the
result through storage events. Without Web Locks, simultaneous cold tabs can
each fetch once. Web Locks generally require a secure context. Blocked storage
disables cross-tab/reload sharing. No worker, lease protocol or background polling
is needed.

Each caller has a cancellation signal. Removing one consumer does not abort a
request needed by another; removing the last aborts it. Strict Mode clears the
first mount's delay. Disposed hooks ignore late results, and the service checks
cancellation before writing the cache. Timeout and cancellation also settle when
a transport ignores abort. Cancellation does not record a failure backoff.

## Quiet failure handling

HTTP errors (including 404, 403 and 429), network errors, timeouts and invalid
metadata return no release record. Failure deadlines cannot become successful
checks or renew old metadata. The console records only bounded diagnostic codes;
the footer displays only the installed version. No up-to-date claim is made.
A new visible-tab/page-load check after backoff can recover normally.

GitHub documents [CORS access from any origin](https://docs.github.com/en/rest/using-the-rest-api/using-cors-and-jsonp-to-make-cross-origin-requests).
Fetch, AbortController, ReadableStream and optional localStorage/Web Locks are
browser capabilities; there is no GitHub token or backend outbound dependency.
Custom CSPs must allow `https://api.github.com` in `connect-src`. Browser extensions,
network restrictions and shared public-IP rate limits can suppress checks.
Browser clock errors can reject publications or expire cache entries early.

## Scope and tests

The backend release service/router, update schema, cache configuration and
service-specific tests are removed. General `APP_VERSION` configuration,
Docker/native metadata embedding, release classification, publication and image
integrity verification remain independent and unchanged. The old endpoint returns
404. Older backends without `app_version` simply suppress notifications.

`releaseCheck.test.js` covers validation, HTTP/network/timeouts, body limits,
cache expiration, independent tabs, lock coordination, coalescing and cancellation.
`UpdateNotification.test.js` covers the delayed/visible/authenticated lifecycle,
expiry without polling, quiet failures, metadata compatibility, accessible links,
mobile layout and persistent dismissal. All GitHub responses are simulated.

Both upstream and fork 9Router sidebars wait 2.5 seconds, silently ignore check
failures and render a conditional notice. Their server route caches npm metadata
for an hour and uses numeric core comparison. Usage Dashboard adopts the quiet
delayed UX, but uses browser GitHub requests, strict metadata validation, embedded
artifact compatibility and development-channel semantics.
