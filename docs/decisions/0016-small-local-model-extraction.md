# 0016. Small local model for description extraction (Ollama, Qwen2.5 3B)

- Status: Accepted
- Date: 2026-10-19
- Refines: [0007](0007-llm-provider.md), [0012](0012-zero-cost-operation.md)

## Context

Many postings put the facts that matter in the description, not the structured fields: who may apply ("open to candidates in India", "must be authorized to work in the US"), experience, and stack. Rules catch common phrasings. Mohan asked for a tiny AI model for the rest, and spend must stay at zero.

## Decision

- **Rules first.** Description-aware rules plus a 182-skill taxonomy handle most jobs deterministically.
- **A small open model for the residue:**
  - `qwen2.5:3b` served by **Ollama**, run on the GitHub Actions runner (free for public repos) or on the laptop.
  - It only sees *tech* roles whose remote eligibility is unclear, plus data/ML/AI roles missing experience or stack.
  - It gets a trimmed description and must answer in a fixed JSON schema, validated with pydantic.
- **Fail-open merge with grounding.** The model may only fill gaps or widen what the rules found, never narrow. Each claim must be supported by the posting text:
  - "India OK" needs India, APAC or worldwide wording
  - a remote claim needs remote wording
  - an experience figure needs "N years" in the text
  - each skill must appear in the text
- **Bounded cost.** Each run has a time budget (25 min on Actions). The rest waits in a queue file kept in the repo's **Actions cache**, which is never published. A job with a description is never written to the public state.
- **Optional.** Setting `EARLYBIRD_LLM_PROVIDER=none`, or Ollama being unavailable, means rules only. A failed model call keeps the rule result.

## Benchmark (2026-10-19, real postings, Apple M4)

| Model | Speed | Behaviour |
| --- | --- | --- |
| qwen2.5:1.5b | ~5 s/job | **Rejected.** It labelled US-only and Poland-only roles "remote, India OK". |
| qwen2.5:3b | ~8 s/job | Conservative and mostly right (kept US/EU roles restricted; filled grounded YOE). |

Actions CPU speed is measured on the first runs and recorded here.

## Consequences

- Free and private, with no API key.
- Throughput is limited (dozens of jobs per run on a CPU runner). The queue plus prioritisation means unclear-remote jobs go first.
- Actions caches can be restored by workflows on pull requests. First-time contributors' workflows need approval (the GitHub default); keep that setting.
- Anthropic (ADR 0007) remains the upgrade path when there is a budget. The `OllamaExtractor` interface is where it would plug in.
