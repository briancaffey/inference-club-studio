<script setup lang="ts">
import { computed, ref } from 'vue'
import type { NarrationSegment } from '~/types'
import type {
  NarrationImageSequencesController,
} from '~/composables/narration-next/useNarrationImageSequences'
import NarrationImageSeriesCard from '~/components/narration-next/NarrationImageSeriesCard.vue'

const props = defineProps<{
  segment: NarrationSegment
  controller: NarrationImageSequencesController
}>()

const manualName = ref('')
const manualPrompt = ref('')
const manualAutoGenerate = ref(true)
const autoName = ref('')
const autoDirection = ref('')
const autoTargetImages = ref(4)
const localMessage = ref<string | null>(null)

const segmentId = computed(() => props.segment.id)
const series = computed(() => props.controller.listForSegment(segmentId.value))
const loading = computed(() => props.controller.isLoadingSegment(segmentId.value))
const creating = computed(() => props.controller.isCreatingSegment(segmentId.value))
const error = computed(() => props.controller.segmentError(segmentId.value))

async function onRefresh() {
  localMessage.value = null
  try {
    await props.controller.refreshSegment(segmentId.value)
  } catch {
    // segment-level error state is already exposed by the controller
  }
}

async function onCreateManualSeries() {
  const prompt = manualPrompt.value.trim()
  if (!prompt) return

  localMessage.value = null
  try {
    await props.controller.createManualSeries(segmentId.value, {
      name: manualName.value,
      initialPrompt: prompt,
      autoGenerate: manualAutoGenerate.value,
    })
    manualName.value = ''
    manualPrompt.value = ''
    manualAutoGenerate.value = true
    localMessage.value = 'Image sequence created'
  } catch {
    localMessage.value = null
  }
}

async function onCreateAutoSeries() {
  const direction = autoDirection.value.trim()
  if (!direction) return

  localMessage.value = null
  try {
    await props.controller.createAutoSeries(segmentId.value, {
      name: autoName.value,
      creativeDirection: direction,
      targetImages: autoTargetImages.value,
    })
    autoName.value = ''
    autoDirection.value = ''
    autoTargetImages.value = 4
    localMessage.value = 'Sequence plan generated and queued'
  } catch {
    localMessage.value = null
  }
}
</script>

<template>
  <section class="space-y-3 rounded-2xl border border-border/70 bg-muted/20 p-3">
    <header class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h4 class="text-sm font-semibold">Image Sequences</h4>
        <p class="text-xs text-muted-foreground">
          Build visual branches for segment #{{ segment.position }}.
        </p>
      </div>

      <button
        class="rounded-md border px-2 py-1 text-xs hover:bg-muted disabled:opacity-50"
        :disabled="loading"
        @click="onRefresh"
      >
        {{ loading ? 'Refreshing...' : 'Refresh' }}
      </button>
    </header>

    <p v-if="error" class="text-xs text-red-600 dark:text-red-300">
      {{ error }}
    </p>
    <p v-if="localMessage" class="text-xs text-emerald-700 dark:text-emerald-300">
      {{ localMessage }}
    </p>

    <div class="grid gap-3 lg:grid-cols-2">
      <form class="space-y-2 rounded-xl border bg-card p-3" @submit.prevent="onCreateManualSeries">
        <h5 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Quick Start
        </h5>
        <input
          v-model="manualName"
          class="w-full rounded border bg-background px-2 py-1 text-xs"
          placeholder="Series name (optional)"
        >
        <textarea
          v-model="manualPrompt"
          rows="3"
          class="w-full rounded border bg-background px-2 py-1.5 text-xs"
          placeholder="Initial image prompt..."
        />
        <label class="inline-flex items-center gap-2 text-xs">
          <input v-model="manualAutoGenerate" type="checkbox">
          Generate immediately
        </label>
        <button
          class="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50"
          :disabled="creating || !manualPrompt.trim()"
          type="submit"
        >
          {{ creating ? 'Creating...' : 'Create Sequence' }}
        </button>
      </form>

      <form class="space-y-2 rounded-xl border bg-card p-3" @submit.prevent="onCreateAutoSeries">
        <h5 class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Plan With AI
        </h5>
        <input
          v-model="autoName"
          class="w-full rounded border bg-background px-2 py-1 text-xs"
          placeholder="Series name (optional)"
        >
        <textarea
          v-model="autoDirection"
          rows="3"
          class="w-full rounded border bg-background px-2 py-1.5 text-xs"
          placeholder="Creative direction for this sequence..."
        />
        <label class="space-y-1 text-xs text-muted-foreground">
          Target images
          <input
            v-model.number="autoTargetImages"
            type="number"
            min="2"
            max="12"
            class="w-full rounded border bg-background px-2 py-1 text-xs text-foreground"
          >
        </label>
        <button
          class="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground hover:opacity-90 disabled:opacity-50"
          :disabled="creating || !autoDirection.trim()"
          type="submit"
        >
          {{ creating ? 'Planning...' : 'Plan + Generate' }}
        </button>
      </form>
    </div>

    <div
      v-if="loading && !series.length"
      class="rounded-xl border border-dashed p-4 text-xs text-muted-foreground"
    >
      Loading image sequences...
    </div>
    <div
      v-else-if="!series.length"
      class="rounded-xl border border-dashed p-4 text-xs text-muted-foreground"
    >
      No image sequences for this segment yet.
    </div>
    <div v-else class="space-y-3">
      <NarrationImageSeriesCard
        v-for="item in series"
        :key="item.id"
        :segment-id="segmentId"
        :series="item"
        :controller="controller"
      />
    </div>
  </section>
</template>
