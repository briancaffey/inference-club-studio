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

const generationsStore = useGenerationsStore()
const listRef = ref<HTMLElement>()
const localCuts = ref<Cut[]>([...props.cuts])
const expandedCutId = ref<string | null>(null)

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

function toggleExpand(cutId: string) {
  if (expandedCutId.value === cutId) {
    expandedCutId.value = null
  } else {
    expandedCutId.value = cutId
    generationsStore.fetchGenerations(props.projectId, cutId)
  }
}
</script>

<template>
  <div ref="listRef" class="space-y-2">
    <CutCard
      v-for="cut in localCuts"
      :key="cut.id"
      :cut="cut"
      :project-id="projectId"
      :expanded="expandedCutId === cut.id"
      @preview="$emit('preview', $event)"
      @toggle-expand="toggleExpand"
    />
  </div>
</template>
