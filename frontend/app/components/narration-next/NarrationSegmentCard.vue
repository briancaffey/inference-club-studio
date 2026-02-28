<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
  type CarouselApi,
} from '~/components/ui/carousel'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '~/components/ui/dialog'
import type {
  NarrationSegment,
  NarrationService,
  NarrationTranscription,
} from '~/types'
import NarrationTrimPanel from '~/components/narration-next/NarrationTrimPanel.vue'

const props = defineProps<{
  segment: NarrationSegment
  displayStatus: string
  editing: boolean
  editText: string
  regenText: string
  transcribing: boolean
  transcription: NarrationTranscription | null
  expandedTranscript: boolean
  generating: boolean
  audioUrl: string
  cleanedAudioUrl: string | null
  activeWordIdx: number
  canTrim: boolean
  trimOpen: boolean
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
  trimSuggested: boolean
  latestImagePreviewFrames: Array<{
    id: string
    step_order: number
    step_key: string | null
    prompt: string
    src: string
  }>
  imagePanelOpen: boolean
}>()

const emit = defineEmits<{
  (event: 'start-edit', segment: NarrationSegment): void
  (event: 'update:editText', value: string): void
  (event: 'save-edit', segmentId: number): void
  (event: 'cancel-edit'): void
  (event: 'delete', segmentId: number): void
  (event: 'move', segmentId: number, direction: -1 | 1): void
  (event: 'update-service', segmentId: number, service: NarrationService): void
  (event: 'generate', segmentId: number): void
  (event: 'regenerate', segmentId: number): void
  (event: 'update:regenText', value: string): void
  (event: 'transcribe', segmentId: number): void
  (event: 'toggle-transcript', segmentId: number): void
  (event: 'delete-transcription', segmentId: number): void
  (event: 'seek-word', segmentId: number, startSeconds: number): void
  (event: 'toggle-final', segment: NarrationSegment): void
  (event: 'clear-needs-review', segment: NarrationSegment): void
  (event: 'mark-done', segment: NarrationSegment): void
  (event: 'toggle-trim', segmentId: number): void
  (event: 'trim-begin-selection'): void
  (event: 'trim-preview'): void
  (event: 'trim-apply'): void
  (event: 'trim-clear-selection'): void
  (event: 'trim-cancel'): void
  (event: 'trim-regenerate-waveform', segmentId: number): void
  (event: 'trim-retry-waveform', segmentId: number): void
  (event: 'trim-waveform-pointerdown', payload: PointerEvent, segmentId: number): void
  (event: 'toggle-image-panel', segmentId: number): void
}>()

const actionMenuValue = ref('')
const lightboxOpen = ref(false)
const lightboxStartIndex = ref(0)
const lightboxApi = ref<CarouselApi | null>(null)

function onEditInput(event: Event) {
  const target = event.target as HTMLTextAreaElement
  emit('update:editText', target.value)
}

function onRegenInput(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:regenText', target.value)
}

function onServiceChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('update-service', props.segment.id, target.value as NarrationService)
}

function onActionMenuChange(event: Event) {
  const target = event.target as HTMLSelectElement
  actionMenuValue.value = target.value

  if (target.value === 'trim') {
    emit('toggle-trim', props.segment.id)
  }

  actionMenuValue.value = ''
}

function statusClass(status: string) {
  if (status === 'done') return 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-300'
  if (status === 'generating') return 'bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-300'
  if (status === 'queued') return 'bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-300'
  if (status === 'error') return 'bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-300'
  return 'bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300'
}

function studioVoiceStatusLabel(status: string) {
  if (status === 'cleaned') return 'Cleaned'
  if (status === 'unavailable') return 'Unavailable'
  if (status === 'error') return 'Error'
  return 'Not cleaned'
}

function previewStepLabel(frame: { step_key: string | null, step_order: number }) {
  return frame.step_key || `step_${frame.step_order}`
}

function syncLightboxPosition() {
  nextTick(() => {
    if (!lightboxApi.value) return
    lightboxApi.value.scrollTo(lightboxStartIndex.value, true)
  })
}

function openLightboxAt(index: number) {
  lightboxStartIndex.value = index
  lightboxOpen.value = true
  syncLightboxPosition()
}

function onLightboxInit(api: CarouselApi) {
  lightboxApi.value = api
  syncLightboxPosition()
}

watch(lightboxOpen, open => {
  if (open) {
    syncLightboxPosition()
  }
})

watch(
  () => props.latestImagePreviewFrames.length,
  length => {
    if (!length) {
      lightboxOpen.value = false
      lightboxStartIndex.value = 0
      return
    }
    if (lightboxStartIndex.value >= length) {
      lightboxStartIndex.value = 0
    }
  },
)
</script>

<template>
  <article class="space-y-3 rounded-2xl border border-border/70 bg-card p-4 shadow-sm">
    <header class="flex flex-wrap items-start justify-between gap-3">
      <div class="space-y-1">
        <div class="flex flex-wrap items-center gap-2 text-xs">
          <span class="rounded-full border px-2 py-0.5">#{{ segment.position }}</span>
          <span class="rounded-full px-2 py-0.5 font-medium" :class="statusClass(displayStatus)">
            {{ displayStatus }}
          </span>
          <span v-if="segment.is_final" class="rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
            Final
          </span>
          <span v-if="segment.needs_review" class="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
            Needs Review
          </span>
          <span v-if="segment.audio_path" class="rounded-full bg-muted px-2 py-0.5 text-muted-foreground">
            Studio Voice: {{ studioVoiceStatusLabel(segment.studio_voice_status) }}
          </span>
          <span v-if="trimSuggested" class="rounded-full bg-cyan-100 px-2 py-0.5 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300">
            Trim suggested
          </span>
        </div>

        <p v-if="segment.error_message" class="text-xs text-red-600 dark:text-red-300">{{ segment.error_message }}</p>
        <p v-if="segment.studio_voice_error_message" class="text-xs text-amber-700 dark:text-amber-300">{{ segment.studio_voice_error_message }}</p>
      </div>

      <div class="flex flex-wrap gap-1">
        <select
          class="rounded border bg-background px-2 py-1 text-xs"
          :value="segment.service"
          @change="onServiceChange"
        >
          <option value="dia">Dia</option>
          <option value="magpie">Magpie</option>
        </select>
        <button class="rounded border px-2 py-1 text-xs hover:bg-muted" @click="emit('move', segment.id, -1)">↑</button>
        <button class="rounded border px-2 py-1 text-xs hover:bg-muted" @click="emit('move', segment.id, 1)">↓</button>
      </div>
    </header>

    <div v-if="editing" class="space-y-2">
      <textarea data-testid="edit-text" class="w-full rounded-md border bg-background px-2 py-1.5 text-sm" rows="3" :value="editText" @input="onEditInput" />
      <div class="flex flex-wrap gap-2">
        <button data-testid="save-edit" class="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground" @click="emit('save-edit', segment.id)">Save</button>
        <button class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted" @click="emit('cancel-edit')">Cancel</button>
      </div>
    </div>

    <div v-else>
      <p class="text-sm leading-relaxed">{{ segment.text }}</p>
      <p v-if="segment.original_text" class="mt-1 text-xs text-muted-foreground">Original: {{ segment.original_text }}</p>
    </div>

    <div class="flex flex-wrap gap-2">
      <button data-testid="start-edit" class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted" @click="emit('start-edit', segment)">Edit</button>
      <button class="rounded-md border border-red-300 px-3 py-1.5 text-xs text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300" @click="emit('delete', segment.id)">Delete</button>
      <button data-testid="generate" class="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-50" :disabled="generating" @click="emit('generate', segment.id)">Generate</button>
      <button class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50" :disabled="generating" @click="emit('regenerate', segment.id)">Regenerate</button>
      <button
        data-testid="toggle-image-panel"
        class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted"
        @click="emit('toggle-image-panel', segment.id)"
      >
        {{ imagePanelOpen ? 'Hide Images' : 'Images' }}
      </button>

      <button class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted" @click="emit('toggle-final', segment)">
        {{ segment.is_final ? 'Unmark Final' : 'Mark Final' }}
      </button>
      <button class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50" :disabled="!segment.needs_review" @click="emit('clear-needs-review', segment)">
        Clear Review
      </button>
      <button v-if="segment.status === 'error'" class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted" :disabled="!segment.audio_path" @click="emit('mark-done', segment)">
        Mark Done
      </button>

      <button
        class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted disabled:opacity-50"
        :disabled="!segment.audio_path || transcribing"
        @click="emit('transcribe', segment.id)"
      >
        {{ transcribing ? 'Transcribing...' : 'Transcribe' }}
      </button>

      <button
        v-if="transcription"
        class="rounded-md border px-3 py-1.5 text-xs hover:bg-muted"
        @click="emit('toggle-transcript', segment.id)"
      >
        {{ expandedTranscript ? 'Hide Transcript' : 'Transcript' }}
      </button>

      <select
        v-model="actionMenuValue"
        data-testid="segment-action-menu"
        class="rounded-md border bg-background px-2 py-1.5 text-xs"
        @change="onActionMenuChange"
      >
        <option value="">More</option>
        <option value="trim" :disabled="!canTrim">
          {{ trimOpen ? 'Hide Trim Deadspace' : 'Trim Deadspace' }}
        </option>
      </select>
    </div>

    <input
      class="w-full rounded-md border bg-background px-2 py-1.5 text-xs"
      placeholder="Optional regenerate text override"
      :value="regenText"
      @input="onRegenInput"
    >

    <div v-if="segment.audio_path" class="space-y-2">
      <div class="space-y-1">
        <p class="text-[11px] font-medium text-muted-foreground">Original</p>
        <audio :src="audioUrl" controls preload="none" class="w-full" />
      </div>
      <div v-if="cleanedAudioUrl" class="space-y-1">
        <p class="text-[11px] font-medium text-emerald-700 dark:text-emerald-300">Studio Voice</p>
        <audio :src="cleanedAudioUrl" controls preload="none" class="w-full" />
      </div>
    </div>

    <section
      v-if="latestImagePreviewFrames.length"
      class="space-y-2 rounded-xl border bg-muted/20 p-3"
    >
      <div class="flex items-center justify-between gap-2">
        <p class="text-xs font-medium text-muted-foreground">
          Latest Image Sequence
        </p>
        <span class="text-[11px] text-muted-foreground">
          {{ latestImagePreviewFrames.length }} frame{{ latestImagePreviewFrames.length === 1 ? '' : 's' }}
        </span>
      </div>

      <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <button
          v-for="(frame, index) in latestImagePreviewFrames"
          :key="frame.id"
          type="button"
          data-testid="segment-image-preview"
          class="group space-y-1 text-left"
          @click="openLightboxAt(index)"
        >
          <div class="aspect-video overflow-hidden rounded-lg border bg-muted/40">
            <img
              :src="frame.src"
              :alt="`Sequence frame ${frame.step_order}`"
              class="h-full w-full object-cover transition-transform duration-200 group-hover:scale-[1.03]"
            >
          </div>
          <p class="line-clamp-1 text-[11px] text-muted-foreground">
            {{ previewStepLabel(frame) }}
          </p>
        </button>
      </div>

      <Dialog v-model:open="lightboxOpen">
        <DialogContent
          data-testid="segment-image-lightbox"
          class="!w-[86vw] !max-w-[86vw] sm:!max-w-[86vw]"
        >
          <DialogHeader>
            <DialogTitle>Latest Image Sequence</DialogTitle>
            <DialogDescription>
              Use arrows to browse. Carousel loops continuously.
            </DialogDescription>
          </DialogHeader>

          <Carousel
            :opts="{ loop: true, duration: 0, startIndex: lightboxStartIndex }"
            @init-api="onLightboxInit"
          >
            <CarouselContent class="!-ml-0">
              <CarouselItem
                v-for="frame in latestImagePreviewFrames"
                :key="`lightbox-${frame.id}`"
                class="!pl-0"
              >
                <div class="space-y-2">
                  <div class="flex max-h-[68vh] min-h-[360px] items-center justify-center rounded-xl border bg-muted/30 p-2">
                    <img
                      :src="frame.src"
                      :alt="`Sequence frame ${frame.step_order}`"
                      class="max-h-[64vh] w-full rounded object-contain"
                    >
                  </div>
                  <div class="space-y-1">
                    <p class="text-xs font-medium text-muted-foreground">
                      {{ previewStepLabel(frame) }}
                    </p>
                    <p class="text-sm leading-relaxed">
                      {{ frame.prompt }}
                    </p>
                  </div>
                </div>
              </CarouselItem>
            </CarouselContent>

            <CarouselPrevious class="left-2" />
            <CarouselNext class="right-2" />
          </Carousel>
        </DialogContent>
      </Dialog>
    </section>

    <NarrationTrimPanel
      v-if="trimOpen"
      :segment-id="segment.id"
      :transcription="transcription"
      :trim-range-label="trimRangeLabel"
      :trim-selection-armed="trimSelectionArmed"
      :trim-waveform-loading="trimWaveformLoading"
      :trim-waveform-error="trimWaveformError"
      :has-trim-selection="hasTrimSelection"
      :trim-applying="trimApplying"
      :can-preview-trim="canPreviewTrim"
      :trim-waveform-ready="trimWaveformReady"
      :trim-selection-start="trimSelectionStart"
      :trim-selection-end="trimSelectionEnd"
      :trim-selection-duration="trimSelectionDuration"
      :trim-audio-duration="trimAudioDuration"
      @begin-selection="emit('trim-begin-selection')"
      @preview="emit('trim-preview')"
      @apply="emit('trim-apply')"
      @clear-selection="emit('trim-clear-selection')"
      @cancel="emit('trim-cancel')"
      @regenerate-waveform="emit('trim-regenerate-waveform', segment.id)"
      @retry-waveform="emit('trim-retry-waveform', segment.id)"
      @waveform-pointerdown="emit('trim-waveform-pointerdown', $event, segment.id)"
    />

    <section v-if="expandedTranscript && transcription" class="space-y-2 rounded-xl border bg-muted/30 p-3">
      <div class="flex items-center justify-between gap-2">
        <p class="text-sm font-medium">Transcription</p>
        <button class="rounded-md border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 dark:border-red-900 dark:text-red-300" @click="emit('delete-transcription', segment.id)">
          Delete
        </button>
      </div>

      <p class="text-sm">{{ transcription.text }}</p>

      <div v-if="transcription.words?.length" class="flex flex-wrap gap-1">
        <button
          v-for="(word, index) in transcription.words"
          :key="`${segment.id}-${index}`"
          type="button"
          class="rounded border px-1.5 py-0.5 text-xs transition-colors"
          :class="activeWordIdx === index
            ? 'border-primary bg-primary text-primary-foreground'
            : 'border-border bg-background hover:bg-muted'"
          :title="`${word.start.toFixed(2)}s - ${word.end.toFixed(2)}s`"
          @click="emit('seek-word', segment.id, word.start)"
        >
          {{ word.word }}
        </button>
      </div>
    </section>
  </article>
</template>
