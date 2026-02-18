<script setup lang="ts">
import { Loader2, AlertCircle, Trash2, Image as ImageIcon, ChevronDown, ChevronUp } from 'lucide-vue-next'
import type { Generation, Take } from '~/types'

const props = defineProps<{
  generation: Generation
  projectId: string
  cutId: string
  expanded?: boolean
  takes: Take[]
  cutFilePath: string | null
}>()

const emit = defineEmits<{
  toggleExpand: [generationId: string]
}>()

const { mediaUrl } = useApi()
const store = useGenerationsStore()
const deleting = ref(false)
const previewOpen = ref(false)

const outputSrc = computed(() => mediaUrl(props.generation.output_image_path))

const isProcessing = computed(() =>
  ['pending', 'extracting_frame', 'uploading_reference', 'generating', 'downloading'].includes(
    props.generation.status,
  ),
)

const statusLabel = computed(() => {
  switch (props.generation.status) {
    case 'pending':
      return 'Queued'
    case 'extracting_frame':
      return 'Extracting frame...'
    case 'uploading_reference':
      return 'Uploading reference...'
    case 'generating':
      return 'Generating...'
    case 'downloading':
      return 'Downloading...'
    case 'completed':
      return 'Completed'
    case 'error':
      return 'Error'
    default:
      return props.generation.status
  }
})

function handleCardClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  if (target.closest('button') || target.closest('img')) return
  if (props.generation.status === 'completed') {
    emit('toggleExpand', props.generation.id)
  }
}

async function handleDelete() {
  deleting.value = true
  try {
    await store.deleteGeneration(props.projectId, props.cutId, props.generation.id)
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div>
    <div
      class="group rounded-lg border bg-card p-3 transition-shadow hover:shadow-sm"
      :class="generation.status === 'completed' ? 'cursor-pointer' : ''"
      @click="handleCardClick"
    >
      <div class="flex items-start gap-3">
        <!-- Output image thumbnail -->
        <div
          class="relative h-28 w-28 flex-shrink-0 cursor-pointer overflow-hidden rounded bg-muted"
          @click.stop="outputSrc && (previewOpen = true)"
        >
          <img
            v-if="outputSrc"
            :src="outputSrc"
            alt="Generated output"
            class="h-full w-full object-cover"
          />
          <div v-else class="flex h-full w-full items-center justify-center">
            <Loader2 v-if="isProcessing" class="h-5 w-5 animate-spin text-muted-foreground" />
            <ImageIcon v-else class="h-5 w-5 text-muted-foreground" />
          </div>
        </div>

        <!-- Info -->
        <div class="min-w-0 flex-1">
          <p class="line-clamp-2 text-sm">{{ generation.prompt }}</p>
          <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span>{{ generation.width }}x{{ generation.height }}</span>
            <span>{{ generation.num_steps }} steps</span>
            <span v-if="generation.actual_seed != null">seed: {{ generation.actual_seed }}</span>
          </div>
          <div class="mt-1">
            <Badge
              :variant="generation.status === 'error' ? 'destructive' : generation.status === 'completed' ? 'default' : 'secondary'"
              class="text-xs"
            >
              <Loader2 v-if="isProcessing" class="mr-1 h-3 w-3 animate-spin" />
              <AlertCircle v-if="generation.status === 'error'" class="mr-1 h-3 w-3" />
              {{ statusLabel }}
            </Badge>
          </div>
          <p v-if="generation.error_message" class="mt-1 text-xs text-destructive">
            {{ generation.error_message }}
          </p>
        </div>

        <!-- Actions -->
        <div class="flex flex-shrink-0 items-center gap-1">
          <ChevronUp v-if="expanded && generation.status === 'completed'" class="h-4 w-4 text-muted-foreground" />
          <ChevronDown v-else-if="generation.status === 'completed'" class="h-4 w-4 text-muted-foreground" />
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

      <!-- Full preview dialog -->
      <Dialog v-model:open="previewOpen">
        <DialogContent class="max-w-3xl">
          <DialogHeader>
            <DialogTitle class="line-clamp-1">{{ generation.prompt }}</DialogTitle>
          </DialogHeader>
          <div v-if="outputSrc" class="flex justify-center">
            <img :src="outputSrc" alt="Generated output" class="max-h-[70vh] rounded object-contain" />
          </div>
        </DialogContent>
      </Dialog>
    </div>

    <!-- Expanded takes section -->
    <div v-if="expanded && generation.status === 'completed'" class="ml-6 mt-2 border-l pl-4">
      <TakeList
        :takes="takes"
        :project-id="projectId"
        :cut-id="cutId"
        :generation-id="generation.id"
        :cut-file-path="cutFilePath"
        :generation-image-path="generation.output_image_path"
      />
    </div>
  </div>
</template>
