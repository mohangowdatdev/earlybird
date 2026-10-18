# 0010. Portal: FastAPI + HTMX instead of Streamlit

- Status: Accepted
- Date: 2026-10-18

## Context

The core interaction is a fast morning triage: many cards, many save/dismiss clicks, ideally keyboard-driven. Streamlit re-runs the whole script on every interaction, which gets slow with hundreds of cards and makes keyboard shortcuts awkward.

## Decision

Build the portal with **FastAPI + Jinja templates + HTMX**: server-rendered HTML, partial updates on click, keyboard shortcuts in a few lines of JS, and no frontend build step.

## Consequences

- Instant save/dismiss, keyboard triage, and real URLs per view.
- The same app becomes the API surface for a hosted version.
- Slightly more template work than Streamlit for charts and tables. Use a tiny CSS framework (e.g. Pico) to keep it simple.

## Alternatives considered

- **Streamlit:** fastest to prototype, worst for high-volume triage.
- **NiceGUI/Reflex:** heavier abstractions with less control.
- **SPA (React):** needs a JS build and toolchain.

## Update (2026-10-18)

The "tiny CSS framework (e.g. Pico)" consequence was replaced by a small hand-written design system (tokens + components, no build step), because Pico's defaults didn't give a polished dashboard. The decision itself (FastAPI + Jinja + HTMX, server-rendered, no frontend build) is unchanged. See [portal.md](../portal.md#design-system).
