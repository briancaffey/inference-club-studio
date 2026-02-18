<script setup lang="ts">
import { Settings, ExternalLink, Activity, CheckCircle, XCircle, Loader2 } from 'lucide-vue-next'

const config = useRuntimeConfig()

const { data: health, error, status, refresh } = useFetch<{ status: string }>(
  `${config.public.apiBase}/api/v1/health`,
  { server: false }
)
</script>

<template>
  <div>
    <PageHeader
      title="Admin"
      description="Manage your Inference Club Studio instance."
    />

    <div class="grid gap-6 sm:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Activity class="h-5 w-5" />
            API Status
          </CardTitle>
          <CardDescription>
            Backend health check.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div class="flex items-center gap-3">
            <template v-if="status === 'idle' || status === 'pending'">
              <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
              <span class="text-sm text-muted-foreground">Checking...</span>
            </template>
            <template v-else-if="!error && health?.status === 'ok'">
              <CheckCircle class="h-5 w-5 text-green-500" />
              <span class="text-sm text-green-600 dark:text-green-400">API is healthy</span>
            </template>
            <template v-else>
              <XCircle class="h-5 w-5 text-red-500" />
              <span class="text-sm text-red-600 dark:text-red-400">API unreachable</span>
            </template>
          </div>
        </CardContent>
        <CardFooter>
          <Button variant="outline" size="sm" @click="refresh()">
            Refresh
          </Button>
        </CardFooter>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <Settings class="h-5 w-5" />
            General Settings
          </CardTitle>
          <CardDescription>
            Configure your instance settings and preferences.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p class="text-sm text-muted-foreground">
            Settings panel coming soon. This is where you'll manage models, API keys, and instance configuration.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Quick Links</CardTitle>
          <CardDescription>
            Helpful resources and navigation.
          </CardDescription>
        </CardHeader>
        <CardContent class="flex flex-col gap-3">
          <Button variant="outline" as-child class="justify-start">
            <NuxtLink to="/about">
              <ExternalLink class="mr-2 h-4 w-4" />
              About Inference Club Studio
            </NuxtLink>
          </Button>
          <Button variant="outline" as-child class="justify-start">
            <a href="http://localhost:8000/docs" target="_blank">
              <ExternalLink class="mr-2 h-4 w-4" />
              API Documentation
            </a>
          </Button>
          <Button variant="outline" as-child class="justify-start">
            <a href="http://localhost:5555" target="_blank">
              <ExternalLink class="mr-2 h-4 w-4" />
              Flower (Celery Monitor)
            </a>
          </Button>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
