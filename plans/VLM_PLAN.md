# Milestone: Qwen3-VL Integration for Cut Intelligence and Prompt Workflows

## Outcome
Integrate qwen3-vl into the existing cut pipeline so each cut can produce:
- A concise but detailed whole-clip overview for downstream LTX prompt building.
- A detailed first-frame description for Flux 2 Klein style-transfer prompting.
- Repeatable regeneration with history tracking.
- Fast copy-to-clipboard UX for all major text artifacts.

This milestone also adds a qwen-powered text helper for prompt composition, including a style/content combiner pattern.

## Why This Milestone
Current project flow supports cut upload, style-transfer image generation, and video takes, but it does not persist or expose VLM-derived scene understanding. This milestone adds a durable "analysis layer" so prompts can be generated from structured creative context instead of manual inspection.

## Scope
In scope:
- qwen3-vl analysis on cut upload (video + first frame).
- Regenerate actions per cut.
- Prompt template system (versioned keys).
- Database schema for current outputs + run history.
- API routes for fetch/regenerate/use output in prompt generation.
- UI integration on cut cards and generation forms.
- Copy-to-clipboard affordances across new and existing prompt text areas.

Out of scope for this milestone:
- Multi-provider orchestration.
- Human approval workflows.
- Full prompt quality scoring/ranking.

## User Stories
1. As a user, when I upload a cut and it reaches `ready`, I can see "Clip Overview" and "First Frame Description" without leaving the cut view.
2. As a user, I can regenerate either description (or both) per cut if results are weak.
3. As a user, I can generate a Flux prompt draft that combines `{style}` and `{content}` (with optional cut context), then copy it in one click.
4. As a user, I can copy any major text block (clip overview, first-frame description, generated prompt, generation/take prompts) quickly and consistently.

## Technical Plan

### 1. Backend Prompt Profiles
Add centralized prompt profiles in backend (code-based templates, versioned keys):
- `clip_overview_v1`
- `first_frame_description_v1`
- `flux_style_content_prompt_v1`

Each profile defines:
- Purpose and expected output shape.
- Input variables.
- Recommended generation parameters (`temperature`, `top_p`, `max_tokens`).

### 2. Database Changes
Add two new tables so we can keep latest values and full history.

`cut_ai_state` (1 row per cut):
- `id` UUID PK
- `cut_id` UUID FK unique (`cuts.id`, cascade delete)
- `clip_overview_text` TEXT nullable
- `first_frame_description_text` TEXT nullable
- `first_frame_path` VARCHAR(1000) nullable
- `clip_overview_run_id` UUID nullable FK (`cut_ai_runs.id`)
- `first_frame_run_id` UUID nullable FK (`cut_ai_runs.id`)
- `clip_overview_status` VARCHAR(50) default `pending`
- `first_frame_status` VARCHAR(50) default `pending`
- `last_error_message` TEXT nullable
- `created_at`, `updated_at` timestamptz

`cut_ai_runs` (append-only history):
- `id` UUID PK
- `cut_id` UUID FK (`cuts.id`, cascade delete)
- `analysis_type` VARCHAR(50) (`clip_overview`, `first_frame`, `flux_style_content_prompt`)
- `status` VARCHAR(50) (`queued`, `running`, `completed`, `error`)
- `prompt_key` VARCHAR(100) (ex: `clip_overview_v1`)
- `prompt_input` JSON
- `prompt_text` TEXT
- `response_text` TEXT nullable
- `model_name` VARCHAR(200)
- `prompt_tokens` INT nullable
- `completion_tokens` INT nullable
- `temperature` FLOAT nullable
- `max_tokens` INT nullable
- `error_message` TEXT nullable
- `created_at`, `started_at`, `completed_at`, `updated_at` timestamptz

Indexes:
- `ix_cut_ai_runs_cut_id_created_at`
- `ix_cut_ai_runs_cut_id_type_created_at`

Optional in same milestone (recommended):
- `prompt_drafts` table for reusable generated text snippets (especially Flux prompt drafts), with `cut_id`, `draft_type`, `input_payload`, `prompt_text`, `created_at`.

### 3. Celery Task Integration
Add new tasks in `backend/app/tasks/cuts.py` (or a new `tasks/vlm.py` module):
- `queue_cut_ai_analysis(cut_id)`
- `generate_clip_overview(cut_id, run_id, force=False)`
- `generate_first_frame_description(cut_id, run_id, force=False)`
- `generate_flux_style_content_prompt(cut_id, style, content, run_id)`

Pipeline behavior:
- After existing cut pipeline finishes and status becomes `ready`, enqueue clip overview + first-frame analysis.
- Persist run status transitions (`queued` -> `running` -> `completed`/`error`).
- Update `cut_ai_state` pointers to the latest successful run.

### 4. API Endpoints
Add routes under cuts:
- `GET /api/v1/projects/{project_id}/cuts/{cut_id}/ai`
  - Returns current state (both descriptions, statuses, last run metadata).
- `POST /api/v1/projects/{project_id}/cuts/{cut_id}/ai/regenerate`
  - Body: `{ "types": ["clip_overview", "first_frame"] }`
  - Creates new runs and queues tasks.
- `GET /api/v1/projects/{project_id}/cuts/{cut_id}/ai/runs`
  - Queryable history for debugging/audit.
- `POST /api/v1/projects/{project_id}/cuts/{cut_id}/ai/prompt-drafts/flux`
  - Body: `{ "style": "...", "content": "..." }`
  - Optional defaults from latest cut analysis text.

### 5. Frontend UX Integration
New UI module:
- `CutInsightsPanel.vue` embedded in expanded cut view above `GenerationList`.

Panel contents:
- `Clip Overview` section with status badge, timestamp, copy button, regenerate button.
- `First Frame Description` section with status badge, timestamp, copy button, regenerate button.
- `Regenerate All` action.
- Inline loading/error states per section.

Prompt helper:
- Add a `Generate Flux Prompt` helper in generation/take workflow.
- Pre-fill content from `first_frame_description_text` + `clip_overview_text`.
- Let user add/override style text.
- One-click copy for resulting prompt.

Copy UX standardization:
- Create shared `CopyButton` + `useClipboardCopy` composable.
- Add to:
  - Cut insights text blocks.
  - Generation prompt display (`GenerationCard`).
  - Take prompt display (`TakeCard`, keep existing behavior but migrate to shared component).
  - Flux prompt helper output.

### 6. Error Handling and Observability
- If qwen service is down, mark run `error`, keep cut usable, and expose retry CTA.
- Log per run id with model + token usage.
- Add lightweight health check usage of `QwenVLClient.check_health()` in route/service path before queueing optional auto-runs.

## Deliverables by Workstream
Backend:
- SQLAlchemy models: `CutAIState`, `CutAIRun` (and optional `PromptDraft`).
- Alembic migration(s) for tables and indexes.
- New schemas and routes.
- Celery tasks wired into existing cut completion flow.
- Tests for routes, task status transitions, and regeneration.

Frontend:
- Type updates in `frontend/app/types/index.ts`.
- Store module for cut AI data (`stores/cutAi.ts` or extension of `projects` store).
- `CutInsightsPanel.vue` + reusable copy helpers.
- UI actions for regenerate and flux prompt draft creation.

## Acceptance Criteria
1. Uploading a cut triggers automatic clip overview + first-frame description generation after cut status becomes `ready`.
2. Each cut shows both descriptions with clear status and regenerate controls.
3. Regeneration creates new run history rows and updates current visible description on success.
4. Flux prompt draft endpoint and UI helper produce copyable text using style/content inputs.
5. All major text artifacts in cut/generation/take flow have one-click copy behavior.
6. Existing generation/take features continue to work without regression.

## Suggested Build Sequence
1. Add DB schema + models + Alembic migration.
2. Implement backend prompt profiles + qwen orchestration service.
3. Implement Celery tasks and auto-trigger from cut pipeline.
4. Expose API routes for fetch/regenerate/history/prompt-draft.
5. Integrate frontend insights panel and copy helpers.
6. Add tests and run full regression checks.

## Open Product Decisions
1. Should auto-analysis run for every cut by default, or be project-toggle controlled?
2. Do you want history visible in UI now, or only latest output + regenerate in this milestone?
3. For Flux prompt drafts, should output be plain text only, or include structured fields (subject, style, camera, constraints) in addition to plain text?

