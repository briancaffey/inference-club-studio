<script setup lang="ts">
import type {
  SegmentSortMode,
  SegmentStatusFilter,
} from '~/composables/narration-next/narrationWorkspaceUtils'

const props = defineProps<{
  segmentCount: number
  doneCount: number
  pendingCount: number
  queuedCount: number
  generatingCount: number
  errorCount: number
  totalDuration: string
  generating: boolean
  cancelling: boolean
  transcribingAll: boolean
  transcribeAllLabel: string
  showImport: boolean
  showAdd: boolean
  showTimeline: boolean
  showExport: boolean
  hasAudio: boolean
  hasSegments: boolean
  segmentStatusFilter: SegmentStatusFilter
  segmentSortMode: SegmentSortMode
  showFinalSegments: boolean
  showNeedsReviewOnly: boolean
  filteredCount: number
}>()

const emit = defineEmits<{
  (event: 'toggle-import'): void
  (event: 'toggle-add'): void
  (event: 'toggle-timeline'): void
  (event: 'toggle-export'): void
  (event: 'generate-all'): void
  (event: 'retry-failed'): void
  (event: 'transcribe-all'): void
  (event: 'cancel-generation'): void
  (event: 'clear-all'): void
  (event: 'update:segmentStatusFilter', value: SegmentStatusFilter): void
  (event: 'update:segmentSortMode', value: SegmentSortMode): void
  (event: 'update:showFinalSegments', value: boolean): void
  (event: 'update:showNeedsReviewOnly', value: boolean): void
}>()

function onStatusFilterChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('update:segmentStatusFilter', target.value as SegmentStatusFilter)
}

function onSortModeChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('update:segmentSortMode', target.value as SegmentSortMode)
}

function onShowFinalChange(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:showFinalSegments', target.checked)
}

function onShowNeedsReviewChange(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:showNeedsReviewOnly', target.checked)
}
</script>

<template>
  <section class="space-y-3 rounded-2xl border border-border/70 bg-card/60 p-4">
    <div class="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span class="rounded-full bg-muted px-2 py-1">{{ segmentCount }} segments</span>
      <span class="rounded-full bg-emerald-100 px-2 py-1 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">{{ doneCount }} done</span>
      <span class="rounded-full bg-amber-100 px-2 py-1 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">{{ pendingCount }} pending</span>
      <span v-if="queuedCount" class="rounded-full bg-sky-100 px-2 py-1 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">{{ queuedCount }} queued</span>
      <span v-if="generatingCount" class="rounded-full bg-blue-100 px-2 py-1 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">{{ generatingCount }} generating</span>
      <span v-if="errorCount" class="rounded-full bg-red-100 px-2 py-1 text-red-700 dark:bg-red-900/40 dark:text-red-300">{{ errorCount }} failed</span>
      <span class="ml-auto text-sm font-semibold text-foreground">{{ totalDuration }}</span>
    </div>

    <div class="flex flex-wrap gap-2">
      <button data-testid="toggle-import" class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted" @click="emit('toggle-import')">
        {{ showImport ? 'Hide Import' : 'Import' }}
      </button>
      <button data-testid="toggle-add" class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted" @click="emit('toggle-add')">
        {{ showAdd ? 'Hide Add' : 'Add Segment' }}
      </button>
      <button data-testid="toggle-timeline" class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50" :disabled="!hasSegments" @click="emit('toggle-timeline')">
        {{ showTimeline ? 'Hide Timeline' : 'Timeline' }}
      </button>
      <button data-testid="toggle-export" class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50" :disabled="!hasAudio" @click="emit('toggle-export')">
        {{ showExport ? 'Hide Export' : 'Export' }}
      </button>

      <span class="mx-1 hidden h-6 w-px bg-border sm:block" />

      <button data-testid="generate-all" class="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50" :disabled="!hasSegments || generating" @click="emit('generate-all')">
        Generate All
      </button>
      <button v-if="generating" data-testid="cancel-generation" class="rounded-md border border-red-300 px-3 py-1.5 text-xs text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300" :disabled="cancelling" @click="emit('cancel-generation')">
        {{ cancelling ? 'Cancelling...' : 'Cancel' }}
      </button>
      <button data-testid="retry-failed" class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50" :disabled="!errorCount || generating" @click="emit('retry-failed')">
        Retry Failed
      </button>
      <button data-testid="transcribe-all" class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50" :disabled="!hasAudio || transcribingAll" @click="emit('transcribe-all')">
        {{ transcribeAllLabel }}
      </button>

      <button data-testid="clear-all" class="ml-auto rounded-md border border-red-300 px-3 py-1.5 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-300" :disabled="!hasSegments || generating" @click="emit('clear-all')">
        Clear All
      </button>
    </div>

    <div class="flex flex-wrap items-center gap-2 rounded-xl border bg-muted/20 p-2 text-xs">
      <label class="text-muted-foreground" for="segment-filter">Filter</label>
      <select id="segment-filter" :value="segmentStatusFilter" class="rounded border bg-background px-2 py-1" @change="onStatusFilterChange">
        <option value="all">All</option>
        <option value="pending">Pending</option>
        <option value="queued">Queued</option>
        <option value="generating">Generating</option>
        <option value="done">Done</option>
        <option value="error">Error</option>
      </select>

      <label class="text-muted-foreground" for="sort-mode">Sort</label>
      <select id="sort-mode" :value="segmentSortMode" class="rounded border bg-background px-2 py-1" @change="onSortModeChange">
        <option value="position">Segment Order</option>
        <option value="recent">Recently Generated</option>
      </select>

      <label class="ml-2 inline-flex items-center gap-1">
        <input :checked="showFinalSegments" type="checkbox" @change="onShowFinalChange">
        Show Final
      </label>

      <label class="inline-flex items-center gap-1">
        <input :checked="showNeedsReviewOnly" type="checkbox" @change="onShowNeedsReviewChange">
        Needs Review
      </label>

      <span class="ml-auto text-muted-foreground">{{ filteredCount }} shown</span>
    </div>
  </section>
</template>
