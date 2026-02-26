<script setup lang="ts">
import type { NarrationTranscription } from '~/types'

const props = defineProps<{
  segmentId: number
  transcription: NarrationTranscription | null
  trimRangeLabel: string
  trimSelectionArmed: boolean
  trimWaveformLoading: boolean
  trimWaveformError: string
  hasTrimSelection: boolean
  trimApplying: boolean
  canPreviewTrim: boolean
  trimWaveformReady: boolean
  trimSelectionStart: number
  trimSelectionEnd: number
  trimSelectionDuration: number
  trimAudioDuration: number
}>()

const emit = defineEmits<{
  (event: 'begin-selection'): void
  (event: 'preview'): void
  (event: 'apply'): void
  (event: 'clear-selection'): void
  (event: 'cancel'): void
  (event: 'regenerate-waveform'): void
  (event: 'retry-waveform'): void
  (event: 'waveform-pointerdown', payload: PointerEvent): void
}>()

function onPointerDown(event: PointerEvent) {
  emit('waveform-pointerdown', event)
}
</script>

<template>
  <section class="space-y-3 rounded-xl border border-cyan-200 bg-cyan-50/40 p-3 dark:border-cyan-900/50 dark:bg-cyan-900/10">
    <div class="flex flex-wrap items-center gap-2">
      <p class="text-sm font-medium text-cyan-700 dark:text-cyan-300">Trim Deadspace</p>
      <span class="text-xs tabular-nums text-muted-foreground">{{ trimRangeLabel }}</span>

      <button
        class="rounded-md border px-2.5 py-1 text-xs hover:bg-background disabled:opacity-50"
        :class="trimSelectionArmed ? 'border-rose-500 text-rose-700 dark:text-rose-300' : ''"
        :disabled="trimWaveformLoading || !trimWaveformReady || trimApplying"
        @click="emit('begin-selection')"
      >
        {{ trimSelectionArmed ? 'Drag on Waveform' : 'Select Deadspace' }}
      </button>

      <button
        class="rounded-md border px-2.5 py-1 text-xs hover:bg-background disabled:opacity-50"
        :disabled="trimWaveformLoading || !trimWaveformReady || !hasTrimSelection || !canPreviewTrim"
        @click="emit('preview')"
      >
        Preview New Audio
      </button>

      <button
        class="rounded-md bg-primary px-2.5 py-1 text-xs text-primary-foreground disabled:opacity-50"
        :disabled="trimApplying || trimWaveformLoading || !trimWaveformReady || !hasTrimSelection"
        @click="emit('apply')"
      >
        {{ trimApplying ? 'Saving...' : 'Save' }}
      </button>

      <button
        class="rounded-md border px-2.5 py-1 text-xs hover:bg-background disabled:opacity-50"
        :disabled="trimWaveformLoading || !hasTrimSelection"
        @click="emit('clear-selection')"
      >
        Clear
      </button>

      <button
        class="rounded-md border px-2.5 py-1 text-xs hover:bg-background disabled:opacity-50"
        :disabled="trimApplying"
        @click="emit('cancel')"
      >
        Close
      </button>

      <button
        class="rounded-md border px-2.5 py-1 text-xs hover:bg-background disabled:opacity-50"
        :disabled="trimWaveformLoading || trimApplying"
        @click="emit('regenerate-waveform')"
      >
        Regenerate Waveform
      </button>

      <button
        v-if="trimWaveformError"
        class="rounded-md border px-2.5 py-1 text-xs hover:bg-background disabled:opacity-50"
        :disabled="trimWaveformLoading"
        @click="emit('retry-waveform')"
      >
        Retry Waveform
      </button>
    </div>

    <p v-if="trimWaveformLoading" class="text-xs text-muted-foreground">Loading waveform...</p>
    <p v-else-if="trimWaveformError" class="text-xs text-amber-700 dark:text-amber-300">{{ trimWaveformError }}</p>
    <p v-else-if="trimWaveformReady && !canPreviewTrim" class="text-xs text-muted-foreground">
      Waveform loaded in server mode. Preview is unavailable, but you can still save trims.
    </p>
    <p v-else class="text-xs text-muted-foreground">
      {{ trimSelectionArmed
        ? 'Click and drag on the waveform to highlight deadspace to remove.'
        : 'Click Select Deadspace, drag to highlight the section to cut, then preview or save.' }}
    </p>

    <div class="relative h-32 select-none">
      <canvas :id="`trim-waveform-${segmentId}`" class="h-full w-full rounded-md border bg-muted/50" />

      <div
        v-if="trimWaveformReady"
        class="absolute inset-0 rounded-md touch-none"
        :class="trimSelectionArmed ? 'cursor-crosshair' : 'cursor-default'"
        @pointerdown="onPointerDown"
      />

      <div
        v-if="hasTrimSelection"
        class="pointer-events-none absolute bottom-0 top-0 rounded-md border border-rose-500/70 bg-rose-500/20"
        :style="{
          left: `${(trimSelectionStart / trimAudioDuration) * 100}%`,
          width: `${(trimSelectionDuration / trimAudioDuration) * 100}%`,
        }"
      />
    </div>

    <div v-if="transcription?.words?.length" class="flex flex-wrap gap-1">
      <span
        v-for="(word, index) in transcription.words"
        :key="`trim-word-${segmentId}-${index}`"
        class="rounded px-1.5 py-0.5 text-[11px]"
        :class="hasTrimSelection && word.start * 1000 >= trimSelectionStart && word.end * 1000 <= trimSelectionEnd
          ? 'bg-rose-100 text-rose-700 line-through dark:bg-rose-900/40 dark:text-rose-300'
          : 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300'"
      >
        {{ word.word }}
      </span>
    </div>
  </section>
</template>
