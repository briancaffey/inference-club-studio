<script setup lang="ts">
import { computed, ref } from 'vue'
import type {
  NarrationImageFrame,
  NarrationImageSeries,
} from '~/types'
import type {
  NarrationImageSequencesController,
} from '~/composables/narration-next/useNarrationImageSequences'

const props = defineProps<{
  segmentId: number
  series: NarrationImageSeries
  controller: NarrationImageSequencesController
}>()

const expanded = ref(
  props.series.status === 'queued'
  || props.series.status === 'generating'
  || !!props.series.error_message,
)
const newPrompt = ref('')
const sourceFrameId = ref<string | null>(null)
const isFork = ref(true)
const guidance = ref('')
const suggestions = ref<string[]>([])
const localError = ref<string | null>(null)

const frames = computed(() => (
  [...props.series.frames].sort((a, b) => a.step_order - b.step_order)
))

const frameById = computed(() => {
  const map: Record<string, NarrationImageFrame> = {}
  for (const frame of frames.value) {
    map[frame.id] = frame
  }
  return map
})

const completedFrames = computed(() => (
  frames.value.filter(frame => frame.status === 'completed')
))

const hasPendingFrames = computed(() => (
  frames.value.some(frame => frame.status === 'pending')
))

const createdLabel = computed(() => (
  new Date(props.series.created_at).toLocaleString()
))

const seriesBusy = computed(() => props.controller.isSeriesBusy(props.series.id))
const suggesting = computed(() => props.controller.isSeriesSuggesting(props.series.id))

function statusClass(status: string) {
  if (status === 'completed') {
    return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
  }
  if (status === 'generating') {
    return 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300'
  }
  if (status === 'queued') {
    return 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300'
  }
  if (status === 'error') {
    return 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
  }
  return 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300'
}

function frameStatusClass(status: string) {
  if (status === 'completed') {
    return 'text-emerald-700 dark:text-emerald-300'
  }
  if (status === 'generating') {
    return 'text-blue-700 dark:text-blue-300'
  }
  if (status === 'error') {
    return 'text-red-700 dark:text-red-300'
  }
  return 'text-amber-700 dark:text-amber-300'
}

function onSourceFrameChange(event: Event) {
  const target = event.target as HTMLSelectElement
  sourceFrameId.value = target.value || null
  if (!sourceFrameId.value) {
    isFork.value = false
  }
}

function frameImageUrl(frame: NarrationImageFrame) {
  return props.controller.mediaUrl(frame.output_image_path)
}

function frameStepLabel(frame: NarrationImageFrame) {
  return frame.step_key || `step_${frame.step_order}`
}

function parentStepLabel(frame: NarrationImageFrame) {
  if (!frame.parent_frame_id) return null
  const parent = frameById.value[frame.parent_frame_id]
  if (!parent) return 'parent missing'
  return parent.step_key || `step_${parent.step_order}`
}

async function onQueueSeries() {
  localError.value = null
  try {
    await props.controller.queueSeries(props.segmentId, props.series.id)
  } catch (err: any) {
    localError.value = err?.data?.detail || err?.message || 'Failed to queue series'
  }
}

async function onDeleteSeries() {
  if (!confirm('Delete this image sequence?')) return

  localError.value = null
  try {
    await props.controller.deleteSeries(props.segmentId, props.series.id)
  } catch (err: any) {
    localError.value = err?.data?.detail || err?.message || 'Failed to delete series'
  }
}

async function onAddFrame() {
  const prompt = newPrompt.value.trim()
  if (!prompt) return

  localError.value = null
  try {
    await props.controller.addFrame(props.segmentId, props.series.id, {
      prompt,
      parentFrameId: sourceFrameId.value,
      isFork: !!sourceFrameId.value && isFork.value,
      mode: sourceFrameId.value ? 'image_to_image' : 'text_to_image',
    })
    newPrompt.value = ''
    guidance.value = ''
    suggestions.value = []
  } catch (err: any) {
    localError.value = err?.data?.detail || err?.message || 'Failed to add frame'
  }
}

async function onSuggestPrompts() {
  localError.value = null

  try {
    suggestions.value = await props.controller.suggestPrompts(props.series.id, {
      sourceFrameId: sourceFrameId.value,
      guidance: guidance.value,
      count: 4,
    })
    if (!newPrompt.value && suggestions.value.length) {
      newPrompt.value = suggestions.value[0]
    }
  } catch (err: any) {
    localError.value = err?.data?.detail || err?.message || 'Failed to suggest prompts'
  }
}

async function onRegenerateFrame(frameId: string, includeDescendants: boolean) {
  localError.value = null
  try {
    await props.controller.regenerateFrame(
      props.segmentId,
      props.series.id,
      frameId,
      {
        includeDescendants,
        autoGenerate: true,
      },
    )
  } catch (err: any) {
    localError.value = err?.data?.detail || err?.message || 'Failed to regenerate frame'
  }
}
</script>

<template>
  <article class="space-y-3 rounded-xl border border-border/70 bg-card/70 p-3">
    <header class="flex flex-wrap items-start justify-between gap-2">
      <div class="space-y-1">
        <div class="flex flex-wrap items-center gap-2">
          <h5 class="text-sm font-semibold">
            {{ series.name || `Series ${series.id.slice(0, 8)}` }}
          </h5>
          <span class="rounded-full px-2 py-0.5 text-[11px] font-medium" :class="statusClass(series.status)">
            {{ series.status }}
          </span>
          <span class="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
            {{ series.frames.length }} frame{{ series.frames.length === 1 ? '' : 's' }}
          </span>
        </div>
        <p class="text-[11px] text-muted-foreground">Created {{ createdLabel }}</p>
      </div>

      <div class="flex flex-wrap gap-1">
        <button
          class="rounded-md border px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
          :disabled="seriesBusy"
          @click="expanded = !expanded"
        >
          {{ expanded ? 'Collapse' : 'Expand' }}
        </button>
        <button
          v-if="hasPendingFrames && series.status !== 'queued' && series.status !== 'generating'"
          class="rounded-md border px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
          :disabled="seriesBusy"
          @click="onQueueSeries"
        >
          Generate Pending
        </button>
        <button
          class="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-300"
          :disabled="seriesBusy"
          @click="onDeleteSeries"
        >
          Delete
        </button>
      </div>
    </header>

    <p v-if="series.error_message" class="text-xs text-red-600 dark:text-red-300">
      {{ series.error_message }}
    </p>
    <p v-if="localError" class="text-xs text-red-600 dark:text-red-300">
      {{ localError }}
    </p>

    <div v-if="expanded" class="space-y-3">
      <div
        v-if="!frames.length"
        class="rounded-lg border border-dashed p-3 text-xs text-muted-foreground"
      >
        No frames yet. Add an initial prompt below.
      </div>

      <div v-else class="space-y-2">
        <article
          v-for="frame in frames"
          :key="frame.id"
          class="grid gap-2 rounded-lg border border-border/60 bg-background/60 p-2 md:grid-cols-[90px_1fr_auto]"
        >
          <div class="h-20 overflow-hidden rounded border bg-muted/40">
            <img
              v-if="frameImageUrl(frame)"
              :src="frameImageUrl(frame) || ''"
              :alt="`Frame ${frame.step_order}`"
              class="h-full w-full object-cover"
            >
            <div v-else class="flex h-full items-center justify-center text-[10px] text-muted-foreground">
              no image
            </div>
          </div>

          <div class="space-y-1">
            <div class="flex flex-wrap items-center gap-2 text-xs">
              <span class="rounded-full bg-muted px-2 py-0.5 font-medium">
                {{ frameStepLabel(frame) }}
              </span>
              <span class="rounded-full border px-2 py-0.5 text-[11px]">
                {{ frame.mode }}
              </span>
              <span class="text-[11px] font-medium" :class="frameStatusClass(frame.status)">
                {{ frame.status }}
              </span>
              <span v-if="frame.is_fork" class="rounded-full bg-cyan-100 px-2 py-0.5 text-[11px] text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300">
                fork
              </span>
              <span v-if="parentStepLabel(frame)" class="text-[11px] text-muted-foreground">
                parent: {{ parentStepLabel(frame) }}
              </span>
            </div>
            <p class="line-clamp-3 text-xs leading-relaxed">
              {{ frame.prompt }}
            </p>
            <p v-if="frame.error_message" class="text-xs text-red-600 dark:text-red-300">
              {{ frame.error_message }}
            </p>
          </div>

          <div class="flex flex-wrap gap-1 md:flex-col md:justify-start">
            <button
              class="rounded border px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
              :disabled="seriesBusy"
              @click="onRegenerateFrame(frame.id, false)"
            >
              Regen
            </button>
            <button
              class="rounded border px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
              :disabled="seriesBusy"
              @click="onRegenerateFrame(frame.id, true)"
            >
              Regen Branch
            </button>
          </div>
        </article>
      </div>

      <section class="space-y-2 rounded-lg border border-dashed p-3">
        <h6 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Add New Frame
        </h6>

        <div class="grid gap-2 md:grid-cols-2">
          <label class="space-y-1 text-xs text-muted-foreground">
            Source Frame
            <select
              class="w-full rounded border bg-background px-2 py-1 text-xs text-foreground"
              :value="sourceFrameId || ''"
              :disabled="seriesBusy"
              @change="onSourceFrameChange"
            >
              <option value="">None (new root)</option>
              <option
                v-for="frame in completedFrames"
                :key="frame.id"
                :value="frame.id"
              >
                {{ frameStepLabel(frame) }}
              </option>
            </select>
          </label>

          <label class="inline-flex items-end gap-2 text-xs">
            <input
              v-model="isFork"
              type="checkbox"
              :disabled="!sourceFrameId || seriesBusy"
            >
            Mark as fork
          </label>
        </div>

        <textarea
          v-model="newPrompt"
          rows="3"
          class="w-full rounded border bg-background px-2 py-1.5 text-xs"
          :disabled="seriesBusy"
          placeholder="Prompt for next frame..."
        />

        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="guidance"
            class="min-w-44 flex-1 rounded border bg-background px-2 py-1 text-xs"
            :disabled="seriesBusy"
            placeholder="Optional guidance for suggestions"
          >
          <button
            class="rounded border px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
            :disabled="seriesBusy || suggesting"
            @click="onSuggestPrompts"
          >
            {{ suggesting ? 'Suggesting...' : 'Suggest' }}
          </button>
          <button
            class="rounded bg-primary px-3 py-1 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50"
            :disabled="seriesBusy || !newPrompt.trim()"
            @click="onAddFrame"
          >
            {{ sourceFrameId ? 'Add Fork Frame' : 'Add Root Frame' }}
          </button>
        </div>

        <div v-if="suggestions.length" class="flex flex-wrap gap-1">
          <button
            v-for="(item, index) in suggestions"
            :key="`${series.id}-suggestion-${index}`"
            class="rounded-full border px-2 py-0.5 text-[11px] hover:bg-muted"
            @click="newPrompt = item"
          >
            {{ item }}
          </button>
        </div>
      </section>
    </div>
  </article>
</template>
