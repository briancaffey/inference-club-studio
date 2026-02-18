<script setup lang="ts">
import { GripVertical, Loader2, AlertCircle, Play, Trash2, ChevronDown, ChevronUp } from 'lucide-vue-next'
import type { Cut } from '~/types'

const props = defineProps<{
  cut: Cut
  projectId: string
  expanded?: boolean
}>()

const emit = defineEmits<{
  preview: [cut: Cut]
  delete: [cutId: string]
  toggleExpand: [cutId: string]
}>()

const { mediaUrl } = useApi()
const store = useProjectsStore()
const generationsStore = useGenerationsStore()
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

function handleCardClick(e: MouseEvent) {
  // Don't expand if clicking on interactive elements
  const target = e.target as HTMLElement
  if (target.closest('button') || target.closest('.cursor-grab')) return
  if (props.cut.status === 'ready') {
    emit('toggleExpand', props.cut.id)
  }
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
  <div
    class="group cursor-pointer rounded-lg border bg-card p-3 transition-shadow hover:shadow-sm"
    :class="{ 'cursor-default': cut.status !== 'ready' }"
    @click="handleCardClick"
  >
    <div class="flex items-start gap-3">
      <div class="mt-1 cursor-grab text-muted-foreground" @click.stop>
        <GripVertical class="h-5 w-5" />
      </div>

      <!-- Thumbnail -->
      <div
        class="relative h-24 w-40 flex-shrink-0 cursor-pointer overflow-hidden rounded bg-muted"
        @click.stop="$emit('preview', cut)"
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
      <div class="flex flex-shrink-0 items-center gap-1">
        <ChevronUp v-if="expanded && cut.status === 'ready'" class="h-4 w-4 text-muted-foreground" />
        <ChevronDown v-else-if="cut.status === 'ready'" class="h-4 w-4 text-muted-foreground" />
        <Button
          variant="ghost"
          size="icon"
          class="h-8 w-8 opacity-0 transition-opacity group-hover:opacity-100"
          :disabled="deleting"
          @click.stop="handleDelete"
        >
          <Trash2 class="h-4 w-4 text-destructive" />
        </Button>
      </div>
    </div>
  </div>

  <!-- Expanded generations section -->
  <div v-if="expanded && cut.status === 'ready'" class="mt-3 border-t pt-3">
    <CutInsightsPanel
      :project-id="projectId"
      :cut-id="cut.id"
      class="mb-3"
    />
    <GenerationList
      :generations="generationsStore.generationsForCut(cut.id)"
      :project-id="projectId"
      :cut-id="cut.id"
      :cut-width="cut.width"
      :cut-height="cut.height"
      :cut-file-path="cut.file_path"
    />
  </div>
</template>
