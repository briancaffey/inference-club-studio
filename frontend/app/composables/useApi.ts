export function useApi() {
  const config = useRuntimeConfig()
  const baseURL = config.public.apiBase as string

  return {
    baseURL,
    mediaUrl(path: string | null): string | null {
      if (!path) return null
      // Convert absolute container paths to relative URLs
      // e.g., /app/media/xxx/thumbnails/yyy.jpg → /media/xxx/thumbnails/yyy.jpg
      const relativePath = path.replace(/^\/app\/media\//, '/media/')
      return `${baseURL}${relativePath}`
    },
  }
}
