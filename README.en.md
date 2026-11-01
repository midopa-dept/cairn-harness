# Cairn Harness

[한국어](README.md) · English

Cairn is a **small declarative Harness** for software projects in which LLM agents change code over long periods. Eight files placed inside the project set out, as a contract, authority, task state, verification and acceptance, evidence, recovery after interruption, and closing procedures. Existing agent runtimes such as Claude Code and Codex read and follow this contract.

> **Current public release:** `1.0.0-candidate.5` (`contract_version` 3, Task `schema_version` 3) + companion validator `cairn_check` 0.3.0
> This is a release candidate, not the final `1.0.0`. It is still being validated through continued use in real projects.
> This release does not automatically verify or enforce the order of recording attempts before execution ([Current limitations](#8-current-limitations)).
> Per-release changes are listed in the [CHANGELOG](CHANGELOG.md).
> The review and decision history behind this release is in the [design notes](docs/design-notes/README.en.md).

## Contents

1. [What is Cairn?](#1-what-is-cairn)
2. [Why is it needed?](#2-why-is-it-needed)
3. [Quick start](#3-quick-start)
4. [Key features](#4-key-features)
5. [Usage example](#5-usage-example)
6. [Validator and scope of guarantees](#6-validator-and-scope-of-guarantees)
7. [Detailed docs, change history, and design background](#7-detailed-docs-change-history-and-design-background)
8. [Current limitations](#8-current-limitations)

---

## 1. What is Cairn?

Cairn is **a project-local contract that agents follow**. The files copied into the target project root declare the following.

- Who can do what at which stage (authority and roles)
- Which stages a task goes through to finish (workflow and Task Packet)
- What counts as verification, what counts as acceptance, and what counts as closing
- Which changes need human approval (Human Gate)
- Where and how to leave evidence, and where to resume after an interruption

Cairn is **a declarative Harness, not a standalone agent runtime.** It has no program that runs commands or enforces authority. The agents and people working on top of it are the ones who interpret and keep the contract. Do not assume that Cairn provides isolation or authority enforcement that the actual runtime does not provide.

### Using it with Claude Code and Codex

The two runtimes use **the same Core semantics**. There is only one shared operating contract, `AGENTS.md`. Each runtime adapter describes **only how to carry out** that meaning, without changing it.

| runtime | Entry point | adapter |
|---|---|---|
| Claude Code | `CLAUDE.md`: two lines that import `@AGENTS.md` and `@.harness/adapters/claude-code.md` | [`.harness/adapters/claude-code.md`](.harness/adapters/claude-code.md) |
| Codex | Reads `AGENTS.md` natively | [`.harness/adapters/codex.md`](.harness/adapters/codex.md) (read at admit and recover) |

An adapter covers runtime conventions: how capabilities map to actual tools, how to launch an independent context, the attempt recording order, commit trailers, and similar. An adapter cannot change the meaning of Human Gate, acceptance, authority, requirements, or next action. If the two conflict, the shared contract takes precedence.

### What Cairn does not include

- An agent runtime or agent spawning service
- Model/provider adapters (the two runtime adapter files are documents that describe how to carry out the contract, not executable code)
- A sandbox or OS-level permission enforcement
- A graph database, vector database / embeddings
- A CI/CD framework or automatic update service
- A general-purpose semantic validator (a deterministic integrity checking tool, `cairn_check`, is provided as an optional companion)
- Automatic verification or enforcement of the order of recording attempts before execution

---

## 2. Why is it needed?

When LLM agents change the same project across many sessions, "does it do the next task well" is not enough. Over time, the following problems pile up.

| Problem | How Cairn responds |
|---|---|
| **Context loss and bloat.** When the session changes, earlier decisions and their rationale are lost. Reading the full history every time makes the context grow | Keeps task state in a single Task Packet and retrieves only the needed material, step by step ([4.6](#46-progressive-retrieval)) |
| **Confusing authority with task state.** It becomes unclear who can change what, and how far a task has progressed | Computes authority as role ∩ current stage ∩ Task scope, and writes state only in a fixed vocabulary ([4.1](#41-authority-and-roles), [4.2](#42-workflow-and-task-packet)) |
| **Confusing verification with acceptance.** "Tests passed", "review done", and "committed and delivered" get collapsed into one "done", and the agent that built the work accepts it itself | Separates `VERIFIED`, `ACCEPTED`, and `CLOSED`, and forbids producer self-acceptance ([4.3](#43-independent-review-and-acceptance)) |
| **Careless handling of high-risk changes.** Changes such as authentication or DB migrations go through the same flow as ordinary work | Defined risk categories get human approval before they take effect ([4.4](#44-human-gate)) |
| **Failed recovery after interruption.** On restart, earlier attempts, failures, and judgments disappear, or the same effect runs twice | Records attempts and resume points in the Packet, and checks them against Git state when work is taken over ([4.7](#47-recovery-and-handoff)) |
| **Mixing past evidence with current canonical sources.** A PASS for an earlier candidate is used as if it were valid for the current one, and stale documents mix with current ones | Binds evidence to candidate and scope, seals closed records, and sorts documents by class and temperature ([4.5](#45-evidence-and-artifact-lifecycle)) |

Cairn's goal is not to make all work heavy. **It keeps routine work light and applies a stronger contract only to risky changes.**

---

## 3. Quick start

### 3.1 Installation

After getting this repository, copy the 8 distribution files into the target project root. Do not miss the hidden directory `.harness/`. Run the commands below from the working directory where you will get this repository (outside the target project). Change only the `TARGET` value on the first line to the **existing** project directory where you will apply Cairn.

```sh
TARGET="$HOME/my-project"
git clone https://github.com/midopa-dept/cairn-harness.git
cp cairn-harness/AGENTS.md cairn-harness/CLAUDE.md "$TARGET/" && cp -R cairn-harness/.harness "$TARGET/"
```

Always wrap `"$TARGET"` in double quotes so that paths with spaces work. If the `TARGET` directory does not exist, the first `cp` fails, and because of `&&` the `.harness/` copy does not run either. If the target project already has `AGENTS.md`, `CLAUDE.md`, `.harness/`, or other agent instructions, do not run this command. Review the conflicts and merge by hand (`cp` overwrites files with the same name). `tools/` is not something you copy.

| Distribution file | Role |
|---|---|
| `AGENTS.md` | The shared operating contract all runtimes follow (human-readable form). Entry point for Codex |
| `CLAUDE.md` | Entry point for Claude Code. Imports `AGENTS.md` and the Claude Code adapter |
| `.harness/core.yaml` | lifecycle, role, authority, guard, graph, subgraph, schema, core policies |
| `.harness/project.yaml` | Project-specific local settings |
| `.harness/task.example.yaml` | Task Packet template |
| `.harness/distribution.yaml` | Distribution version, content ID, payload SHA-256 |
| `.harness/adapters/claude-code.md` | How to carry out the contract in Claude Code |
| `.harness/adapters/codex.md` | How to carry out the contract in Codex |

### 3.2 Project settings

Set the project-specific values in `.harness/project.yaml`.

- `project_id`, `artifact_roots` (roots of the material the agent retrieves), `task_root` (default `.harness/tasks`)
- `runtime.access_boundary` and `judgment_boundary`: persistent execution boundaries that span multiple Tasks
- Optional `layout`: per-path artifact class, evidence root, and the locations of the relocation and delivery ledgers
- Optional `extra_human_gate_tags`: project categories added to the default Human Gate categories

Settings do not grant new execution authority. Per-Task user delegation is not accumulated in settings. It goes in each Task Packet's `scope.authorization`. You do not have to fill these in yourself from the start. In the bootstrap below, the agent fills them in based on the user's request.

### 3.3 Starting the first Task (bootstrap)

When the settings are empty and there is no active Task, and you give the project goals and requirements, the agent takes that request as a bootstrap delegation.

```text
This project is Booklog, a personal reading log service.
Bootstrap and proceed according to the Cairn included in the current project.

Key requirements:
- ...
- ...
```

Following the contract, the agent prepares the following.

1. Checks the repository and existing instructions, read-only
2. Structures the given requirements with their sources and identifies only the real open decisions
3. Writes `project.yaml` and the bootstrap Task Packet (copies `task.example.yaml` into `task_root` and records the `content_id` from `distribution.yaml` in `harness_snapshot`)
4. Organizes goals, requirements, core user flows, initial domain/data concepts, and the verification strategy into canonical documents
5. Prepares the canonical index and the first implementation Task Packet
6. Stops only at the Human Gates that are needed

Bootstrap also goes through verification, non-producer acceptance, and closing. The user does not need to re-explain the Harness operating rules in every prompt.

### 3.4 Using the validator (optional)

`cairn_check` is a report-only checking tool in this repository's `tools/`. You do not need to copy it into the target project. You run it with `--project` pointing at the target project. It requires Python 3.9 or later and `ruamel.yaml`. Use `TARGET` as-is, in the same shell and the same working directory as in 3.1. Install into a virtual environment so the system Python is not changed.

```sh
python3 -m venv cairn-venv
. cairn-venv/bin/activate
python3 -m pip install -r cairn-harness/tools/requirements-dev.txt
python3 cairn-harness/tools/cairn_check.py --version
python3 cairn-harness/tools/cairn_check.py --project "$TARGET" check
python3 cairn-harness/tools/cairn_check.py --project "$TARGET" health
```

Once a Task Packet exists, you can check the next action. Replace `PACKET` with the Packet path relative to the project root. The target project must be a Git repository (`--git`).

```sh
PACKET=".harness/tasks/my-first-task.yaml"
python3 cairn-harness/tools/cairn_check.py --project "$TARGET" next-action --packet "$PACKET" --git
```

The exit codes of `check` are 0 `PASS`, 1 `FAIL`, 2 invocation error, and 3 `INCONCLUSIVE`. In a new project with no Task Packets, getting 3 because of `no_packets` is normal. 3 is not success. It means a person needs to check why evaluation did not happen. Details are in [Chapter 6](#6-validator-and-scope-of-guarantees) and [`tools/README.md`](tools/README.md).

### 3.5 Projects using an earlier release

Projects that already applied `1.0.0-candidate.4` or earlier do not change automatically. Review the following in a separate update Task, then apply the changes.

- The diff between the two distributions and how it applies to the project. In candidate.5 the distribution grew from 5 files to 8 (merge if an existing `CLAUDE.md` is present).
- Do not modify existing Packets. Each Packet is interpreted under the contract of its own `harness_snapshot`, and new rules are not applied retroactively.
- Starting with new Task Packets, use `schema_version` 3 and the new `harness_snapshot`.
- `project.yaml` can keep using schema 1. To use `layout` and `health`, raise it to schema 2.
- Upgrade the validator to 0.3.0 (for 0.2.1's under-checking, see [6.3](#63-areas-not-validated-automatically)). For candidate.4 Packets, if you supply the candidate.4 `core.yaml` with `--contract <content_id>=<path>`, they are checked under that contract.

For differences between releases, see the [CHANGELOG](CHANGELOG.md).

---

## 4. Key features

All the features below are one contract that works together in the current release. The normative sources are [`AGENTS.md`](AGENTS.md) and [`.harness/core.yaml`](.harness/core.yaml).

### 4.1 Authority and roles

An agent's actual authority is not set by a role name alone.

```text
effective authority = role allow ∩ current workflow node allow ∩ Task scope.allow
                      (all denies and path restrictions also apply)
```

- There are 9 roles: coordinator, specifier, designer, planner, executor, verifier, reviewer, integrator, and steward. For example, an executor can change outputs but cannot accept them. A reviewer can review and accept but cannot modify outputs.
- Lower layers can only narrow authority. They cannot silently widen it. Functions that are not declared are forbidden.
- Writes apply only to paths listed in `scope.write`, and reads only to paths listed in `scope.read`.
- `scope.authorization` is the location and content of the actual user delegation. The agent cannot create authority for itself. A new session's delegation is only appended, with date and actor.
- If the delegation sentence sets a final stage (for example, up to acceptance), the agent goes only up to that stage and only reports the next stage.

### 4.2 Workflow and Task Packet

One task is one **Task Packet** (YAML). A Packet holds, in one place, the purpose, scope and delegation, current stage and actor, acceptance criteria, a manifest of related materials, the candidate, verification evidence, decisions, delivery, and recovery state. The default is not to produce separate plans, reviews, and reports each time, but to keep the minimum state needed to resume in a recoverable form.

The stages of the default workflow graph `standard-change` are as follows. Each stage defines its participating roles, allowed functions, and entry conditions (guards).

```text
admit → plan → execute → verify → accept → close
            (on failure or interruption, move to recover from any stage, then return)
```

There are four lifecycle states, and none substitutes for another.

| State | Meaning |
|---|---|
| `OPEN` | Task obligations are being carried out, or the candidate changed and judgment is being prepared again |
| `VERIFIED` | Applicable verification evidence exists for the current candidate's required criteria. Not acceptance |
| `ACCEPTED` | An authorized non-producer accepted the current candidate. Not closing |
| `CLOSED` | Acceptance, delivery, handoff of remaining obligations, and cleanup are finished |

```text
PASS ≠ ACCEPTED
VERIFIED ≠ CLOSED
commit/push ≠ product acceptance
child ACCEPTED ≠ parent ACCEPTED
```

- A guard is a declaration for judging whether there is evidence that it is satisfied. It is not automatically executed code.
- The next thing to do is derived from a fixed vocabulary (`none`, `recover`, `reconcile_checkpoint`, `complete_admission`, `plan`, `request_human_gate`, `execute`, `verify`, `independent_review`, `accept`, `deliver`, `settle_close`) and a fixed order. Given the same Packet and Git state, the result must be the same no matter which runtime reads it.
- When a large task is split into child Tasks, the parent owns one **Coverage Matrix**. It disposes of every structural unit of the promised canonical sections as one of `owned`, `deferred`, `excluded`, or `informative`. Each child refines its own rows into criteria. Rows are bound to the canonical source by excerpt and fingerprint, so when the canonical source changes, this shows up as drift (`suspect`, `ambiguous`, `missing`).
- Records not used by guards go in a decision with `kind: record` and a `subkind`. Project extension information goes in `local`.
- Each Packet is interpreted under the contract of its own `harness_snapshot` (the distribution's `content_id`). Updating the Harness does not apply new rules retroactively to existing Packets.

### 4.3 Independent Review and Acceptance

- **A producer that created or modified a candidate cannot accept that candidate.** This holds even if it changes role, context, runtime, or ID.
- The acceptor must be a real actor different from the producer. **It may be the same model.**
- Required independent judgment is decided by its properties. It must be an actor different from the producer. It must not inherit the producer's conversation. It must start only from bounded inputs such as the frozen candidate, criteria, and source materials. Forking, resuming, or continuing a conversation is not independence.
- The means differ by runtime. Claude Code uses a subagent that is not a fork, or a new `claude -p` process. Codex uses a new `codex exec` process (see each adapter). A new session that the user opened in that way also works. Record the means and inputs used.
- A different runtime alone is not independence. Even a different runtime does not claim separation if it received the producer's reasoning as input.
- An eligible non-producer reviewer can go as far as acceptance (`ACCEPTED`). If a reviewer modifies the candidate, that reviewer becomes a producer.

### 4.4 Human Gate

Changes in the following default categories need explicit human approval before they take effect. A project can only add categories, not remove them.

`architecture` · `authentication_security` · `db_migration` · `canonical_requirement` · `production_effect` · `equivalent_high_impact`

Judgments fall into three classes.

| class | Meaning | Handling |
|---|---|---|
| derivable | A single answer follows from canonical sources, decisions, and evidence, and it is not in a high-risk category | Proceed and record the source of the derivation |
| ambiguous_semantic | Two or more legitimate interpretations, each with a source that can be cited | Human Gate question |
| high_impact | The meaning is clear, but it falls into one of the categories above | Explicit approval bound to the plan identity (`plan.identity`) |

- Ask only one question at a time. Attach 2–3 meaningful options, short pros and cons, and a recommendation with its reason. Do not ask again about answers that are already settled.
- Do not lower a class or skip the Gate based on model confidence or self-assessment.
- Reuse a past approval only within the same scope. Do not extend it automatically to new changes.

Human Gate is not a device for inserting a person into every task. It marks **authority boundaries that the agent must not cross on its own**.

### 4.5 Evidence and Artifact Lifecycle

- **Evidence is bound to candidate and scope.** Use a past PASS or approval only after checking that it applies to the current candidate, scope, and release. When the candidate changes, verify or accept the needed scope again.
- **No proxy observation.** These observations are not PASS: a CSS check in place of a touch requirement, structure or accessibility checks in place of visual quality, desktop emulation in place of a real device, internal metrics in place of perceived latency, or a fallback run in place of the primary path. If there is no means of observation, the result is `not_run`.
- **Evidence manifest.** Each Task writes new evidence only to its own namespace (`layout.evidence_root/<Task ID>`). It classifies the evidence as authoritative (records that acceptance relied on directly), supporting (summaries for explanation and reproduction), or raw (logs, screenshots, and so on).
- **Artifact class and temperature.** Documents are divided into canonical, operational, decision, task, evidence, raw_evidence, and historical. Retrieval priority is hot, warm, or cold. Class is not stored. It is computed from `layout`, Task state, and the manifest. The recommended structure is `docs` = documents for understanding the current project, and `.harness` = Tasks, evidence, and provenance.
- **Sealed.** Packets and evidence whose owning Task is `CLOSED` are not modified, overwritten, or deleted. Re-runs go in a new Task namespace, and corrections are left as new records.
- **Relocation ledger.** When moving a document, append from, to, and content identity to the ledger. Old paths in historical Packets are not modified. They are resolved through the ledger. If the content changes, it is a new version, not a move. Cleanup and compression are not deletion.
- **Residual.** Remaining risk is handed off in a `risk`, `owner`, `condition` structure (optional `id`, `owner_kind`, `owner_ref`, `due`). The closing Task is not set as its own owner. Resolution, replacement, transfer, or acceptance of a previous Task's residual is appended to the follow-up Packet's `delivery.residual_dispositions`.

### 4.6 Progressive Retrieval

Cairn does not put the whole project history into the initial context every time.

```text
ID / metadata → short summary/title → relevant excerpt → full artifact only when needed
```

- Even the contract itself is read only for the keys needed (the current graph, node, role, Packet criteria, and so on).
- For closed Tasks, only objective, state, delivery, and authoritative evidence are read by default. Supporting and raw evidence are read when needed, with a reason recorded.
- Before plans and criteria are finalized, related shared obligations (requirements, security, architecture, and so on) are checked in a bounded way against the IDs, titles, and scope of application in the canonical index (applicability check).
- A small task-local Artifact Graph is derived deterministically **only from explicit references in canonical sources**. **The absence of an edge in the graph is not taken to mean that no related requirement exists.** If something is not found or its applicability is unclear, it is recorded as unresolved and the related claim is held back.

### 4.7 Recovery and Handoff

- **The only authorities for state are repository bytes, Git identity, the Task Packet, durable evidence, and records of user decisions.** State that exists only in runtime memory, threads, or conversation reasoning is not authority, and another runtime cannot take it over.
- Effectful execution (file writes, implementation steps, test and verification runs, test or probe runs during review or acceptance, commands with external effects) is recorded in `recovery.attempts` before it starts, and its status and receipt are updated when it ends. Effect-free state checks are not attempts. Examples are reading the Packet or Git, working out the next action, deterministic contract checks, and capability checks.
- **Execution that is not clearly effect-free (inline code, scripts, conversion commands, and so on) is treated as effectful: record the attempt first, then run it.** The same applies to reviewers and acceptors. Before running a test or probe during review or acceptance, they first record their own attempt. The record is not put in the same write batch as the effect. It is saved first, and the Packet is checked to be readable.
- This order is **a contractual obligation, and this release has no tool that automatically checks or enforces it.**
- The number of attempts stays within a finite per-Task limit (`max_attempts`). Failure and interruption records are not deleted, and the limit is not reset at will.
- At points where work may stop or another runtime may take over, `recovery.checkpoint` (base commit, intended uncommitted paths, completed/remaining steps) is kept in line with reality.
- The side taking over reads the Packet and checks Git HEAD and the working tree against the checkpoint. If there are changes whose origin cannot be explained, it sets `recovery.status: blocked` and does not proceed until the user confirms. It does not erase them with reset, clean, or stash.
- In the same working tree, two runtimes do not work on the same Packet or on overlapping write scopes at the same time.

### 4.8 Cross-runtime Portability

- The contract speaks in terms of 10 capabilities, not tool names: `read_files`, `edit_files`, `execute_commands`, `git`, `network`, `spawn_independent_context`, `browser_observation`, `production_read`, `production_write`, `human_interaction`.
- At admit, recover, and runtime switches, the needed capabilities are actually observed and recorded in `runtime_observations` as `available`, `unavailable`, `gated`, or `not_checked`. A missing capability is not assumed to succeed. Its handling (`alternate_path`, `not_available`, `not_run`, `blocker`) is recorded separately. A declaration is not authority.
- Record the runtime family in `actor.runtime`. The recommended actor ID format is `<runtime>-<task>-<role>`.
- If runtimes judge differently at a deterministic boundary (state, node, authority, need for a Gate, candidate identity, acceptance eligibility), this is treated as a defect in contract interpretation, not as an escalation. `cairn_check next-action` computes the reference values for these boundaries.

### 4.9 Project Health

`cairn_check health` looks at the freshness of the project's information structure, separately from per-Task checks. It reports index freshness, reference resolution, relocation integrity, writes and modifications to sealed paths, residual liveness, raw evidence location and size, concurrent writes, verification surface drift, and adapter drift as `error`, `warning`, `info`, or `not_checked`. With an optional verification registry, it can find "runners you thought were verified but that are missing from the suite." Health results are not judgments about authority, acceptance, or Human Gate.

### 4.10 Git Closeout

In a Git project, if delegation or policy allows commit/push, a working remote exists, and the only changes are within the Task scope, a completion-style closeout is performed by default. Completion is not just `git push`. It is the following flow.

```text
Check final diff
→ Confirm verification / non-producer acceptance
→ One completion commit
→ non-force push
→ Confirm local/remote target identity
→ Confirm clean working tree
→ Record actual delivery evidence
```

- Facts that cannot be written into the Packet in advance, such as the close commit, are not left only in the conversation. They are recorded in `layout.delivery_ledger` (JSON Lines, append-only).
- No force push, destructive reconciliation, inclusion of out-of-scope changes, or unapproved history rewrite.
- Being a Git project or having a remote is not authority. If Git, delegation, or a remote is missing, this is not dressed up as a product failure. Only the narrow user action that is needed is reported.

---

## 5. Usage example

This is the flow of a routine task within an already approved requirement, such as a feature for renaming a bookshelf. It starts in Claude Code and moves to Codex. Stage names are nodes of the `standard-change` graph.

1. **admit — intake.** The user asks Claude Code to implement the feature. Claude creates a new Task Packet and writes the original delegation text to `scope.authorization` and the write scope to `scope.write`. It observes the needed capabilities and records them in `runtime_observations`.
2. **plan — planning.** It narrowly retrieves only the related requirements and shared obligations (applicability check), and sets the acceptance criteria and the attempt limit. No high-risk category applies, so there is no Human Gate.
3. **execute — implementation.** It records an attempt before writing files, and updates status and receipt after implementing.
4. **Interruption and handoff.** The session stops partway through implementation and leaves `recovery.checkpoint` (base commit, intended uncommitted paths, completed/remaining steps). In the next session, Codex reads the Packet, checks the checkpoint against Git state with `cairn_check next-action --packet <Packet> --git`, and continues the remaining implementation. When the output version is frozen as a candidate, both actors, Claude and Codex, are recorded as producers.
5. **verify — independent review.** A new reviewer context that does not inherit the producer conversation (for example, a new `claude -p` process) gets only the frozen candidate, the criteria, and the source material paths. As long as it is an actor different from the producer, it may be the same model. The reviewer does not modify the candidate. It judges each criterion and records the results in the Packet's `decisions`.
6. **accept — acceptance.** If the reviewer is an eligible actor not on the producer list and the required criteria are met, it accepts the candidate as `ACCEPTED`. A producer does not accept its own candidate.
7. **close — closing.** The Task becomes `CLOSED` after a final diff check, one commit, a non-force push, confirmation of local/remote identity and a clean tree, and a delivery ledger record. Remaining risks are handed off with an owner and conditions.

For a high-risk task that changes the login or session authentication method, the flow is the same, with the following additions.

- Retrieve the authentication/security canonical sources and the related architecture canonical sources, and check the affected ownership, session, and persistence obligations.
- Make the plan and the Review Brief concrete, and **before the actual change**, get Human Gate approval bound to that plan identity.
- Widen verification to match the affected scope, and carry out the needed independent judgment and non-producer acceptance.

---

## 6. Validator and scope of guarantees

### 6.1 The role of `cairn_check`

`cairn_check` 0.3.0 is a **report-only companion tool** that computes the Cairn contract's deterministic integrity rules (VS0–VS6) and deterministic projections (next action, project health, relocation, evidence tier).

- It is not one of the 8 distribution files. The tool version is not part of the contract `content_id`, and changing the tool does not change the contract `content_id`.
- The tool is not authority. It does not modify Packets, Coverage Matrices, or canonical sources, and it does not create lifecycle transitions, decisions, or acceptance.
- Without the tool, a person or agent can carry out the rules and order in `core.yaml` `validation_contract.companion` directly (record method `manual` and the scope covered).

| Command | What it does |
|---|---|
| `check` | Checks Packets and Coverage Matrices (syntax → schema → links → matrix → drift → ownership) |
| `skeleton`·`rows`·`seed` | Prints a Coverage Matrix draft, retrieves child rows, and assembles the full canonical text for rows owned by a criterion |
| `next-action --packet PATH [--git]` | Deterministic projection of state, node, authority, Human Gate, candidate, actors excluded from acceptance, checkpoint comparison, and next action. The reference values for handoff between runtimes |
| `health` | Project health report |
| `relocations` | Checks the relocation ledger and resolves old paths |
| `evidence` | Aggregates evidence tiers per Task |

### 6.2 The difference between PASS and ACCEPTED

| | Meaning | Who |
|---|---|---|
| `cairn_check` `PASS` | Only that it passed the declared contract's **deterministic integrity checks** | The tool (or manual execution of the same rules) |
| `VERIFIED` | Eligible verification evidence exists that covers the current candidate's required criteria | The verifier and any needed independent review |
| `ACCEPTED` | An authorized non-producer accepted the current candidate | A reviewer or coordinator who is not the producer, or a person |

`PASS` is not correctness, product acceptance, or Human Gate approval. In CI, treat only exit code 0 as success. For 3 (`INCONCLUSIVE`), a person checks why evaluation did not happen.

### 6.3 Areas not validated automatically

- **Whether an attempt was recorded before the effectful execution** (the tool checks only the attempt entry schema and the `max_attempts` limit)
- Semantic correctness of content, sufficiency of scope declarations and task splitting, validity of `informative` judgments, whether a criterion actually implies the canonical obligation, and sufficiency of the observation method
- Authenticity of human approval, actual runtime actor isolation, and OS-level authority enforcement
- Determining whether an arbitrary shell command has effects

Behaviors to know:

- Validator 0.2.1 does not reject candidate.5 Packets and may PASS them without knowing the v3 rules. Use 0.3.0 or later for candidate.5 projects.
- When it meets a `contract_version` newer than the tool, it returns `INCONCLUSIVE` with `contract_newer_than_tool`.
- In `task_root`, a typo in kind or an empty YAML file only produces the warning `unrecognized_yaml` and does not affect the verdict. The allowed kinds will be defined in the next contract revision.

---

## 7. Detailed docs, change history, and design background

### 7.1 Documents

These documents are written in Korean.

| Document | Contents |
|---|---|
| [`AGENTS.md`](AGENTS.md) | The shared operating contract for all runtimes (normative source) |
| [`.harness/core.yaml`](.harness/core.yaml) | The canonical source for lifecycle, role, authority, guard, graph, schema, and policies |
| [`.harness/adapters/claude-code.md`](.harness/adapters/claude-code.md) · [`.harness/adapters/codex.md`](.harness/adapters/codex.md) | How to carry out the contract in each runtime |
| [`.harness/task.example.yaml`](.harness/task.example.yaml) | Task Packet template and field descriptions |
| [`tools/README.md`](tools/README.md) | `cairn_check` commands, exit codes, known limitations, and version |
| [CHANGELOG](CHANGELOG.md) | Changes in each public release |
| [Design notes](docs/design-notes/README.en.md) | How the mechanisms were extracted from a retrospective, and the review and decision history of each version (including 16 rejected independent reviews and the release-scope split). The English page summarizes the Korean notes |

### 7.2 Releases and distribution identity

`.harness/distribution.yaml` identifies the exact distribution by version, distribution ID, content ID, and the SHA-256 of each payload file. Values in `.harness/project.yaml` that you change after copying, and actual Task Packets, are not part of this identity. The version and content ID are for comparing shipped copies. They are not an instruction to look up another repository.

The current public release is **`1.0.0-candidate.5`**, not the final `1.0.0`. Its content ID is `sha256:7a3d4d4f69a346ef9fa4c44973276a7625e52b94e9e56dde742dba5e4b5e00ca`.

### 7.3 Design background and references

**Is Cairn Graph Engineering?** Partly, yes. Cairn distinguishes two kinds of graph.

| Area | Role |
|---|---|
| Workflow Graph | Execution order, roles, guards, state transitions, reusable subgraphs |
| Artifact Graph | Context retrieval cues for finding related material and canonical sources |

Recent Graph Engineering literature deals with externalizing task organization, agent coordination, and runtime state management as explicit graphs, and Cairn's Workflow Graph overlaps with this problem area. However, Cairn's scope also includes authority narrowing, Human Gate, evidence and candidate identity, progressive retrieval, acceptance isolation, recovery policy, distribution boundary, and Git closeout. So **Graph Engineering is one of the core components of the Harness, not a synonym for the whole Harness.** Cairn does not implement a stateful orchestration runtime such as LangGraph.

Cairn does not claim to be "an entirely new agent architecture." It drew on several existing ideas and close engineering precedents, or compared itself against them after the fact, and on that basis combined a project-local lifecycle, authority, and evidence contract. **The sources below are not evidence that experimentally validated Cairn's performance or effectiveness.** Read them while keeping "patterns referenced", "comparison targets", and "close precedents" apart.

Sources referenced in the initial design:

- **OpenAI — [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)**: How short entry points and project-local knowledge in the repository let agents move to the canonical sources they need. A reference point close to progressive retrieval and local operating rules. OpenAI's development speed and automated review/merge results are not used as performance claims for Cairn.
- **Anthropic — [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)**: An approach of retrieving needed information as it is needed and managing context. It connects to minimal seed + progressive retrieval. Cairn also takes into account the information loss of excessive summarization and the possibility of search failure.
- **Aider — [Repository map](https://aider.chat/docs/repomap.html)**: The idea of choosing relevant code by showing structure and symbols/signatures before file bodies was compared with the task-local manifest. Its ranking algorithm and token budget were not adopted.
- **Microsoft — [GraphRAG](https://microsoft.github.io/graphrag/)**: Relationship-based exploration was compared with the Artifact Graph. Cairn does not have an LLM infer relationships to build a knowledge graph. It **deterministically projects only explicit references in canonical sources**.

Workflow / Graph / Agent orchestration comparison sources:

- **Anthropic — [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)**: Predefined workflows, environment feedback, human checkpoints, and bounded iteration were compared with the Workflow Graph, Human Gate, and Recovery.
- **Feng et al. — [Graph Engineering in the Era of LLM Agents: From Individual Intelligence to System Intelligence](https://arxiv.org/html/2608.21156v2)**: A survey that systematizes task organization, agent coordination, and runtime state management from a graph perspective. Cairn is not an implementation of this whole taxonomy. It has a project-local workflow/state contract that overlaps with it.
- **LangGraph — [Overview](https://docs.langchain.com/oss/python/langgraph/overview), [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)**: A comparison target: a stateful orchestration runtime that provides StateGraph, checkpoints, and interrupt/resume. Cairn does not implement runtime persistence or automatic resume.
- **luxiaolei — [Graph Engineering](https://github.com/luxiaolei/graph-engineering)**: A close precedent that puts state, routing, guards, context, evaluation, and governance together in a project-local graph contract. Cairn uses a YAML-based Core/Task Packet and its own authority/evidence semantics.
- **context4ai — [Agent Graph](https://github.com/context4ai/agent-graph)**: A work-contract approach that uses current Facts and Outcome to limit the next route, the needed resources, and completion evidence. Its concerns partly overlap with Task Packet/context routing, but it is not the same runtime/SDK model.

Evidence / provenance / independent judgment sources:

- **Anthropic — [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)**: The separation of generation from evaluation, and context management in long sessions, were compared with the non-producer acceptance and bounded-context independent judgment policies. Its topology and performance figures are not used as validation evidence for Cairn.
- **W3C — [PROV-DM: The PROV Data Model](https://www.w3.org/TR/2013/REC-prov-dm-20130430/)**: The distinction among entity, activity, and revision was compared with candidate/artifact/evidence identity. Cairn does not claim to implement or conform to the W3C PROV ontology.
- **Edge et al. — [From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/html/2404.16130v2)**: The original GraphRAG paper. It was used to confirm a boundary, so that its performance on global questions and summarization over a document collection is not wrongly carried over to the Artifact Graph or to token savings.

The following are not rules taken directly from the sources above. They are **concrete semantics that Cairn chose as a project-local contract**.

- `Role ∩ Node ∩ Scope` authority computation
- `VERIFIED ≠ ACCEPTED ≠ CLOSED`
- Separation of child acceptance from parent acceptance
- Non-producer acceptance for every candidate
- Concrete risk categories for Human Gate
- One user decision question at a time
- An eight-file distribution snapshot (one shared contract and thin runtime adapters)
- Artifact Graph relations derived only from explicit references in canonical sources
- Conditional Git closeout

A related idea existing in prior literature is a different thing from that literature having derived or validated the contract above.

---

## 8. Current limitations

What has been confirmed in `1.0.0-candidate.5`:

- Static consistency of the declarative contract and the distribution boundary, and exact distribution identity
- Authority, lifecycle, and Human Gate semantics unchanged from candidate.4 (additions only), and backward compatibility with candidate.3/.4 Packets
- Deterministic checks of the companion validator
- Conformance in which Claude Code and Codex actually took turns running on a small fixture: an **observed run** in which Human Gate judgment, handoff in both directions, non-producer acceptance, and checkpoints held with the same meaning across the two runtimes. It is evidence for the scope of the observed scenarios and does not guarantee every run.

What this release **does not guarantee**:

- **Automatic verification or enforcement of the order of recording attempts before execution.** Recording an attempt before effectful execution is a contractual obligation, but this release has no tool that checks or enforces that order. Compliance must be confirmed by the runtime, the actor, and independent reviewers. In the actual conformance runs, too, the runtimes' compliance with recording in advance varied from run to run.
- Determining whether an arbitrary shell command has effects
- Reproduction of the conformance pass on every run. Run-to-run variance per scenario was not measured, and runtime paths with a browser and interactive session defaults were not tested.
- `next-action` projection for nodes inside a subgraph

What is not yet claimed empirically:

- Reduced token usage
- Higher task success rate
- Reduced agent hallucination
- Enforcement of actual runtime actor isolation
- Fitness for every project
- Independent performance gains from the graph structure itself

Items to check in particular when applying it to real projects:

1. How stably producer/acceptor separation actually holds in the runtime
2. Whether the cost of maintaining Task Packets is excessive for routine work
3. Whether progressive retrieval actually reduces the context/token burden without causing omissions

---

## Default language

The current distribution uses **Korean** as the default language for human-readable explanations, plans, reports, review notes, and handoffs. Identifiers, paths, API/CLI syntax, proper names, original sources, and automated tool output keep their original form. This README is an English translation; the contract files and the other documents remain in Korean.

## License

Cairn is distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.
