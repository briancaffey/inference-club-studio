<script setup lang="ts">
import type { Cut } from '~/types'

const props = defineProps<{
  cut: Cut | null
}>()

const open = defineModel<boolean>('open', { default: false })

const { mediaUrl } = useApi()

const videoSrc = computed(() => {
  if (!props.cut) return null
  return mediaUrl(props.cut.file_path)
})
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="max-w-3xl p-0">
      <DialogHeader class="px-6 pt-6">
        <DialogTitle>{{ cut?.original_filename }}</DialogTitle>
        <DialogDescription v-if="cut">
          {{ cut.width }}x{{ cut.height }} &middot; {{ cut.codec }} &middot;
          {{ cut.duration ? `${Math.round(cut.duration)}s` : '' }}
        </DialogDescription>
      </DialogHeader>
      <div class="px-6 pb-6">
        <video
          v-if="videoSrc"
          :src="videoSrc"
          controls
          class="w-full rounded-lg"
          autoplay
        >
          Your browser does not support video playback.
        </video>
      </div>
    </DialogContent>
  </Dialog>
</template>
