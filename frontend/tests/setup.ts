import { config } from '@vue/test-utils'
import { vi } from 'vitest'

config.global.stubs = {
  NuxtLink: {
    template: '<a><slot /></a>',
  },
}

if (!globalThis.confirm) {
  globalThis.confirm = () => true
}

if (typeof HTMLMediaElement !== 'undefined') {
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined)
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
}
