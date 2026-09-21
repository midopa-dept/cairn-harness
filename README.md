# Cairn Harness

Cairn is a small declarative harness for long-running agentic software projects. It defines lifecycle, authority, evidence, review, acceptance, recovery, and closeout contracts without requiring a dedicated runtime.

> Current distribution: `1.0.0-candidate.3`

## What is included

The distributable harness is intentionally small:

- `AGENTS.md` — human-readable operating contract for agents working in the project
- `.harness/core.yaml` — lifecycle, roles, authority, guards, subgraphs, schemas, and core policies
- `.harness/project.yaml` — project-local configuration template
- `.harness/task.example.yaml` — Task Packet template
- `.harness/distribution.yaml` — immutable distribution identity and payload hashes

Cairn is declarative. It does **not** include an agent runtime, tool adapter, sandbox, or policy-enforcement daemon. Runtime capabilities and isolation boundaries must be verified in the environment where Cairn is used.

## Install into a project

Copy `AGENTS.md` and the entire `.harness/` directory into the root of the target project. If the project already has agent instructions or harness files, review and merge conflicts instead of overwriting them blindly.

Then give the agent the project goal and requirements and ask it to bootstrap and proceed according to Cairn. Project-specific values in `.harness/project.yaml` and the first Task Packet are filled during bootstrap.

## Core properties

Cairn is built around several contracts:

- effective authority is narrowed by role, workflow node, and task scope;
- high-impact changes such as architecture, authentication/security, database migration, and canonical requirement changes require a human gate;
- verification, acceptance, and closeout are distinct states;
- a producer cannot accept its own candidate;
- context is retrieved progressively instead of loading project history by default;
- evidence and decisions stay bound to the candidate and scope they actually support;
- routine work proceeds automatically inside already-approved boundaries;
- Git closeout, when authorized and applicable, verifies the actual delivered remote state.

The normative details live in `AGENTS.md` and `.harness/core.yaml`.

## Language

The current distribution uses Korean as the default language for human-readable plans, reports, review notes, and handoffs. Identifiers, paths, APIs, CLI syntax, proper names, source evidence, and tool output retain their original notation.

## Distribution identity

`.harness/distribution.yaml` identifies the exact distributable payload using a version, distribution ID, content ID, and per-file hashes. Project-local configuration and Task Packets are not part of that immutable payload identity.

This repository currently publishes a **release candidate**, not a final `1.0.0` release.

## License

No open-source license has been selected yet. Public availability of this repository does not by itself grant reuse rights beyond those provided by applicable law and GitHub's terms. A license can be added once the distribution terms are chosen.
