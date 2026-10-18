# 0015. Terms-restricted sources run privately; descriptions are never published

- Status: Accepted (Mohan to confirm)
- Date: 2026-10-18
- Refines: [0005](0005-public-private-split.md)

## Context

Verifying the board endpoints surfaced their terms:
- **Himalayas:** "Do not redistribute jobs to other job boards or aggregators."
- **Remotive:** do not submit its jobs to third-party websites.
- **RemoteOK:** allows reuse with attribution (a followed link back, and naming "Remote OK").
- **We Work Remotely:** publishes RSS feeds meant for syndication; its terms pages weren't reachable.

Separately, the public `state.db` is a downloadable file. Any job description inside it would amount to republishing descriptions.

## Decision

1. Every board adapter declares `PUBLIC_OK`. Boards with `PUBLIC_OK = False` (Himalayas, Remotive) are **private-plane-only**:
   - The public ingest skips them.
   - The laptop scheduler fetches them into the local DB with `visibility=private`, so they still reach Dawn.
   - The publish guard already refuses private rows.
2. **Descriptions are never stored in the public state.**
   - Extraction runs on the fresh fetch, and the text is then dropped.
   - The public dataset carries the extracted facts and stack tags.
   - Private-plane jobs keep their description locally.
3. RemoteOK attribution is shown wherever its jobs appear publicly (Earlybird Board, Phase 4).

## Consequences

- Personal use of every source is preserved, and the public dataset stays within each source's terms.
- The public board shows fewer board jobs. ATS feeds remain the core of coverage anyway.
- Private-only boards run only while the laptop is awake.
- Re-extraction with improved rules needs a re-fetch, which happens naturally because content changes trigger one.

## Alternatives considered

- **Publish everything with attribution:** conflicts with the Himalayas and Remotive terms.
- **Drop those boards entirely:** loses personal coverage for no reason.
