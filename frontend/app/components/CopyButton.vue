<script setup lang="ts">
import { Check, Copy } from 'lucide-vue-next'

const props = withDefaults(defineProps<{
  text: string | null | undefined
  tooltip?: string
  copiedTooltip?: string
  size?: 'default' | 'sm' | 'lg' | 'icon'
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link'
  class?: string
}>(), {
  tooltip: 'Copy',
  copiedTooltip: 'Copied!',
  size: 'icon',
  variant: 'ghost',
  class: '',
})

const { copied, copy } = useClipboardCopy()

async function onCopy() {
  await copy(props.text)
}
</script>

<template>
  <TooltipProvider>
    <Tooltip>
      <TooltipTrigger as-child>
        <Button
          :variant="variant"
          :size="size"
          :class="class"
          :disabled="!text"
          @click="onCopy"
        >
          <Check v-if="copied" class="h-4 w-4 text-green-500" />
          <Copy v-else class="h-4 w-4" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        <p>{{ copied ? copiedTooltip : tooltip }}</p>
      </TooltipContent>
    </Tooltip>
  </TooltipProvider>
</template>
