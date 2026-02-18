<script setup lang="ts">
import { Loader2, AlertCircle, Trash2, Film, Video } from 'lucide-vue-next'
import type { Take } from '~/types'

const props = defineProps<{
  take: Take
  projectId: string
  cutId: string
  generationId: string
}>()

const { mediaUrl } = useApi()
const store = useTakesStore()
const deleting = ref(false)
const previewOpen = ref(false)

const videoSrc = computed(() => mediaUrl(props.take.output_video_path))
const cannySrc = computed(() => mediaUrl(props.take.canny_video_path))

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
</script>

<template>
  <div class="group rounded-lg border bg-card p-3 transition-shadow hover:shadow-sm">
    <div class="flex items-start gap-3">
      <!-- Video thumbnail -->
      <div
        class="relative h-20 w-28 flex-shrink-0 cursor-pointer overflow-hidden rounded bg-muted"
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
          <a
            v-if="cannySrc"
            :href="cannySrc"
            target="_blank"
            class="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <Video class="h-3 w-3" />
            Canny
          </a>
        </div>
        <p v-if="take.error_message" class="mt-1 text-xs text-destructive">
          {{ take.error_message }}
        </p>
      </div>

      <!-- Actions -->
      <Button
        variant="ghost"
        size="icon"
        class="h-8 w-8 flex-shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
        :disabled="deleting"
        @click="handleDelete"
      >
        <Trash2 class="h-4 w-4 text-destructive" />
      </Button>
    </div>

    <!-- Video preview dialog -->
    <Dialog v-model:open="previewOpen">
      <DialogContent class="max-w-3xl">
        <DialogHeader>
          <DialogTitle class="line-clamp-1">{{ take.prompt }}</DialogTitle>
        </DialogHeader>
        <div v-if="videoSrc" class="flex justify-center">
          <video
            :src="videoSrc"
            controls
            autoplay
            loop
            class="max-h-[70vh] rounded"
          />
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
