<script setup lang="ts">
import { Plus } from 'lucide-vue-next'

const store = useProjectsStore()

const open = ref(false)
const name = ref('')
const description = ref('')
const projectType = ref<'video_to_video' | 'narration'>('video_to_video')
const submitting = ref(false)

async function handleSubmit() {
  if (!name.value.trim()) return
  submitting.value = true
  try {
    await store.createProject(
      name.value.trim(),
      description.value.trim() || undefined,
      projectType.value,
    )
    open.value = false
    name.value = ''
    description.value = ''
    projectType.value = 'video_to_video'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogTrigger as-child>
      <Button>
        <Plus class="mr-2 h-4 w-4" />
        New Project
      </Button>
    </DialogTrigger>
    <DialogContent class="sm:max-w-[425px]">
      <DialogHeader>
        <DialogTitle>Create Project</DialogTitle>
        <DialogDescription>
          Create a project for narration or video-to-video workflows.
        </DialogDescription>
      </DialogHeader>
      <form @submit.prevent="handleSubmit" class="space-y-4">
        <div class="space-y-2">
          <Label for="name">Name</Label>
          <Input
            id="name"
            v-model="name"
            placeholder="My Film Project"
            required
          />
        </div>
        <div class="space-y-2">
          <Label for="projectType">Type</Label>
          <select
            id="projectType"
            v-model="projectType"
            class="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          >
            <option value="video_to_video">Video-to-video</option>
            <option value="narration">Narration</option>
          </select>
        </div>
        <div class="space-y-2">
          <Label for="description">Description</Label>
          <Textarea
            id="description"
            v-model="description"
            placeholder="Optional description..."
            :rows="3"
          />
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="!name.trim() || submitting">
            {{ submitting ? 'Creating...' : 'Create' }}
          </Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>
</template>
