<script setup lang="ts">
import type { Cut } from '~/types'

const props = defineProps<{
  projectId: string
  cut: Cut | null
}>()

const open = defineModel<boolean>('open', { default: false })

const { mediaUrl, baseURL } = useApi()
const cutAiStore = useCutAiStore()
const loadingInsights = ref(false)
const generatingInsights = ref(false)
const videoRef = ref<HTMLVideoElement | null>(null)
const insightsPollInterval = ref<ReturnType<typeof setInterval>>()

const videoSrc = computed(() => {
  const path = props.cut?.file_path
  if (!path) return null
  if (path.startsWith('/media/')) return `${baseURL}${path}`
  const resolved = mediaUrl(path)
  return resolved || path
})

const aiState = computed(() => {
  if (!props.cut) return null
  return cutAiStore.stateForCut(props.cut.id)
})

const clipOverview = computed(() => aiState.value?.clip_overview_text || null)

const clipOverviewStatus = computed(() => aiState.value?.clip_overview_status || 'pending')
const insightsGenerating = computed(() => {
  const state = aiState.value
  if (!state) return false
  return ['queued', 'running'].includes(state.clip_overview_status) || ['queued', 'running'].includes(state.first_frame_status)
})

async function fetchInsights() {
  if (!props.cut) return
  loadingInsights.value = true
  try {
    await cutAiStore.fetchState(props.projectId, props.cut.id)
  } catch {
    // Keep modal usable even if AI insights fetch fails.
  } finally {
    loadingInsights.value = false
  }
}

async function generateInsights() {
  if (!props.cut) return
  generatingInsights.value = true
  try {
    await cutAiStore.regenerate(props.projectId, props.cut.id, ['clip_overview', 'first_frame'])
    await fetchInsights()
  } finally {
    generatingInsights.value = false
  }
}

async function startPlayback() {
  const el = videoRef.value
  if (!el) return
  try {
    el.currentTime = 0
    await el.play()
  } catch {
    // Autoplay can be blocked by browser policy; controls remain available.
  }
}

function stopPlayback() {
  const el = videoRef.value
  if (!el) return
  el.pause()
  el.currentTime = 0
}

watch(
  () => [open.value, props.cut?.id],
  async ([isOpen, cutId]) => {
    if (!isOpen) {
      stopPlayback()
      return
    }
    if (!cutId) return
    await fetchInsights()
    await nextTick()
    await startPlayback()
  },
  { immediate: true },
)

watch(
  () => [open.value, insightsGenerating.value],
  ([isOpen, generating]) => {
    if (isOpen && generating && !insightsPollInterval.value) {
      insightsPollInterval.value = setInterval(() => {
        fetchInsights()
      }, 3000)
      return
    }
    if (insightsPollInterval.value && (!isOpen || !generating)) {
      clearInterval(insightsPollInterval.value)
      insightsPollInterval.value = undefined
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  stopPlayback()
  if (insightsPollInterval.value) {
    clearInterval(insightsPollInterval.value)
  }
})
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="!left-1/2 !top-1/2 !h-[94vh] !max-h-[94vh] !w-[96vw] !max-w-[96vw] !translate-x-[-50%] !translate-y-[-50%] p-0 sm:!max-w-[96vw]">
      <DialogHeader class="px-6 pt-6">
        <DialogTitle>{{ cut?.original_filename }}</DialogTitle>
        <DialogDescription v-if="cut">
          {{ cut.width }}x{{ cut.height }} &middot; {{ cut.codec }} &middot;
          {{ cut.duration ? `${Math.round(cut.duration)}s` : '' }}
        </DialogDescription>
      </DialogHeader>

      <div class="grid h-[calc(94vh-5.25rem)] grid-cols-[minmax(560px,42%)_minmax(0,58%)] gap-5 overflow-hidden px-7 pb-7">
        <div class="flex h-full flex-col overflow-hidden rounded-lg border bg-muted/20 p-4">
          <div class="mb-3 flex items-center justify-between gap-2">
            <h3 class="text-base font-semibold">Clip Overview</h3>
            <div class="flex items-center gap-1">
              <Badge
                :variant="clipOverviewStatus === 'completed' ? 'default' : clipOverviewStatus === 'error' ? 'destructive' : 'secondary'"
                class="text-xs"
              >
                {{ clipOverviewStatus }}
              </Badge>
              <CopyButton
                :text="clipOverview"
                tooltip="Copy overview"
                class="h-8 w-8"
              />
            </div>
          </div>

          <div class="mb-3 grid grid-cols-2 gap-2 rounded-md border bg-background p-3 text-sm">
            <div>
              <p class="text-xs text-muted-foreground">Resolution</p>
              <p class="font-medium">{{ cut?.width }}x{{ cut?.height }}</p>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">Duration</p>
              <p class="font-medium">{{ cut?.duration ? `${Math.round(cut.duration)}s` : '--' }}</p>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">FPS</p>
              <p class="font-medium">{{ cut?.fps || '--' }}</p>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">Codec</p>
              <p class="font-medium">{{ cut?.codec || '--' }}</p>
            </div>
          </div>

          <div class="min-h-0 flex-1 overflow-auto rounded-md border bg-background p-3">
            <p v-if="loadingInsights" class="text-sm text-muted-foreground">
              Loading overview...
            </p>
            <p v-else-if="clipOverview" class="whitespace-pre-wrap text-sm leading-6">
              {{ clipOverview }}
            </p>
            <div v-else class="space-y-3">
              <p class="text-sm text-muted-foreground">
                Overview not available yet. Generate or refresh cut insights.
              </p>
              <Button
                size="sm"
                :disabled="loadingInsights || generatingInsights || insightsGenerating"
                @click="generateInsights"
              >
                {{
                  generatingInsights || insightsGenerating
                    ? 'Generating insights...'
                    : 'Generate Clip Insights'
                }}
              </Button>
            </div>
          </div>
        </div>

        <div class="flex h-full flex-col overflow-hidden rounded-lg border bg-black/5 p-3">
          <video
            v-if="videoSrc"
            ref="videoRef"
            :src="videoSrc"
            controls
            class="h-full w-full rounded-lg object-contain"
            preload="metadata"
          >
            Your browser does not support video playback.
          </video>
          <div v-else class="flex h-full items-center justify-center rounded-lg bg-muted">
            <p class="text-sm text-muted-foreground">Video unavailable for this cut.</p>
          </div>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
