# Design notes

[한국어](README.md) · English

These notes describe the failures Cairn started from, and what each version tested, changed, and left unchanged. The current contract is defined by [`AGENTS.md`](../../AGENTS.md) and [`.harness/core.yaml`](../../.harness/core.yaml) at the repository root. The notes are **background** for that contract; they do not add or change rules.

The four detailed notes are written in Korean. This page summarizes all of them in English.

| Note (Korean) | Contents |
|---|---|
| [1. From retrospective to mechanisms](01-origins.md) | How 28 cases from a long-running agent development project were merged into seven mechanisms, and what was left out |
| [2. First application and candidate.4](02-candidates-1-4.md) | Independent audits, 15 observations from the first real application (Booklog), why the Coverage Matrix and the proxy-observation rule were added |
| [3. Sixteen REJECTs and a release-scope split](03-candidate5-reviews.md) | Real Claude Code ↔ Codex conformance runs, root-cause analysis of 16 rejected independent reviews, fixed stopping rules, the release-scope split and publication |
| [4. What did not change, and what people decided](04-decisions.md) | candidate.5 design decisions with rejected alternatives, human decisions, errata |

## Timeline

| Date (KST) | Event |
|---|---|
| 2026-09-21 | Retrospective cases R01–R28; seven mechanisms proposed. candidate.2 independent audit `CORRECTION_REQUIRED` → candidate.3 re-audit `READY_FOR_FIRST_APPLICATION`; first public release |
| 2026-09-28 | Observations BK-01–15 frozen after applying candidate.3 to Booklog |
| 2026-09-29 | candidate.4 published (Coverage Matrix, proxy-observation rule, structured residuals, `cairn_check` 0.2.1) |
| 2026-10-08 | candidate.5 version decision (HD-C5-01), implementation and first freeze, cross-runtime conformance starts, first independent review REJECT |
| 2026-10-09 | 16th independent review REJECT, release-scope split (HD-C5-03), release-scope independent review PASS + ACCEPT |
| 2026-10-10 | candidate.5 published (HD-C5-04) |

## 1. From retrospective to mechanisms

Cairn did not start from a blank design. It started from one earlier, private project where agents changed code over a long period. From its policy documents, acceptance records, raw run outputs, and post-mortem, 28 cases of "what nearly went wrong and what stopped it" were extracted (R01–R28). Each case was labeled by the kind of evidence behind it: read directly from the raw record, stated in a report at the time, post-hoc analysis, policy, or an already-approved design decision. Reading a report was never written up as re-computing its raw data.

Examples:

- Routine changes waited for approval each time. The post-mortem classified 49 of 59 human-intervention clusters as routine. → Work inside an existing delegation proceeds; only high-impact changes go to a person.
- Four child corrections were accepted while the whole project was still open. → Child acceptance is not parent acceptance.
- PASS, commit, and push were mixed up with acceptance and closure. → `VERIFIED ≠ ACCEPTED ≠ CLOSED`.
- Machine checks passed, but a question the user needed was missing. An independent review failed it, and the problem came back after the first fix. → Independent review against the actual outcome; the original FAIL is kept.
- A freshly spawned sub-agent read files outside its packet. → Logical independence is not access control; do not overstate isolation.
- After many passing regressions, an exhaustive audit found three defects with independent causes. → Test counts and mapping completeness are not correctness.

The cases were merged into seven mechanisms: bounded authority with explicit escalation (UM-01), claims bound to identified artifacts (UM-02), separate verification, acceptance, and closure (UM-03), independence for required judgments (UM-04), verification scaled to risk (UM-05), bounded recovery by reconciling what actually ran (UM-06), and minimal canonical context with derived navigation (UM-07). The first four are invariants. They are the backbone of the current contract: `Role ∩ Node ∩ Scope` authority, four lifecycle states, non-producer acceptance, Human Gates, candidate-bound evidence, and progressive retrieval.

Left out on purpose: human acceptance at every step, fixed repetition counts, a final audit every time, large snapshots and duplicated ledgers, one session per role, Git-SHA-only identity in Core, and graph or vector databases.

## 2. First application and candidate.4

candidate.2 failed an independent audit on one correction: nothing told the agent to check shared requirements that the artifact map did not link to. The current `AGENTS.md` line "a missing graph edge does not mean there is no relevant requirement" came from that. candidate.3 passed a bounded re-audit as ready for a *first application*, not as a final release.

candidate.3 was then applied, unchanged, to Booklog, a small personal reading-log service. Afterwards 15 observations (BK-01–15) were frozen before any change to Cairn, so later memory could not rewrite what had happened. The strongest signals were:

- When work was split into child tasks, some canonical requirements were assigned to no child, and integration did not catch it. → candidate.4 **Coverage Matrix**.
- Criteria were checked with weaker proxies than real use: only the fallback path, CSS computed style instead of real touch, accessibility checks instead of visual quality, desktop instead of the real mobile/dark environment. → candidate.4 **no proxy observation** rules.
- Deferred residual risks had no owner. → **structured residuals** (`risk`, `owner`, `condition`).
- The Packet schema drifted between tasks. → companion validator `cairn_check`.

Two research directions were explicitly kept out of Core: a richer artifact/provenance graph (`KEEP_MINIMAL_GRAPH`) and model-confidence-driven autonomy (`EXPERIMENT ONLY`). candidate.4's first independent review was REJECT because of one major validator finding. Only the validator was fixed; the contract bytes did not change. That is why the contract and the validator carry separate versions.

## 3. Sixteen REJECTs and a release-scope split

candidate.5 makes Claude Code and Codex use Cairn with **the same meaning**. It was tested with real cross-runtime runs: fresh `claude -p` and `codex exec` processes took turns on temporary fixtures, with no Cairn rules restated in the prompt. Six scenarios ran in both directions (12 runs): next-action projection, Human Gate and escalation class, one runtime stopping mid-implementation and the other resuming, one runtime's candidate reviewed and accepted by the other, stopping on an unexplained change, and not reporting PASS when failing evidence exists. Results were compared field by field against the projection computed by `cairn_check next-action`; no model graded another model.

The runs also exposed wording gaps. Given a new `claude -p` session opened by the harness, the Claude reviewer read the contract as "I must spawn the independent context myself" and stopped, while the Codex reviewer treated its own session as independent. The contract now defines an independent context by its properties (different actor, no inherited conversation, bounded input), not by who opened it.

Each frozen candidate went to a new non-producer reviewer session opened by the user. **All sixteen reviews were REJECT** (69 R-numbered findings including minor ones and some observations, plus 14 separately numbered observations). Early findings were in the validator (relocation, sealed records, residual transfer) and in the conformance judge. From the 9th review on, the largest group of findings was false PASSes in one development tool: a judge that tried to decide statically whether arbitrary shell, inline Python, or Ruby commands had side effects. Every fix produced a new form of the same problem, ending with `sort -ro <outside> input` and a heredoc delimiter `<<'EOF'X` that hid a command. The producer's own root-cause analysis (not an acceptance judgment) found **no defect in the Core contract** in reviews 9–13.

So the stopping rules were fixed in advance: shrink the judge to a small allowlist of provably read-only forms and treat everything else as a possible effect (false FAILs accepted by design); at most two more correction-and-review rounds; if blocking or major findings remain, stop and hand the decision to a person. Both rounds were used, the 16th review still found two major judge issues, and the work stopped.

The person decided (HD-C5-03) to split the release scope. The eight distribution files and `cairn_check` 0.3.0 (24 files, pinned by a `release_scope_id` hash) became the release scope. The command-string judge stayed an unaccepted development tool outside the published files. The 16th REJECT was not withdrawn, the two findings stayed open, and the obligation to record an attempt before any effect stayed in the contract; only *automatic proof* of that order was removed from what this release guarantees. A new Codex non-producer session reviewed the release scope: **PASS + ACCEPT** (0 blocking, 0 major, 2 minor). Publication was a separate Human Gate bound to the exact base commit, tree, README hash, content ID, and release-scope ID, and was recorded as complete only after the remote identity matched.

Lessons:

- If a verification tool is asked to decide something it cannot decide, reviews do not converge.
- Fix stopping rules before the cycle, not in the middle of it.
- A rejection can stay on record while a narrower scope is accepted, as long as both scopes and the open findings are written down together.
- Real runtime compliance varies between runs (10/12, then 12/12 on the same frozen candidate). Passing conformance is evidence for the observed runs, not a guarantee.

## 4. What did not change, and what people decided

candidate.5 kept candidate.4's core: `role ∩ node ∩ scope` authority, no self-acceptance, Human Gate categories, one question at a time, the four lifecycle states (no new state), the Coverage Matrix, and a validator that is never authority or acceptance. New requirements were added in a fixed order of preference: reuse → policy sentence → validator check → small optional schema → new artifact → subsystem.

Most design decisions compared two or three options. Examples: artifact class is computed from a path layout and a per-task evidence manifest instead of per-file front matter or a central registry; moved files are resolved through an append-only relocation ledger instead of rewriting historical packets; residual risks are closed by append-only dispositions in later packets instead of editing closed ones; escalation uses three structural classes instead of model confidence scores.

The human decisions were: the version label and `contract_version` 3 (HD-C5-01), the boundary of the attempt-before-effect rule (HD-C5-02), the release-scope split (HD-C5-03), and publication bound to exact identities (HD-C5-04). Each record also says what the decision did *not* approve. When a sentence turned out to be wrong, an erratum was appended instead of editing the original.

## Reading notes

- These notes summarize design records, review texts, and raw run data from a private development repository. Raw data and the paths and commits of private projects were not copied. Booklog is the author's personal project and is not public.
- Numbers are the values recorded at the time. They were not re-run or re-computed for these notes.
- Effects such as lower token use or higher task success were not measured ([README, Current limitations](../../README.en.md#8-current-limitations)).
