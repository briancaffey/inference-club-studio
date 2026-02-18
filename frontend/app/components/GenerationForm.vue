<script setup lang="ts">
import { Loader2, Sparkles, WandSparkles } from 'lucide-vue-next'

const props = defineProps<{
  projectId: string
  cutId: string
  cutWidth: number | null
  cutHeight: number | null
}>()

const open = defineModel<boolean>('open', { default: false })

const store = useGenerationsStore()
const cutAiStore = useCutAiStore()
const submitting = ref(false)
const generatingPromptDraft = ref(false)

const defaultWidth = computed(() => props.cutWidth || 1024)
const defaultHeight = computed(() => props.cutHeight || 1024)

const form = reactive({
  prompt: '',
  width: defaultWidth.value,
  height: defaultHeight.value,
  num_steps: 16,
  seed: -1,
})

const aiHelper = reactive({
  style: '',
  content: '',
  generated: '',
})

// Reset dimensions to defaults when dialog opens
watch(open, async (isOpen) => {
  if (isOpen) {
    form.width = defaultWidth.value
    form.height = defaultHeight.value
    selectedRatio.value = 'original'
    aiHelper.generated = ''
    await cutAiStore.fetchState(props.projectId, props.cutId).catch(() => {})
    const ai = cutAiStore.stateForCut(props.cutId)
    if (!aiHelper.content.trim()) {
      aiHelper.content = ai?.first_frame_description_text || ai?.clip_overview_text || ''
    }
  }
})

type RatioKey = 'original' | '4:3' | 'custom'
const selectedRatio = ref<RatioKey>('original')

const ratioPresets: { key: RatioKey; label: string; getSize?: () => { w: number; h: number } }[] = [
  {
    key: 'original',
    label: 'Original',
    getSize: () => ({ w: defaultWidth.value, h: defaultHeight.value }),
  },
  {
    key: '4:3',
    label: '4:3 (1200x896)',
    getSize: () => ({ w: 1200, h: 896 }),
  },
  {
    key: 'custom',
    label: 'Custom',
  },
]

function applyRatio(preset: (typeof ratioPresets)[number]) {
  selectedRatio.value = preset.key
  if (preset.getSize) {
    const { w, h } = preset.getSize()
    form.width = w
    form.height = h
  }
}

async function generatePromptDraft() {
  if (!aiHelper.style.trim()) return
  generatingPromptDraft.value = true
  try {
    const draft = await cutAiStore.createFluxPromptDraft(props.projectId, props.cutId, {
      style: aiHelper.style,
      content: aiHelper.content || undefined,
    })
    aiHelper.generated = draft.prompt_text
    form.prompt = draft.prompt_text
  } finally {
    generatingPromptDraft.value = false
  }
}

async function handleSubmit() {
  if (!form.prompt.trim()) return
  submitting.value = true
  try {
    await store.createGeneration(props.projectId, props.cutId, {
      prompt: form.prompt,
      width: form.width,
      height: form.height,
      num_steps: form.num_steps,
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
        <DialogTitle>Generate Style Transfer</DialogTitle>
        <DialogDescription>
          Create a styled image from the first frame of this cut.
        </DialogDescription>
      </DialogHeader>

      <form class="space-y-4" @submit.prevent="handleSubmit">
        <div class="space-y-2 rounded-md border bg-muted/30 p-3">
          <div class="flex items-center justify-between">
            <label class="flex items-center gap-2 text-sm font-medium">
              <WandSparkles class="h-4 w-4" />
              AI Prompt Helper (Qwen3-VL)
            </label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              :disabled="generatingPromptDraft || !aiHelper.style.trim()"
              @click="generatePromptDraft"
            >
              <Loader2 v-if="generatingPromptDraft" class="mr-1.5 h-3.5 w-3.5 animate-spin" />
              <WandSparkles v-else class="mr-1.5 h-3.5 w-3.5" />
              Generate Draft
            </Button>
          </div>
          <div class="space-y-1">
            <label class="text-xs text-muted-foreground">Style</label>
            <Input
              v-model="aiHelper.style"
              placeholder="e.g. painterly cinematic neon noir"
            />
          </div>
          <div class="space-y-1">
            <label class="text-xs text-muted-foreground">Content</label>
            <textarea
              v-model="aiHelper.content"
              class="flex min-h-[70px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Optional. Defaults to first-frame/clip insights if available."
            />
          </div>
          <div v-if="aiHelper.generated" class="space-y-1">
            <div class="flex items-center justify-between">
              <label class="text-xs text-muted-foreground">Generated Draft</label>
              <CopyButton
                :text="aiHelper.generated"
                tooltip="Copy draft"
                class="h-7 w-7"
              />
            </div>
            <p class="max-h-28 overflow-auto whitespace-pre-wrap rounded border bg-background p-2 text-xs">
              {{ aiHelper.generated }}
            </p>
          </div>
        </div>

        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <label class="text-sm font-medium">Prompt</label>
            <CopyButton
              :text="form.prompt"
              tooltip="Copy prompt"
              class="h-7 w-7"
            />
          </div>
          <textarea
            v-model="form.prompt"
            class="flex min-h-[80px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            placeholder="Describe the style you want..."
            required
          />
        </div>

        <div class="space-y-2">
          <label class="text-sm font-medium">Dimensions</label>
          <div class="flex flex-wrap gap-2">
            <Button
              v-for="preset in ratioPresets"
              :key="preset.key"
              type="button"
              size="sm"
              :variant="selectedRatio === preset.key ? 'default' : 'outline'"
              @click="applyRatio(preset)"
            >
              {{ preset.label }}
            </Button>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1">
              <label class="text-xs text-muted-foreground">Width</label>
              <Input
                v-model.number="form.width"
                type="number"
                :min="64"
                :max="2048"
                @input="selectedRatio = 'custom'"
              />
            </div>
            <div class="space-y-1">
              <label class="text-xs text-muted-foreground">Height</label>
              <Input
                v-model.number="form.height"
                type="number"
                :min="64"
                :max="2048"
                @input="selectedRatio = 'custom'"
              />
            </div>
          </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-2">
            <label class="text-sm font-medium">Steps</label>
            <Input v-model.number="form.num_steps" type="number" :min="1" :max="100" />
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium">Seed</label>
            <Input v-model.number="form.seed" type="number" :min="-1" />
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" @click="open = false">Cancel</Button>
          <Button type="submit" :disabled="submitting || !form.prompt.trim()">
            <Sparkles class="mr-2 h-4 w-4" />
            {{ submitting ? 'Generating...' : 'Generate' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
