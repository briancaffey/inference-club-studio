<script setup lang="ts">
import { Film } from 'lucide-vue-next'

const props = defineProps<{
  projectId: string
  cutId: string
  generationId: string
}>()

const open = defineModel<boolean>('open', { default: false })

const store = useTakesStore()
const submitting = ref(false)

const form = reactive({
  prompt: '',
  width: 640,
  height: 448,
  frame_count: 122,
  seed: -1,
})

type DimKey = 'default' | 'custom'
const selectedDim = ref<DimKey>('default')

const dimPresets: { key: DimKey; label: string; getSize?: () => { w: number; h: number } }[] = [
  {
    key: 'default',
    label: 'Default (640x448)',
    getSize: () => ({ w: 640, h: 448 }),
  },
  {
    key: 'custom',
    label: 'Custom',
  },
]

watch(open, (isOpen) => {
  if (isOpen) {
    form.width = 640
    form.height = 448
    form.frame_count = 122
    form.seed = -1
    selectedDim.value = 'default'
  }
})

function applyDim(preset: (typeof dimPresets)[number]) {
  selectedDim.value = preset.key
  if (preset.getSize) {
    const { w, h } = preset.getSize()
    form.width = w
    form.height = h
  }
}

async function handleSubmit() {
  if (!form.prompt.trim()) return
  submitting.value = true
  try {
    await store.createTake(props.projectId, props.cutId, props.generationId, {
      prompt: form.prompt,
      width: form.width,
      height: form.height,
      frame_count: form.frame_count,
      seed: form.seed,
    })
    form.prompt = ''
    open.value = false
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="max-w-md">
      <DialogHeader>
        <DialogTitle>Create Video Take</DialogTitle>
        <DialogDescription>
          Generate video using this styled image and the cut's motion reference.
        </DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit.prevent="handleSubmit">
        <div class="space-y-2">
          <label class="text-sm font-medium">Prompt</label>
          <textarea
            v-model="form.prompt"
            class="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            placeholder="Describe the video scene..."
            required
          />
        </div>

        <div class="space-y-2">
          <label class="text-sm font-medium">Dimensions</label>
          <div class="flex flex-wrap gap-2">
            <Button
              v-for="preset in dimPresets"
              :key="preset.key"
              type="button"
              size="sm"
              :variant="selectedDim === preset.key ? 'default' : 'outline'"
              @click="applyDim(preset)"
            >
              {{ preset.label }}
            </Button>
          </div>
          <div v-if="selectedDim === 'custom'" class="grid grid-cols-2 gap-3">
            <div class="space-y-1">
              <label class="text-xs text-muted-foreground">Width</label>
              <Input v-model.number="form.width" type="number" :min="64" :max="1280" />
            </div>
            <div class="space-y-1">
              <label class="text-xs text-muted-foreground">Height</label>
              <Input v-model.number="form.height" type="number" :min="64" :max="1280" />
            </div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-2">
            <label class="text-sm font-medium">Frame Count</label>
            <Input v-model.number="form.frame_count" type="number" :min="1" :max="257" />
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium">Seed</label>
            <Input v-model.number="form.seed" type="number" :min="-1" />
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" @click="open = false">Cancel</Button>
          <Button type="submit" :disabled="submitting || !form.prompt.trim()">
            <Film class="mr-2 h-4 w-4" />
            {{ submitting ? 'Creating...' : 'Create Take' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
