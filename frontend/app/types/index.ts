export type CutStatus =
  | 'uploaded'
  | 'processing_metadata'
  | 'extracting_audio'
  | 'ready'
  | 'error'

export interface Cut {
  id: string
  project_id: string
  order: number
  original_filename: string
  file_path: string
  file_size: number | null
  duration: number | null
  fps: number | null
  width: number | null
  height: number | null
  aspect_ratio: string | null
  codec: string | null
  audio_codec: string | null
  thumbnail_path: string | null
  audio_path: string | null
  status: CutStatus
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface Project {
  id: string
  name: string
  description: string | null
  cut_count?: number
  metadata?: Record<string, unknown> | null
  cuts?: Cut[]
  created_at: string
  updated_at: string
}
