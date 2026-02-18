# Frontend — Nuxt 4 + shadcn/ui

## Stack
- **Nuxt 4** (app/ directory structure), **Vue 3** with `<script setup lang="ts">`
- **Tailwind CSS v4** via `@tailwindcss/vite`
- **shadcn-vue** — all components pre-installed in `app/components/ui/`
- **Pinia** for state management (`app/stores/`)
- **@nuxtjs/color-mode** for light/dark/system theme
- **lucide-vue-next** for icons

## Directory Structure
```
app/
  assets/css/main.css   # Tailwind + shadcn CSS variables
  components/           # App-level components
  components/ui/        # shadcn/ui components (auto-imported, don't edit)
  composables/          # Auto-imported composables (useXxx pattern)
  layouts/              # Layout components (default.vue has nav + theme picker)
  lib/utils.ts          # cn() helper for Tailwind class merging
  pages/                # File-based routing
  stores/               # Pinia stores (useXxxStore pattern)
```

## Conventions
- Use `<script setup lang="ts">` for all components
- shadcn/ui components are auto-imported — use directly in templates (e.g. `<Button>`, `<Card>`)
- Icons: `import { IconName } from 'lucide-vue-next'`
- Composables go in `app/composables/`, auto-imported with `useXxx` naming
- Pinia stores go in `app/stores/`, use `defineStore` with setup syntax
- Theme: dark mode uses `.dark` class on `<html>`. Use `useColorMode()` to read/set
- Style with Tailwind utility classes. Use `cn()` from `@/lib/utils` for conditional classes
- Prefer `useFetch`/`useAsyncData` for data fetching, not raw `fetch`

## Adding shadcn/ui Components
All components are already installed. If a new one is released:
```bash
npx shadcn-vue@latest add <component-name>
```

## Dev Commands
```bash
yarn dev      # Start dev server
yarn build    # Production build
```
