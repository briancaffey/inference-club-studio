<script setup lang="ts">
import { computed, nextTick, ref, toRef } from 'vue'
import { Mic2 } from 'lucide-vue-next'
import type { NarrationSegment } from '~/types'
import NarrationStatusBanner from '~/components/narration-next/NarrationStatusBanner.vue'
import NarrationToolbar from '~/components/narration-next/NarrationToolbar.vue'
import NarrationTimeline from '~/components/narration-next/NarrationTimeline.vue'
import NarrationSegmentCard from '~/components/narration-next/NarrationSegmentCard.vue'
import { useNarrationWorkspaceNext } from '~/composables/narration-next/useNarrationWorkspaceNext'
import { useNarrationTrimNext } from '~/composables/narration-next/useNarrationTrimNext'

const props = defineProps<{
  projectId: string
}>()

const workspace = useNarrationWorkspaceNext(toRef(props, 'projectId'))

const timelineRef = ref<{ seekToWord: (segmentId: number, startSeconds: number) => void } | null>(null)
const playbackSpeed = ref(1)
const confirmClear = ref(false)
const trim = useNarrationTrimNext({
  segments: workspace.segments,
  transcriptions: workspace.transcriptions,
  audioVersion: workspace.audioVersion,
  playbackSpeed,
  status: workspace.status,
  refreshWorkspace: workspace.refreshWorkspace,
  ensureTranscription: async segmentId => {
    await workspace.transcribeSegment(segmentId, { silent: true })
  },
})

const transcribeAllLabel = computed(() => {
  const progress = workspace.transcribeAllProgress.value
  if (!progress) return 'Transcribe All'
  return `Transcribing ${progress.done}/${progress.total}`
})

function clearAllWithConfirm() {
  if (!confirmClear.value) {
    confirmClear.value = true
    setTimeout(() => {
      confirmClear.value = false
    }, 2200)
    return
  }

  confirmClear.value = false
  void workspace.clearAllSegments()
}

function deleteSegmentWithConfirm(segmentId: number) {
  if (!confirm('Delete this segment?')) return
  void workspace.deleteSegment(segmentId)
}

function onSeekWord(segmentId: number, startSeconds: number) {
  workspace.showTimeline.value = true
  nextTick(() => {
    timelineRef.value?.seekToWord(segmentId, startSeconds)
  })
}

function toggleFinal(segment: NarrationSegment) {
  void workspace.toggleFinal(segment)
}

function clearNeedsReview(segment: NarrationSegment) {
  void workspace.clearNeedsReview(segment)
}

function markDone(segment: NarrationSegment) {
  void workspace.markSegmentDone(segment)
}

function onGenerate(segmentId: number) {
  void workspace.generateOne(segmentId)
}

function onRegenerate(segmentId: number) {
  void workspace.regenerate(segmentId)
}

function onTranscribe(segmentId: number) {
  void workspace.transcribeSegment(segmentId)
}

function onDeleteTranscription(segmentId: number) {
  void workspace.deleteTranscription(segmentId)
}

function onMove(segmentId: number, direction: -1 | 1) {
  void workspace.moveSegment(segmentId, direction)
}

function onUpdateService(segmentId: number, service: 'dia' | 'magpie') {
  void workspace.updateSegmentService(segmentId, service)
}

function onSaveEdit(segmentId: number) {
  void workspace.saveEdit(segmentId)
}

function onImportScript() {
  void workspace.importScript()
}

function onAddSegment() {
  void workspace.addSegment()
}

function onGenerateAll() {
  void workspace.generateAll()
}

function onRetryFailed() {
  void workspace.retryFailed()
}

function onTranscribeAll() {
  void workspace.transcribeAll()
}

function onCancelGeneration() {
  void workspace.cancelGeneration()
}

function onToggleTrim(segmentId: number) {
  void trim.toggleTrim(segmentId)
}

function onTrimPreview() {
  void trim.previewTrim()
}

function onTrimApply() {
  void trim.applyTrim()
}

function onTrimRegenerate(segmentId: number) {
  void trim.regenerateTrimWaveform(segmentId)
}

function onTrimRetry(segmentId: number) {
  void trim.loadTrimWaveform(segmentId)
}
</script>

<template>
  <div class="space-y-4">
    <section class="rounded-2xl border border-border/70 bg-gradient-to-br from-card via-card to-muted/40 p-4 shadow-sm">
      <div class="flex items-center gap-2">
        <Mic2 class="h-5 w-5 text-primary" />
        <h2 class="text-lg font-semibold tracking-tight">Narration Workspace Next</h2>
      </div>
      <p class="mt-1 text-sm text-muted-foreground">
        Modular narration workspace with focused timeline and segment controls.
      </p>
    </section>

    <NarrationStatusBanner
      :status="workspace.status.value"
      :error="workspace.error.value"
      :generating="workspace.generating.value"
      :gen-estimate="workspace.genEstimate.value"
      :gen-progress="workspace.genProgress.value"
    />

    <NarrationToolbar
      :segment-count="workspace.segments.value.length"
      :done-count="workspace.doneCount.value"
      :pending-count="workspace.pendingCount.value"
      :queued-count="workspace.queuedCount.value"
      :generating-count="workspace.generatingCount.value"
      :error-count="workspace.errorCount.value"
      :total-duration="workspace.totalDuration.value"
      :generating="workspace.generating.value"
      :cancelling="workspace.cancelling.value"
      :transcribing-all="!!workspace.transcribeAllProgress.value"
      :transcribe-all-label="transcribeAllLabel"
      :show-import="workspace.showImport.value"
      :show-add="workspace.showAdd.value"
      :show-timeline="workspace.showTimeline.value"
      :show-export="workspace.showExport.value"
      :has-audio="workspace.hasAudio.value"
      :has-segments="!!workspace.segments.value.length"
      :segment-status-filter="workspace.segmentStatusFilter.value"
      :segment-sort-mode="workspace.segmentSortMode.value"
      :show-final-segments="workspace.showFinalSegments.value"
      :show-needs-review-only="workspace.showNeedsReviewOnly.value"
      :filtered-count="workspace.filteredSegments.value.length"
      @toggle-import="workspace.showImport.value = !workspace.showImport.value"
      @toggle-add="workspace.showAdd.value = !workspace.showAdd.value"
      @toggle-timeline="workspace.showTimeline.value = !workspace.showTimeline.value"
      @toggle-export="workspace.showExport.value = !workspace.showExport.value"
      @generate-all="onGenerateAll"
      @retry-failed="onRetryFailed"
      @transcribe-all="onTranscribeAll"
      @cancel-generation="onCancelGeneration"
      @clear-all="clearAllWithConfirm"
      @update:segment-status-filter="workspace.segmentStatusFilter.value = $event"
      @update:segment-sort-mode="workspace.segmentSortMode.value = $event"
      @update:show-final-segments="workspace.showFinalSegments.value = $event"
      @update:show-needs-review-only="workspace.showNeedsReviewOnly.value = $event"
    />

    <p v-if="confirmClear" class="text-xs font-medium text-red-600 dark:text-red-300">Press “Clear All” again to confirm.</p>

    <section v-if="workspace.showImport.value" class="space-y-2 rounded-2xl border border-border/70 bg-card p-4">
      <div class="flex items-center justify-between gap-2">
        <h3 class="text-sm font-semibold">Import Script</h3>
        <select v-model="workspace.importService.value" class="rounded-md border bg-background px-2 py-1 text-xs">
          <option value="dia">Dia</option>
          <option value="magpie">Magpie</option>
        </select>
      </div>

      <textarea
        v-model="workspace.importText.value"
        data-testid="import-text"
        rows="6"
        class="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
        placeholder="Paste script here (one line per segment)"
      />

      <button
        data-testid="import-script"
        class="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50"
        :disabled="!workspace.importText.value.trim()"
        @click="onImportScript"
      >
        Import Script
      </button>
    </section>

    <section v-if="workspace.showAdd.value" class="space-y-2 rounded-2xl border border-border/70 bg-card p-4">
      <div class="flex items-center justify-between gap-2">
        <h3 class="text-sm font-semibold">Add Segment</h3>
        <select v-model="workspace.addService.value" class="rounded-md border bg-background px-2 py-1 text-xs">
          <option value="dia">Dia</option>
          <option value="magpie">Magpie</option>
        </select>
      </div>

      <textarea
        v-model="workspace.addText.value"
        rows="3"
        class="w-full rounded-md border bg-background px-2 py-1.5 text-sm"
        placeholder="Segment text"
      />

      <button
        data-testid="add-segment"
        class="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50"
        :disabled="!workspace.addText.value.trim()"
        @click="onAddSegment"
      >
        Add Segment
      </button>
    </section>

    <section v-if="workspace.showExport.value" class="space-y-3 rounded-2xl border border-border/70 bg-card p-4">
      <h3 class="text-sm font-semibold">Export</h3>

      <div class="grid gap-3 sm:grid-cols-4">
        <label class="space-y-1 text-xs text-muted-foreground">
          Format
          <select v-model="workspace.exportFormat.value" class="w-full rounded-md border bg-background px-2 py-1 text-sm text-foreground">
            <option value="wav">WAV</option>
            <option value="mp3">MP3</option>
          </select>
        </label>

        <label class="space-y-1 text-xs text-muted-foreground">
          Gap (ms)
          <input v-model.number="workspace.exportGapMs.value" type="number" min="0" max="5000" class="w-full rounded-md border bg-background px-2 py-1 text-sm text-foreground">
        </label>

        <label class="space-y-1 text-xs text-muted-foreground">
          Fade (ms)
          <input v-model.number="workspace.exportFadeMs.value" type="number" min="0" max="500" class="w-full rounded-md border bg-background px-2 py-1 text-sm text-foreground">
        </label>

        <label class="inline-flex items-end gap-2 text-sm">
          <input v-model="workspace.exportNormalize.value" type="checkbox">
          Normalize
        </label>
      </div>

      <div class="flex flex-wrap gap-2">
        <button class="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50" :disabled="!workspace.hasAudio.value" @click="workspace.exportAudio">
          Download Combined
        </button>
        <button class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50" :disabled="!workspace.hasAudio.value" @click="workspace.exportAudioZip">
          Download Zip
        </button>
      </div>
    </section>

    <NarrationTimeline
      v-if="workspace.showTimeline.value && workspace.segments.value.length"
      ref="timelineRef"
      v-model:playback-speed="playbackSpeed"
      :segments="workspace.segments.value"
      :transcriptions="workspace.transcriptions"
      :segment-audio-url="workspace.segmentPreferredAudioUrl"
    />

    <div v-if="workspace.loading.value && !workspace.segments.value.length" class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
      Loading narration segments...
    </div>

    <div v-else-if="!workspace.segments.value.length" class="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
      No narration segments yet. Import a script or add one manually.
    </div>

    <div v-else class="space-y-3">
      <div
        v-if="!workspace.filteredSegments.value.length"
        class="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground"
      >
        No segments match the current filters.
      </div>

      <NarrationSegmentCard
        v-for="segment in workspace.filteredSegments.value"
        :key="segment.id"
        :segment="segment"
        :display-status="workspace.resolveSegmentDisplayStatus(segment, workspace.queuedSegmentIds)"
        :editing="workspace.editingId.value === segment.id"
        :edit-text="workspace.editText.value"
        :regen-text="workspace.regenText[segment.id] || ''"
        :transcribing="!!workspace.transcribing[segment.id]"
        :transcription="workspace.transcriptions[segment.id] || null"
        :expanded-transcript="workspace.expandedTranscript.value === segment.id"
        :generating="workspace.generating.value"
        :audio-url="workspace.segmentAudioUrl(segment.id)"
        :cleaned-audio-url="segment.studio_voice_audio_path ? workspace.segmentCleanedAudioUrl(segment.id) : null"
        :active-word-idx="-1"
        :can-trim="trim.segmentHasTrimmableAudio(segment)"
        :trim-open="trim.expandedTrimSegmentId.value === segment.id"
        :trim-range-label="trim.trimRangeLabel.value"
        :trim-selection-armed="trim.trimSelectionArmed.value"
        :trim-waveform-loading="trim.trimWaveformLoading.value && trim.expandedTrimSegmentId.value === segment.id"
        :trim-waveform-error="trim.trimWaveformError.value"
        :has-trim-selection="trim.hasTrimSelection.value"
        :trim-applying="trim.trimApplying.value"
        :can-preview-trim="!!trim.trimDecodedBuffer.value"
        :trim-waveform-ready="!!trim.trimWaveformData.value && trim.trimSegmentId.value === segment.id"
        :trim-selection-start="trim.trimSelectionStart.value"
        :trim-selection-end="trim.trimSelectionEnd.value"
        :trim-selection-duration="trim.trimSelectionDuration.value"
        :trim-audio-duration="trim.trimAudioDuration.value"
        :trim-suggested="trim.segmentNeedsTrim(segment)"
        @start-edit="workspace.startEdit"
        @update:edit-text="workspace.editText.value = $event"
        @save-edit="onSaveEdit"
        @cancel-edit="workspace.cancelEdit"
        @delete="deleteSegmentWithConfirm"
        @move="onMove"
        @update-service="onUpdateService"
        @generate="onGenerate"
        @regenerate="onRegenerate"
        @update:regen-text="workspace.regenText[segment.id] = $event"
        @transcribe="onTranscribe"
        @toggle-transcript="workspace.toggleTranscript"
        @delete-transcription="onDeleteTranscription"
        @seek-word="onSeekWord"
        @toggle-final="toggleFinal"
        @clear-needs-review="clearNeedsReview"
        @mark-done="markDone"
        @toggle-trim="onToggleTrim"
        @trim-begin-selection="trim.beginTrimSelection"
        @trim-preview="onTrimPreview"
        @trim-apply="onTrimApply"
        @trim-clear-selection="trim.clearTrimSelection"
        @trim-cancel="trim.cancelTrimDeadspace"
        @trim-regenerate-waveform="onTrimRegenerate"
        @trim-retry-waveform="onTrimRetry"
        @trim-waveform-pointerdown="trim.onTrimWaveformPointerDown"
      />
    </div>
  </div>
</template>
