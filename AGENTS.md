<!-- BEGIN project-workspace managed rules -->
## Project workspace files

- Put AI-only intermediate files under the project `.codex/` directory and register every created file in `.codex/manifest.json` through the project-workspace manager.
- Put conversation handoff documents under `.codex/handoffs/` and register them as `supporting` files.
- Keep formal source code, tests, configuration, environments, reproduction scripts, inputs, and deliverables in their normal project locations.
- Treat existing and user-supplied files as inputs. Do not move, overwrite, register, archive, or clean them merely for tidiness.
- Only an explicit project-workspace finalization may preview or dispose of registered internal files; never permanently delete them.
- Create a baseline only after the full workflow is approved and the user explicitly asks. Never migrate a step into the formal project until the user explicitly starts that step.
- Once formal migration starts, treat baseline implementation and outputs as frozen reference. Formal project files are authoritative.
<!-- END project-workspace managed rules -->

## Workspace scope

- The parent project's `.codex/` stores the overall project direction, milestones, hardware/software coordination and project-wide handoffs.
- This repository's `.codex/` stores code-specific design, builds, tests, debugging, Git operation records and code handoffs. Register new internal files here using the project-workspace manager.
- Keep shared runtime documentation and source files in the normal engineering directories. Do not duplicate project-wide status between the two workspaces.
