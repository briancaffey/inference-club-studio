<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'
import type { Generation } from '~/types'

const props = defineProps<{
  generations: Generation[]
  projectId: string
  cutId: string
  cutWidth: number | null
  cutHeight: number | null
}>()

const formOpen = ref(false)
const takesStore = useTakesStore()
const expandedGenerationId = ref<string | null>(null)

function toggleExpand(generationId: string) {
  if (expandedGenerationId.value === generationId) {
    expandedGenerationId.value = null
  } else {
    expandedGenerationId.value = generationId
    takesStore.fetchTakes(props.projectId, props.cutId, generationId)
  }
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <h4 class="text-sm font-medium text-muted-foreground">
        Style Transfer ({{ generations.length }})
      </h4>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button size="sm" variant="outline" @click="formOpen = true">
              <Sparkles class="mr-1.5 h-3.5 w-3.5" />
              Generate
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>Create a styled image from this cut's first frame</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>

    <div v-if="generations.length === 0" class="py-4 text-center text-sm text-muted-foreground">
      No generations yet. Click Generate to create one.
    </div>

    <div v-else class="space-y-2">
      <GenerationCard
        v-for="gen in generations"
        :key="gen.id"
        :generation="gen"
        :project-id="projectId"
        :cut-id="cutId"
        :expanded="expandedGenerationId === gen.id"
        :takes="takesStore.takesForGeneration(gen.id)"
        @toggle-expand="toggleExpand"
      />
    </div>

    <GenerationForm
      v-model:open="formOpen"
      :project-id="projectId"
      :cut-id="cutId"
      :cut-width="cutWidth"
      :cut-height="cutHeight"
    />
  </div>
</template>
