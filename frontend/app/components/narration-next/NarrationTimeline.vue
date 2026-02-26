<script setup lang="ts">
import { computed, toRef } from 'vue'
import type {
  NarrationSegment,
  NarrationTranscription,
} from '~/types'
import { useNarrationTimelineNext } from '~/composables/narration-next/useNarrationTimelineNext'

const props = defineProps<{
  segments: NarrationSegment[]
  transcriptions: Record<number, NarrationTranscription>
  playbackSpeed: number
  segmentAudioUrl: (segment: NarrationSegment) => string
}>()

const emit = defineEmits<{
  (event: 'update:playbackSpeed', value: number): void
}>()

const playbackSpeedModel = computed({
  get: () => props.playbackSpeed,
  set: value => emit('update:playbackSpeed', value),
})

const {
  timelineAudioPlayer,
  timelinePlayingIdx,
  timelineCurrentTime,
  timelineIsPlaying,
  timelineTotalSeconds,
  timelineOffsets,
  timelineWidths,
  timelineCursorPercent,
  timelineHasDoneSegments,
  toggleTimelinePlayPause,
  stopTimelinePlayback,
  timelineClickSegment,
  onTimelineAudioEnded,
  onTimelineTimeUpdate,
  seekToWord,
  getActiveWordIdx,
  formatDuration,
} = useNarrationTimelineNext({
  segments: toRef(props, 'segments'),
  transcriptions: props.transcriptions,
  playbackSpeed: playbackSpeedModel,
  segmentAudioUrl: props.segmentAudioUrl,
})

defineExpose({
  seekToWord,
})

function onSpeedChange(event: Event) {
  const target = event.target as HTMLInputElement
  const value = Number(target.value)
  if (Number.isNaN(value)) return
  playbackSpeedModel.value = value
}
</script>

<template>
  <section class="space-y-3 rounded-2xl border border-border/70 bg-card p-4 shadow-sm">
    <div class="flex flex-wrap items-center gap-2">
      <h3 class="text-sm font-semibold">Timeline</h3>
      <span class="text-xs text-muted-foreground tabular-nums">{{ formatDuration(timelineTotalSeconds) }}</span>

      <button
        data-testid="timeline-play-toggle"
        class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50"
        :disabled="!timelineHasDoneSegments"
        @click="toggleTimelinePlayPause"
      >
        {{ timelineIsPlaying ? 'Pause' : 'Play All' }}
      </button>

      <button
        v-if="timelinePlayingIdx >= 0"
        class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted"
        @click="stopTimelinePlayback"
      >
        Stop
      </button>

      <label class="ml-auto inline-flex items-center gap-2 text-xs text-muted-foreground">
        Speed
        <input
          :value="playbackSpeed"
          type="range"
          min="0.5"
          max="2.5"
          step="0.05"
          class="w-24"
          @input="onSpeedChange"
        >
        <span class="w-10 text-right tabular-nums">{{ playbackSpeed.toFixed(1) }}x</span>
      </label>
    </div>

    <p v-if="timelinePlayingIdx >= 0" class="text-xs text-muted-foreground tabular-nums">
      {{ formatDuration((timelineOffsets[timelinePlayingIdx] || 0) + timelineCurrentTime) }} / {{ formatDuration(timelineTotalSeconds) }}
      · Segment {{ timelinePlayingIdx + 1 }} of {{ segments.length }}
    </p>

    <div
      v-if="Object.keys(transcriptions).length"
      class="overflow-x-auto whitespace-nowrap rounded-md border bg-muted/30 px-3 py-1.5"
    >
      <template v-for="(segment, segmentIndex) in segments" :key="`word-${segment.id}`">
        <template v-if="transcriptions[segment.id]?.words?.length">
          <button
            v-for="(word, wordIndex) in transcriptions[segment.id].words"
            :key="`word-${segment.id}-${wordIndex}`"
            type="button"
            class="mr-1 inline-block rounded px-1 py-0.5 text-xs"
            :class="getActiveWordIdx(segment.id) === wordIndex
              ? 'bg-primary/20 font-semibold text-primary'
              : 'text-muted-foreground hover:bg-muted'"
            @click="seekToWord(segment.id, word.start)"
          >
            {{ word.word }}
          </button>
        </template>
        <span v-if="segmentIndex < segments.length - 1" class="mx-1 text-[10px] text-muted-foreground/50">|</span>
      </template>
    </div>

    <div class="relative h-16 overflow-hidden rounded-lg border bg-muted/30">
      <div class="relative flex h-full">
        <button
          v-for="(segment, index) in segments"
          :key="segment.id"
          type="button"
          class="relative h-full border-r border-white/20 text-left last:border-r-0 dark:border-black/20"
          :style="{ width: `${timelineWidths[index] || 0}%`, minWidth: '6px' }"
          :class="[
            segment.status === 'done'
              ? 'bg-emerald-200/70 dark:bg-emerald-900/50'
              : segment.status === 'error'
                ? 'bg-red-200/70 dark:bg-red-900/50'
                : segment.status === 'generating'
                  ? 'bg-amber-200/70 dark:bg-amber-900/50'
                  : 'bg-slate-200/80 dark:bg-slate-700/50',
            timelinePlayingIdx === index ? 'ring-2 ring-primary ring-inset' : '',
          ]"
          @click="timelineClickSegment(index)"
        >
          <span class="absolute bottom-0.5 left-1 text-[10px] font-semibold text-black/40 dark:text-white/40">{{ segment.position }}</span>
        </button>

        <div
          v-if="timelinePlayingIdx >= 0"
          class="pointer-events-none absolute inset-y-0"
          :style="{ left: `${timelineCursorPercent}%` }"
        >
          <div class="h-full w-0.5 bg-primary" />
        </div>
      </div>
    </div>

    <audio
      ref="timelineAudioPlayer"
      class="hidden"
      @ended="onTimelineAudioEnded"
      @timeupdate="onTimelineTimeUpdate"
    />
  </section>
</template>
