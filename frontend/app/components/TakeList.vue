<script setup lang="ts">
import { Film } from 'lucide-vue-next'
import type { Take } from '~/types'

const props = defineProps<{
  takes: Take[]
  projectId: string
  cutId: string
  generationId: string
  cutFilePath: string | null
  generationImagePath: string | null
}>()

const formOpen = ref(false)
const prefill = ref<Take | null>(null)

function openNew() {
  prefill.value = null
  formOpen.value = true
}

function openFromTake(take: Take) {
  prefill.value = take
  formOpen.value = true
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <h4 class="text-sm font-medium text-muted-foreground">
        Takes ({{ takes.length }})
      </h4>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button size="sm" variant="outline" @click="openNew">
              <Film class="mr-1.5 h-3.5 w-3.5" />
              Create Take
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>Generate video using this styled image and the cut's motion</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>

    <div v-if="takes.length === 0" class="py-4 text-center text-sm text-muted-foreground">
      No takes yet. Click Create Take to generate video.
    </div>

    <div v-else class="space-y-2">
      <TakeCard
        v-for="take in takes"
        :key="take.id"
        :take="take"
        :project-id="projectId"
        :cut-id="cutId"
        :generation-id="generationId"
        :cut-file-path="cutFilePath"
        :generation-image-path="generationImagePath"
        @regenerate="openFromTake"
      />
    </div>

    <TakeForm
      v-model:open="formOpen"
      :project-id="projectId"
      :cut-id="cutId"
      :generation-id="generationId"
      :prefill="prefill"
    />
  </div>
</template>
