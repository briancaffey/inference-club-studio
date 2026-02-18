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

export type GenerationStatus =
  | 'pending'
  | 'extracting_frame'
  | 'uploading_reference'
  | 'generating'
  | 'downloading'
  | 'completed'
  | 'error'

export interface Generation {
  id: string
  cut_id: string
  prompt: string
  width: number
  height: number
  num_steps: number
  cfg_scale: number
  seed: number
  invokeai_reference_image_name: string | null
  invokeai_generated_image_name: string | null
  actual_seed: number | null
  reference_frame_path: string | null
  output_image_path: string | null
  status: GenerationStatus
  error_message: string | null
  created_at: string
  updated_at: string
}

export type TakeStatus =
  | 'pending'
  | 'uploading_assets'
  | 'generating'
  | 'downloading'
  | 'encoding_canny'
  | 'completed'
  | 'error'

export interface Take {
  id: string
  generation_id: string
  prompt: string
  width: number
  height: number
  frame_count: number
  seed: number
  comfyui_prompt_id: string | null
  actual_seed: number | null
  output_video_path: string | null
  canny_video_path: string | null
  status: TakeStatus
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
