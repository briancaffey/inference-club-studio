<script setup lang="ts">
import { Loader2, AlertCircle, Trash2, Film, RefreshCw } from 'lucide-vue-next'
import type { Take } from '~/types'

const props = defineProps<{
  take: Take
  projectId: string
  cutId: string
  generationId: string
  cutFilePath: string | null
  generationImagePath: string | null
}>()

const emit = defineEmits<{
  regenerate: [take: Take]
}>()

const { mediaUrl } = useApi()
const store = useTakesStore()
const deleting = ref(false)
const previewOpen = ref(false)

const videoSrc = computed(() => mediaUrl(props.take.output_video_path))
const cannySrc = computed(() => mediaUrl(props.take.canny_video_path))
const cutVideoSrc = computed(() => mediaUrl(props.cutFilePath))
const generationImgSrc = computed(() => mediaUrl(props.generationImagePath))

// Video sync refs — take is the master, others follow
const takeVideoRef = ref<HTMLVideoElement | null>(null)
const cannyVideoRef = ref<HTMLVideoElement | null>(null)
const cutVideoRef = ref<HTMLVideoElement | null>(null)
let syncRaf: number | null = null

const isProcessing = computed(() =>
  ['pending', 'uploading_assets', 'generating', 'downloading', 'encoding_canny'].includes(
    props.take.status,
  ),
)

const statusLabel = computed(() => {
  switch (props.take.status) {
    case 'pending':
      return 'Queued'
    case 'uploading_assets':
      return 'Uploading assets...'
    case 'generating':
      return 'Generating video...'
    case 'downloading':
      return 'Downloading...'
    case 'encoding_canny':
      return 'Encoding canny...'
    case 'completed':
      return 'Completed'
    case 'error':
      return 'Error'
    default:
      return props.take.status
  }
})

async function handleDelete() {
  deleting.value = true
  try {
    await store.deleteTake(props.projectId, props.cutId, props.generationId, props.take.id)
  } finally {
    deleting.value = false
  }
}

// Sync a follower video to the master take video
function syncFollower(master: HTMLVideoElement, follower: HTMLVideoElement) {
  const masterDuration = master.duration
  if (!masterDuration || isNaN(masterDuration)) return

  const followerDuration = follower.duration
  if (!followerDuration || isNaN(followerDuration)) return

  const targetTime = master.currentTime % followerDuration

  if (Math.abs(follower.currentTime - targetTime) > 0.15) {
    follower.currentTime = targetTime
  }

  if (!master.paused && follower.paused) {
    follower.play()
  } else if (master.paused && !follower.paused) {
    follower.pause()
  }
}

function syncVideos() {
  const takeVid = takeVideoRef.value
  if (!takeVid) return

  if (cutVideoRef.value) syncFollower(takeVid, cutVideoRef.value)
  if (cannyVideoRef.value) syncFollower(takeVid, cannyVideoRef.value)

  syncRaf = requestAnimationFrame(syncVideos)
}

function startSync() {
  if (syncRaf) cancelAnimationFrame(syncRaf)
  syncRaf = requestAnimationFrame(syncVideos)
}

function stopSync() {
  if (syncRaf) {
    cancelAnimationFrame(syncRaf)
    syncRaf = null
  }
}

watch(previewOpen, (open) => {
  if (open) {
    nextTick(startSync)
  } else {
    stopSync()
  }
})

onUnmounted(stopSync)
</script>

<template>
  <div class="group rounded-lg border bg-card p-3 transition-shadow hover:shadow-sm">
    <div class="flex items-start gap-3">
      <!-- Video thumbnail -->
      <div
        class="relative h-28 w-40 flex-shrink-0 cursor-pointer overflow-hidden rounded bg-muted"
        @click="videoSrc && (previewOpen = true)"
      >
        <video
          v-if="videoSrc"
          :src="videoSrc"
          class="h-full w-full object-cover"
          muted
          preload="metadata"
        />
        <div v-else class="flex h-full w-full items-center justify-center">
          <Loader2 v-if="isProcessing" class="h-5 w-5 animate-spin text-muted-foreground" />
          <Film v-else class="h-5 w-5 text-muted-foreground" />
        </div>
      </div>

      <!-- Info -->
      <div class="min-w-0 flex-1">
        <p class="line-clamp-2 text-sm">{{ take.prompt }}</p>
        <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span>{{ take.width }}x{{ take.height }}</span>
          <span>{{ take.frame_count }} frames</span>
          <span v-if="take.actual_seed != null">seed: {{ take.actual_seed }}</span>
        </div>
        <div class="mt-1 flex items-center gap-2">
          <Badge
            :variant="take.status === 'error' ? 'destructive' : take.status === 'completed' ? 'default' : 'secondary'"
            class="text-xs"
          >
            <Loader2 v-if="isProcessing" class="mr-1 h-3 w-3 animate-spin" />
            <AlertCircle v-if="take.status === 'error'" class="mr-1 h-3 w-3" />
            {{ statusLabel }}
          </Badge>
        </div>
        <p v-if="take.error_message" class="mt-1 text-xs text-destructive">
          {{ take.error_message }}
        </p>
      </div>

      <!-- Actions -->
      <div class="flex flex-shrink-0 items-center gap-1">
        <CopyButton
          :text="take.prompt"
          tooltip="Copy prompt"
          copied-tooltip="Copied!"
          class="h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100"
        />
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="ghost"
                size="icon"
                class="h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100"
                @click="$emit('regenerate', take)"
              >
                <RefreshCw class="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              <p>Create new take with these settings</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
        <Button
          variant="ghost"
          size="icon"
          class="h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100"
          :disabled="deleting"
          @click="handleDelete"
        >
          <Trash2 class="h-4 w-4 text-destructive" />
        </Button>
      </div>
    </div>

    <!-- 2x2 preview dialog -->
    <Dialog v-model:open="previewOpen">
      <DialogContent class="max-w-[90vw] w-[90vw]">
        <DialogHeader>
          <DialogTitle class="line-clamp-1">{{ take.prompt }}</DialogTitle>
        </DialogHeader>

        <div class="grid grid-cols-2 gap-3">
          <!-- Top-left: Take output (master) -->
          <div class="text-center">
            <p class="mb-1.5 text-xs font-medium text-muted-foreground">Take</p>
            <video
              v-if="videoSrc"
              ref="takeVideoRef"
              :src="videoSrc"
              controls
              autoplay
              loop
              class="max-h-[40vh] w-full rounded object-contain"
            />
          </div>

          <!-- Top-right: Canny guidance -->
          <div class="text-center">
            <p class="mb-1.5 text-xs font-medium text-muted-foreground">Canny Guidance</p>
            <video
              v-if="cannySrc"
              ref="cannyVideoRef"
              :src="cannySrc"
              muted
              playsinline
              loop
              class="max-h-[40vh] w-full rounded object-contain"
            />
            <div v-else class="flex h-40 items-center justify-center rounded bg-muted">
              <p class="text-xs text-muted-foreground">Not available</p>
            </div>
          </div>

          <!-- Bottom-left: Original cut -->
          <div class="text-center">
            <p class="mb-1.5 text-xs font-medium text-muted-foreground">Original Cut</p>
            <video
              v-if="cutVideoSrc"
              ref="cutVideoRef"
              :src="cutVideoSrc"
              muted
              playsinline
              loop
              class="max-h-[40vh] w-full rounded object-contain"
            />
            <div v-else class="flex h-40 items-center justify-center rounded bg-muted">
              <p class="text-xs text-muted-foreground">Not available</p>
            </div>
          </div>

          <!-- Bottom-right: Style image -->
          <div class="text-center">
            <p class="mb-1.5 text-xs font-medium text-muted-foreground">Style Image</p>
            <img
              v-if="generationImgSrc"
              :src="generationImgSrc"
              alt="Style reference"
              class="max-h-[40vh] w-full rounded object-contain"
            />
            <div v-else class="flex h-40 items-center justify-center rounded bg-muted">
              <p class="text-xs text-muted-foreground">Not available</p>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
