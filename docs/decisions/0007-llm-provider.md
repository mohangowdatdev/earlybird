# 0007. LLM: Anthropic small model, optional and off by default

- Status: Accepted (activation deferred by [0012](0012-zero-cost-operation.md))
- Date: 2026-10-18

## Context

Rules can't read nuance like "remote, but must overlap US hours" or implied seniority. An LLM helps, but costs money, and Mohan isn't spending any yet.

## Decision

- The target provider is the **Anthropic API** with a personal key, using the current small, cheap Claude model. The model id lives in config, verified against the docs at build time; it looked like `claude-haiku-5-5` on 2026-10-18.
- Use the **Batch API** for non-urgent scoring (submitted in one run, collected in the next), **prompt caching** for the profile and rubric, and **strict JSON** validated by pydantic.
- Daily call caps apply, with a stricter cap on the public plane.
- **The LLM is optional and off by default.** Everything works rules-only. A local model (Ollama) may be added as a free provider behind the same interface.

## Consequences

- An `LLMProvider` interface with `none` as the default.
- When the LLM is off, more jobs land in maybe. That's acceptable under fail-open.

## Alternatives considered

- **Other hosted providers:** no advantage for this project; one provider keeps it simple.
- **LLM mandatory:** conflicts with zero spend.
