# Narration App Plan

A mini app for generating voice narration from text using Dia (voice cloning) and Magpie (fast TTS). The goal is to produce ~3:30 of narrated audio composed of many individually generated segments, managed through a simple timeline UI.

## Architecture

```
narration/
├── app/
│   ├── main.py          # FastAPI server
│   ├── db.py            # SQLite setup + models
│   ├── services/
│   │   ├── dia.py       # Dia Gradio client (voice cloning)
│   │   ├── magpie.py    # Magpie NIM client (fast TTS)
│   │   └── sanitize.py  # Text sanitization
│   └── static/
│       └── index.html   # Vue 3 SPA via CDN
├── batch.py             # CLI batch generation script
├── script.txt           # Narration script (committed to git)
├── sample/              # Reference voice files
│   ├── Alice.wav
│   └── text.txt
├── output/              # Generated audio files (gitignored)
├── narration.db         # SQLite database (gitignored)
├── pyproject.toml
└── NARRATION_PLAN.md
```

## Services

| Service | Host | Use Case | Voice Cloning | Speed |
|---------|------|----------|---------------|-------|
| Dia | `192.168.5.253:7860` (configurable via `DIA_URL`) | Primary narration | Yes (from sample/Alice.wav) | Slow (~30-60s per segment) |
| Magpie | `192.168.6.3:9000` (configurable via `MAGPIE_URL`) | Quick drafts / previews | No (preset voices) | Fast (~2-5s per segment) |

## Data Model

### Segment (SQLite table: `segments`)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| position | INTEGER | Order in timeline (1-based) |
| text | TEXT | The narration text |
| sanitized_text | TEXT | Cleaned text sent to TTS |
| service | TEXT | "dia" or "magpie" |
| status | TEXT | "pending", "generating", "done", "error" |
| audio_path | TEXT | Relative path to WAV file in output/ |
| duration_seconds | REAL | Duration of generated audio |
| error_message | TEXT | Error details if failed |
| selected_variant_id | INTEGER | FK to active variant |
| created_at | DATETIME | |
| updated_at | DATETIME | |

### Variant (SQLite table: `variants`)

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| segment_id | INTEGER FK | References segments.id |
| text | TEXT | Text used for this generation |
| sanitized_text | TEXT | Sanitized text sent to TTS |
| service | TEXT | Service used for generation |
| audio_path | TEXT | Path to WAV file |
| duration_seconds | REAL | Duration |
| created_at | DATETIME | |

## Text Sanitization (`sanitize.py`)

Applied automatically before sending to any TTS service:

- Curly single quotes → straight `'`
- Curly double quotes → straight `"`
- Remove parentheses and their contents
- En/em dashes → hyphen or comma
- Ellipsis character → `...`
- Strip `[S1]` / `[S2]` speaker tags (added back programmatically by Dia client)
- Collapse multiple spaces
- Strip leading/trailing whitespace

## API Endpoints

### Segments
- `GET /api/segments` — List all segments ordered by position
- `POST /api/segments` — Create segment
- `PUT /api/segments/{id}` — Update segment text/position/service
- `DELETE /api/segments/{id}` — Delete segment
- `POST /api/segments/reorder` — Bulk reorder
- `POST /api/segments/import` — Import from text (one line per segment)

### Generation
- `POST /api/segments/{id}/generate` — Generate audio for one segment
- `POST /api/segments/{id}/regenerate` — Regenerate (creates new variant)
- `POST /api/generate/all` — Generate all pending segments sequentially
- `GET /api/segments/{id}/audio` — Stream the WAV file
- `GET /api/status` — Current generation status

### Variants
- `GET /api/segments/{id}/variants` — List variants for a segment
- `POST /api/segments/{id}/variants/{vid}/select` — Select active variant
- `GET /api/variants/{vid}/audio` — Stream variant audio
- `DELETE /api/variants/{vid}` — Delete a variant

### Other
- `GET /api/export` — Concatenate all segments into one WAV and download
- `GET /api/voices` — List available Magpie voices
- `GET /` — Serve frontend

---

## Completed Milestones

### Milestone 1: Project Setup + Database [DONE]
- [x] FastAPI app with SQLite, segment CRUD, text sanitization
- [x] Vue 3 SPA via CDN with Pico CSS
- [x] Script import (one line per segment)
- [x] `.gitignore` for `narration.db`, `output/`

### Milestone 2: Dia Voice Generation [DONE]
- [x] Async Dia client via httpx (upload reference audio, SSE polling)
- [x] Voice cloning from `sample/Alice.wav` + `sample/text.txt`
- [x] Generation lock (one at a time via asyncio.Lock)
- [x] Audio playback per segment, duration extraction

### Milestone 3: Batch Generation + Status [DONE]
- [x] Generate All endpoint with sequential processing
- [x] Status endpoint and UI status bar with spinner
- [x] `batch.py` CLI script for headless generation

### Milestone 4: Magpie Integration [DONE]
- [x] Magpie NIM client (form-data POST to `/v1/audio/synthesize`)
- [x] Per-segment service selector (dia/magpie)
- [x] Voices endpoint listing available Magpie voices

### Milestone 5: Export + Polish [DONE]
- [x] WAV concatenation export
- [x] Drag-to-reorder segments
- [x] Summary bar (segment count, done/total, duration)
- [x] Inline UI for add/delete (no browser popups)

### Milestone 6: Variants + Regeneration [DONE]
- [x] Variants table with full generation history
- [x] Regenerate with same or tweaked text
- [x] A/B comparison with per-variant audio players
- [x] Select active variant per segment
- [x] Auto-select new variant on generation

---

## Next Milestones

### Milestone 7: Projects
**Goal**: Introduce a project abstraction so each script import lives in its own workspace.

- [ ] Add `projects` table (id, name, description, created_at, updated_at)
- [ ] Add `project_id` FK to `segments` and `variants` tables
- [ ] `GET/POST /api/projects` — list and create projects
- [ ] `DELETE /api/projects/{id}` — delete project and all its segments/variants/audio files
- [ ] `POST /api/projects/{id}/import` — import script into a specific project
- [ ] UI: project switcher in the toolbar (dropdown or sidebar)
- [ ] UI: "New Project" creates a clean workspace
- [ ] UI: "Delete Project" removes everything (segments, variants, audio files)
- [ ] Importing a script into a new project does not affect other projects
- [ ] Output files organized by project: `output/{project_id}/`
- [ ] Migrate existing segments into a default project on first run

### Milestone 8: Voice Sample Management [DONE]
**Goal**: Support multiple voice samples and make it easy to experiment with different voices.

- [x] Add `voice_samples` table (id, name, audio_path, transcript, created_at)
- [x] Upload voice samples through the UI (WAV + transcript text)
- [x] Per-segment voice sample selection for Dia (dropdown in segment controls)
- [x] Per-segment Magpie voice selection (dropdown populated from `/api/voices`)
- [x] Preview a voice sample before using it (audio player in voice panel)
- [x] Ship with Alice as the default sample, allow adding more
- [x] Dia client accepts custom reference audio/text per segment
- [x] Voice samples panel with upload, list, preview, delete
- [x] Segments store `voice_sample_id` (Dia) and `magpie_voice` (Magpie)

### Milestone 9: Audio Post-Processing [DONE]
**Goal**: Improve exported audio quality with basic post-processing.

- [x] Configurable silence gap between segments (e.g. 0.5s, 1s, 1.5s)
- [x] Fade-in/fade-out per segment to avoid clicks at boundaries
- [x] Normalize audio levels across segments (peak or LUFS normalization)
- [x] Sample rate conversion so Dia (44.1kHz) and Magpie (22.05kHz) segments can be mixed in one export
- [x] Export as MP3 in addition to WAV (add `pydub` or `ffmpeg` dependency)

### Milestone 10: Generation Queue + Progress [DONE]
**Goal**: Better async generation with real-time progress updates.

- [x] WebSocket endpoint for real-time generation progress
- [x] UI updates live as each segment completes (no manual refresh)
- [x] Cancel in-progress generation
- [x] Retry failed segments with one click
- [x] Generation time estimates based on historical durations
- [x] Queue multiple generation requests instead of rejecting with 409

### Milestone 11: Article-to-Narration [DONE]
**Goal**: Paste a full article and have it automatically split into TTS-friendly segments with LLM cleanup.

- [x] `POST /api/projects/{id}/import-article` — accepts raw article text
- [x] LLM-powered text processing (via Nemotron or configurable endpoint):
  - Split article into sentence-level segments appropriate for TTS
  - Sanitize special characters, abbreviations, numbers (e.g. "42%" -> "forty-two percent")
  - Expand acronyms where helpful for spoken clarity
  - Remove or rewrite content that does not work well spoken (URLs, markdown, code blocks)
- [x] UI: "Import Article" option alongside "Import Script"
- [x] Preview the split/cleaned segments before committing
- [x] Configurable LLM endpoint via env var

### Milestone 12: Script Editor [DONE]
**Goal**: A proper inline script editor that makes it easy to iterate on narration text.

- [x] Multi-line script editing view (full script as editable rows)
- [x] Sync edits back to segments (diff-aware: only reset segments whose text changed)
- [x] Line-by-line preview: click play to hear existing audio
- [x] Sentence splitting helper: auto-split long lines at sentence boundaries
- [x] Character count, word count, estimated duration per line
- [x] Highlight lines that are too long (amber >200, red >300 chars)

### Milestone 13: Timeline Visualization [DONE]
**Goal**: A visual timeline showing the full narration with waveforms and timing.

- [x] Horizontal timeline bar showing all segments proportional to duration
- [x] Color-coded by status (pending/done/error)
- [x] Click a segment in the timeline to jump to it and play
- [x] Continuous playback: play all segments in order without gaps
- [x] Waveform display per segment (using Web Audio API)
- [x] Total duration marker and current playback position

### Milestone 14: Speech-to-Text Transcription + Word-Level Timeline
**Goal**: Transcribe generated audio segments using the speech-to-text service, store word-level timestamps, and visualize them in both the segment view and the timeline.

**Speech-to-Text Service**:
- Existing service at `services/speech-to-text/` running on port 8001
- `POST /transcribe?timestamps=true` with multipart WAV file upload
- Returns `{text: str, words: [{word: str, start: float, end: float}]}`
- Configurable via `STT_URL` env var (default `http://localhost:8001`)

**Database Changes**:
- [ ] Add `transcriptions` table:
  - `id` INTEGER PK
  - `segment_id` INTEGER FK → segments.id (unique, one transcription per segment)
  - `text` TEXT — full transcribed text
  - `words_json` TEXT — JSON array of `{word, start, end}` objects
  - `created_at` DATETIME
- [ ] Migration: create table if not exists on init_db

**Backend Endpoints**:
- [ ] `POST /api/segments/{id}/transcribe` — Send segment audio to STT service, store result
  - Reads the segment's active audio (selected variant or primary audio_path)
  - POSTs the WAV file to STT service with `timestamps=true`
  - Stores `{text, words_json}` in transcriptions table
  - Returns the transcription with parsed words array
- [ ] `GET /api/segments/{id}/transcription` — Get stored transcription for a segment
  - Returns `{text, words: [{word, start, end}]}` or 404
- [ ] `DELETE /api/segments/{id}/transcription` — Remove transcription (e.g. after re-generation)
- [ ] `POST /api/projects/{id}/transcribe-all` — Transcribe all segments with audio that don't have transcriptions yet
  - Sequential processing with progress tracking (reuse generation status pattern)
- [ ] Auto-delete transcription when a segment is regenerated or its selected variant changes (stale audio)

**Segment View — Collapsible Transcription Panel**:
- [ ] "Transcribe" button on each segment with audio (next to play/regenerate controls)
- [ ] Collapsible panel below segment showing:
  - Full transcribed text
  - Word-level breakdown: each word with start/end timestamps displayed as pills/chips
  - Click a word to seek audio to that timestamp and play
  - Words highlighted in sequence during audio playback (karaoke-style)
- [ ] Visual indicator on segment card when transcription exists (small icon/badge)
- [ ] "Re-transcribe" option if audio has changed since last transcription
- [ ] Loading state while transcription is in progress

**Timeline View — Word Overlay**:
- [ ] Word track above the waveform timeline showing transcribed words positioned by timestamp
  - Each word placed at its `start` offset relative to the segment's position in the overall timeline
  - Words sized proportionally to their duration (`end - start`)
  - Overflow handling for segments with many words (truncate or smaller font)
- [ ] During playback: current word highlighted (bold/colored) as the playback cursor passes through it
  - Uses `timeupdate` events and binary search on word timestamps for efficiency
- [ ] Words only shown for segments that have been transcribed (others show empty track)
- [ ] "Transcribe All" button in timeline toolbar to batch-transcribe all segments with audio
- [ ] Minimap also reflects transcribed vs. non-transcribed segments (subtle indicator)

**Configuration**:
- `STT_URL` env var for speech-to-text service URL (default: `http://localhost:8001`)

---

## Configuration

All via environment variables with sensible defaults:

```
DIA_URL=http://192.168.5.253:7860
MAGPIE_URL=http://192.168.6.3:9000
REFERENCE_AUDIO=sample/Alice.wav
REFERENCE_TEXT=sample/text.txt
OUTPUT_DIR=output
DATABASE_URL=narration.db
```

## Running

```bash
# Install dependencies
uv sync

# Start the server
uv run uvicorn app.main:app --reload --port 8877

# Or batch generate from CLI
uv run python batch.py script.txt --service dia
```

## Notes

- Dia requires the `[S1]` tag in the reference text and generates with the segment text + `[S2]` suffix (prevents audio cutoff)
- Each segment should be roughly 1-2 sentences — the TTS services struggle with longer text
- The existing `script.txt` has 27 non-empty lines, which at ~7-8 seconds each gives roughly 3:30 of audio
- The original `generate.py` and `sample.py` are preserved as reference but won't be used by the app
