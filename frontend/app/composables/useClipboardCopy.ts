export function useClipboardCopy() {
  const copied = ref(false)
  const copyError = ref<string | null>(null)

  async function copy(text: string | null | undefined) {
    if (!text) return false
    copyError.value = null
    try {
      await navigator.clipboard.writeText(text)
      copied.value = true
      setTimeout(() => { copied.value = false }, 1500)
      return true
    } catch (e: any) {
      copyError.value = e?.message || 'Failed to copy text'
      return false
    }
  }

  return {
    copied,
    copyError,
    copy,
  }
}
