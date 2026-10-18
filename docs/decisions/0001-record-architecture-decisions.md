# 0001. Record architecture decisions

- Status: Accepted
- Date: 2026-10-18

## Context

Mohan reviews decisions and architecture rather than code, and work happens across many sessions. Reasoning must survive both.

## Decision

Record every significant decision as a short ADR in `docs/decisions/`, using [template.md](template.md). Log a one-line entry in the CONTEXT.md decision log. Accepted ADRs are superseded, never rewritten.

## Consequences

Decisions are traceable and reviewable. There is a small overhead per decision, which is worth it.

## Alternatives considered

- Decisions only in CONTEXT.md: too little room for reasoning and alternatives.
