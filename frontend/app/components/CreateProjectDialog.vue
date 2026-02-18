<script setup lang="ts">
import { Plus } from 'lucide-vue-next'

const store = useProjectsStore()

const open = ref(false)
const name = ref('')
const description = ref('')
const submitting = ref(false)

async function handleSubmit() {
  if (!name.value.trim()) return
  submitting.value = true
  try {
    await store.createProject(name.value.trim(), description.value.trim() || undefined)
    open.value = false
    name.value = ''
    description.value = ''
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
          Create a new project to organize your video cuts.
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
