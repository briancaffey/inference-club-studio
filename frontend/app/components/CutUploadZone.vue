<script setup lang="ts">
import { Upload } from 'lucide-vue-next'

const props = defineProps<{
  projectId: string
}>()

const store = useProjectsStore()
const dragging = ref(false)
const uploading = ref(false)
const fileInput = ref<HTMLInputElement>()

function onDragOver(e: DragEvent) {
  e.preventDefault()
  dragging.value = true
}

function onDragLeave() {
  dragging.value = false
}

async function onDrop(e: DragEvent) {
  e.preventDefault()
  dragging.value = false
  const files = Array.from(e.dataTransfer?.files || []).filter(f =>
    f.type.startsWith('video/'),
  )
  if (files.length > 0) await uploadFiles(files)
}

async function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  if (files.length > 0) await uploadFiles(files)
  input.value = ''
}

async function uploadFiles(files: File[]) {
  uploading.value = true
  try {
    await store.uploadCuts(props.projectId, files)
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div
    :class="[
      'relative flex min-h-[160px] cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 transition-colors',
      dragging
        ? 'border-primary bg-primary/5'
        : 'border-muted-foreground/25 hover:border-primary/50',
    ]"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
    @click="fileInput?.click()"
  >
    <input
      ref="fileInput"
      type="file"
      accept="video/*"
      multiple
      class="hidden"
      @change="onFileSelect"
    />
    <Upload class="mb-2 h-8 w-8 text-muted-foreground" />
    <p v-if="uploading" class="text-sm text-muted-foreground">Uploading...</p>
    <template v-else>
      <p class="text-sm font-medium">Drop video files here or click to browse</p>
      <p class="text-xs text-muted-foreground">MP4, MOV, AVI, MKV supported</p>
    </template>
  </div>
</template>
