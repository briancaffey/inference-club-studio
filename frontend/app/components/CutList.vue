<script setup lang="ts">
import { useSortable } from '@vueuse/integrations/useSortable'
import type { Cut } from '~/types'

const props = defineProps<{
  cuts: Cut[]
  projectId: string
}>()

const emit = defineEmits<{
  preview: [cut: Cut]
  reorder: [cutIds: string[]]
}>()

const listRef = ref<HTMLElement>()
const localCuts = ref<Cut[]>([...props.cuts])

watch(
  () => props.cuts,
  (newCuts) => {
    localCuts.value = [...newCuts]
  },
)

useSortable(listRef, localCuts, {
  handle: '.cursor-grab',
  animation: 150,
  onEnd() {
    const cutIds = localCuts.value.map(c => c.id)
    emit('reorder', cutIds)
  },
})
</script>

<template>
  <div ref="listRef" class="space-y-2">
    <CutCard
      v-for="cut in localCuts"
      :key="cut.id"
      :cut="cut"
      :project-id="projectId"
      @preview="$emit('preview', $event)"
    />
  </div>
</template>
