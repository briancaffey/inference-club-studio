<script setup lang="ts">
import { Film } from 'lucide-vue-next'
import type { Take } from '~/types'

const props = defineProps<{
  projectId: string
  cutId: string
  generationId: string
  prefill?: Take | null
}>()

const open = defineModel<boolean>('open', { default: false })

const store = useTakesStore()
const submitting = ref(false)

const form = reactive({
  prompt: '',
  width: 641,
  height: 449,
  frame_count: 121,
  seed: -1,
})

type DimKey = 'default' | 'custom'
const selectedDim = ref<DimKey>('default')

const dimPresets: { key: DimKey; label: string; getSize?: () => { w: number; h: number } }[] = [
  {
    key: 'default',
    label: 'Default (641x449)',
    getSize: () => ({ w: 641, h: 449 }),
  },
  {
    key: 'custom',
    label: 'Custom',
  },
]

// Snap dimensions to nearest valid LTX value (32n+1)
function snapDim(v: number): number {
  const n = Math.max(2, Math.round((v - 1) / 32))
  return 32 * n + 1
}

// Snap frame count to nearest valid LTX value (8n+1)
function snapFrames(v: number): number {
  const n = Math.max(1, Math.round((v - 1) / 8))
  return 8 * n + 1
}

watch(open, (isOpen) => {
  if (isOpen && props.prefill) {
    // Pre-fill from existing take
    form.prompt = props.prefill.prompt
    form.width = props.prefill.width
    form.height = props.prefill.height
    form.frame_count = props.prefill.frame_count
    form.seed = -1
    const isDefault = form.width === 641 && form.height === 449
    selectedDim.value = isDefault ? 'default' : 'custom'
  } else if (isOpen) {
    // Reset to defaults
    form.prompt = ''
    form.width = 641
    form.height = 449
    form.frame_count = 121
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
        <DialogTitle>{{ prefill ? 'Regenerate Take' : 'Create Video Take' }}</DialogTitle>
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
              <label class="text-xs text-muted-foreground">Width (32n+1)</label>
              <Input
                v-model.number="form.width"
                type="number"
                :min="65"
                :max="1281"
                @blur="form.width = snapDim(form.width)"
              />
            </div>
            <div class="space-y-1">
              <label class="text-xs text-muted-foreground">Height (32n+1)</label>
              <Input
                v-model.number="form.height"
                type="number"
                :min="65"
                :max="1281"
                @blur="form.height = snapDim(form.height)"
              />
            </div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-2">
            <label class="text-sm font-medium">Frame Count (8n+1)</label>
            <Input
              v-model.number="form.frame_count"
              type="number"
              :min="9"
              :max="257"
              @blur="form.frame_count = snapFrames(form.frame_count)"
            />
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
