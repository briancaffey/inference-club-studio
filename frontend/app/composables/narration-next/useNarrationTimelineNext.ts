import { computed, ref, watch, type Ref } from 'vue'
import type { NarrationSegment, NarrationTranscription } from '~/types'
import { formatDuration, segmentDurationSeconds } from './narrationWorkspaceUtils'

interface UseNarrationTimelineOptions {
  segments: Ref<NarrationSegment[]>
  transcriptions: Record<number, NarrationTranscription>
  playbackSpeed: Ref<number>
  segmentAudioUrl: (segment: NarrationSegment) => string
}

function hasTimelineAudio(segment: NarrationSegment) {
  return segment.status === 'done' && (!!segment.audio_path || !!segment.studio_voice_audio_path)
}

export function useNarrationTimelineNext(options: UseNarrationTimelineOptions) {
  const timelineAudioPlayer = ref<HTMLAudioElement | null>(null)
  const timelinePlayingIdx = ref(-1)
  const timelineCurrentTime = ref(0)
  const timelineIsPlaying = ref(false)

  const timelineTotalSeconds = computed(() => {
    return options.segments.value.reduce((sum, segment) => sum + segmentDurationSeconds(segment), 0)
  })

  const timelineOffsets = computed(() => {
    const offsets: number[] = []
    let cursor = 0
    for (const segment of options.segments.value) {
      offsets.push(cursor)
      cursor += segmentDurationSeconds(segment)
    }
    return offsets
  })

  const timelineWidths = computed(() => {
    const total = timelineTotalSeconds.value
    if (!total) {
      return options.segments.value.map(() => 100 / Math.max(1, options.segments.value.length))
    }
    return options.segments.value.map(segment => ((segmentDurationSeconds(segment) / total) * 100))
  })

  const timelineCursorPercent = computed(() => {
    if (timelinePlayingIdx.value < 0 || !timelineTotalSeconds.value) return 0
    const offset = timelineOffsets.value[timelinePlayingIdx.value] || 0
    const total = offset + timelineCurrentTime.value
    return Math.max(0, Math.min(100, (total / timelineTotalSeconds.value) * 100))
  })

  const timelineHasDoneSegments = computed(() => {
    return options.segments.value.some(segment => hasTimelineAudio(segment))
  })

  async function playTimelineSegment(startIndex: number, startAtSeconds = 0) {
    const player = timelineAudioPlayer.value
    if (!player) return

    for (let index = startIndex; index < options.segments.value.length; index += 1) {
      const segment = options.segments.value[index]
      if (!hasTimelineAudio(segment)) continue

      timelinePlayingIdx.value = index
      timelineCurrentTime.value = startAtSeconds
      timelineIsPlaying.value = true

      const sourceUrl = options.segmentAudioUrl(segment)
      if (player.src !== sourceUrl) {
        player.src = sourceUrl
      }

      player.playbackRate = options.playbackSpeed.value

      if (startAtSeconds > 0) {
        const seekOnReady = () => {
          player.currentTime = Math.max(0, startAtSeconds)
        }
        player.addEventListener('loadedmetadata', seekOnReady, { once: true })
      }

      try {
        await player.play()
      } catch {
        timelineIsPlaying.value = false
      }
      return
    }

    stopTimelinePlayback()
  }

  function startTimelinePlayback(startIndex = 0) {
    void playTimelineSegment(startIndex)
  }

  function stopTimelinePlayback() {
    const player = timelineAudioPlayer.value
    if (player) {
      player.pause()
      player.removeAttribute('src')
      player.load()
    }
    timelinePlayingIdx.value = -1
    timelineCurrentTime.value = 0
    timelineIsPlaying.value = false
  }

  function toggleTimelinePlayPause() {
    const player = timelineAudioPlayer.value
    if (!player) return

    if (timelineIsPlaying.value) {
      player.pause()
      timelineIsPlaying.value = false
      return
    }

    if (timelinePlayingIdx.value >= 0) {
      player.playbackRate = options.playbackSpeed.value
      player.play().then(() => {
        timelineIsPlaying.value = true
      }).catch(() => {
        timelineIsPlaying.value = false
      })
      return
    }

    startTimelinePlayback(0)
  }

  function timelineClickSegment(index: number) {
    startTimelinePlayback(index)
  }

  function onTimelineAudioEnded() {
    if (timelinePlayingIdx.value < 0) return
    void playTimelineSegment(timelinePlayingIdx.value + 1)
  }

  function onTimelineTimeUpdate() {
    const player = timelineAudioPlayer.value
    if (!player) return
    timelineCurrentTime.value = player.currentTime
  }

  function seekToWord(segmentId: number, startSeconds: number) {
    const segmentIndex = options.segments.value.findIndex(segment => segment.id === segmentId)
    if (segmentIndex < 0) return

    const player = timelineAudioPlayer.value
    if (!player) return

    if (timelinePlayingIdx.value !== segmentIndex) {
      void playTimelineSegment(segmentIndex, startSeconds)
      return
    }

    player.currentTime = startSeconds
    timelineCurrentTime.value = startSeconds

    if (!timelineIsPlaying.value) {
      player.play().then(() => {
        timelineIsPlaying.value = true
      }).catch(() => {
        timelineIsPlaying.value = false
      })
    }
  }

  function getActiveWordIdx(segmentId: number) {
    const segmentIndex = options.segments.value.findIndex(segment => segment.id === segmentId)
    if (segmentIndex < 0 || timelinePlayingIdx.value !== segmentIndex) return -1

    const transcription = options.transcriptions[segmentId]
    if (!transcription?.words?.length) return -1

    return transcription.words.findIndex(word => (
      timelineCurrentTime.value >= word.start
      && timelineCurrentTime.value <= word.end
    ))
  }

  watch(
    () => options.playbackSpeed.value,
    speed => {
      const player = timelineAudioPlayer.value
      if (!player) return
      player.playbackRate = speed
    },
  )

  watch(
    () => options.segments.value.map(segment => `${segment.id}:${segment.status}`).join('|'),
    () => {
      if (timelinePlayingIdx.value >= options.segments.value.length) {
        stopTimelinePlayback()
      }
    },
  )

  return {
    timelineAudioPlayer,
    timelinePlayingIdx,
    timelineCurrentTime,
    timelineIsPlaying,

    timelineTotalSeconds,
    timelineOffsets,
    timelineWidths,
    timelineCursorPercent,
    timelineHasDoneSegments,

    startTimelinePlayback,
    stopTimelinePlayback,
    toggleTimelinePlayPause,
    timelineClickSegment,
    onTimelineAudioEnded,
    onTimelineTimeUpdate,
    seekToWord,
    getActiveWordIdx,

    formatDuration,
  }
}
