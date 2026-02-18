<script setup lang="ts">
import { GripVertical, Loader2, AlertCircle, Play, Trash2 } from 'lucide-vue-next'
import type { Cut } from '~/types'

const props = defineProps<{
  cut: Cut
  projectId: string
}>()

const emit = defineEmits<{
  preview: [cut: Cut]
  delete: [cutId: string]
}>()

const { mediaUrl } = useApi()
const store = useProjectsStore()
const deleting = ref(false)

const thumbnailSrc = computed(() => mediaUrl(props.cut.thumbnail_path))

const isProcessing = computed(() =>
  ['uploaded', 'processing_metadata', 'extracting_audio'].includes(props.cut.status),
)

const statusLabel = computed(() => {
  switch (props.cut.status) {
    case 'uploaded': return 'Queued'
    case 'processing_metadata': return 'Analyzing...'
    case 'extracting_audio': return 'Extracting audio...'
    case 'ready': return 'Ready'
    case 'error': return 'Error'
    default: return props.cut.status
  }
})

function formatDuration(seconds: number | null) {
  if (seconds == null) return '--:--'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function formatResolution(w: number | null, h: number | null) {
  if (!w || !h) return ''
  return `${w}x${h}`
}

async function handleDelete() {
  deleting.value = true
  try {
    await store.deleteCut(props.projectId, props.cut.id)
    emit('delete', props.cut.id)
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="group flex items-start gap-3 rounded-lg border bg-card p-3 transition-shadow hover:shadow-sm">
    <div class="mt-1 cursor-grab text-muted-foreground">
      <GripVertical class="h-5 w-5" />
    </div>

    <!-- Thumbnail -->
    <div
      class="relative h-16 w-28 flex-shrink-0 cursor-pointer overflow-hidden rounded bg-muted"
      @click="$emit('preview', cut)"
    >
      <img
        v-if="thumbnailSrc"
        :src="thumbnailSrc"
        :alt="cut.original_filename"
        class="h-full w-full object-cover"
      />
      <div
        v-if="cut.status === 'ready'"
        class="absolute inset-0 flex items-center justify-center bg-black/20 opacity-0 transition-opacity group-hover:opacity-100"
      >
        <Play class="h-6 w-6 text-white" />
      </div>
      <div
        v-if="isProcessing"
        class="absolute inset-0 flex items-center justify-center bg-black/40"
      >
        <Loader2 class="h-5 w-5 animate-spin text-white" />
      </div>
    </div>

    <!-- Info -->
    <div class="min-w-0 flex-1">
      <p class="truncate text-sm font-medium">{{ cut.original_filename }}</p>
      <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>{{ formatDuration(cut.duration) }}</span>
        <span v-if="cut.width">{{ formatResolution(cut.width, cut.height) }}</span>
        <span v-if="cut.fps">{{ cut.fps }} fps</span>
        <span v-if="cut.codec">{{ cut.codec }}</span>
      </div>
      <div class="mt-1">
        <Badge
          :variant="cut.status === 'error' ? 'destructive' : cut.status === 'ready' ? 'default' : 'secondary'"
          class="text-xs"
        >
          <Loader2 v-if="isProcessing" class="mr-1 h-3 w-3 animate-spin" />
          <AlertCircle v-if="cut.status === 'error'" class="mr-1 h-3 w-3" />
          {{ statusLabel }}
        </Badge>
      </div>
      <p v-if="cut.error_message" class="mt-1 text-xs text-destructive">
        {{ cut.error_message }}
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
</template>
