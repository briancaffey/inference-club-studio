export type CutStatus =
  | 'uploaded'
  | 'processing_metadata'
  | 'extracting_audio'
  | 'ready'
  | 'error'

export type CutAIStatus = 'pending' | 'queued' | 'running' | 'completed' | 'error'

export type CutAIAnalysisType =
  | 'clip_overview'
  | 'first_frame'
  | 'flux_style_content_prompt'

export interface CutAIRun {
  id: string
  cut_id: string
  analysis_type: CutAIAnalysisType | string
  status: CutAIStatus | string
  prompt_key: string
  prompt_input: Record<string, unknown> | null
  prompt_text: string
  response_text: string | null
  model_name: string
  prompt_tokens: number | null
  completion_tokens: number | null
  temperature: number | null
  max_tokens: number | null
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  updated_at: string
}

export interface CutAIState {
  id: string
  cut_id: string
  clip_overview_text: string | null
  first_frame_description_text: string | null
  first_frame_path: string | null
  clip_overview_status: CutAIStatus | string
  first_frame_status: CutAIStatus | string
  last_error_message: string | null
  clip_overview_run: CutAIRun | null
  first_frame_run: CutAIRun | null
  created_at: string
  updated_at: string
}

export interface FluxPromptDraftResponse {
  draft_id: string
  run: CutAIRun
  prompt_text: string
  created_at: string
}

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
  ai_state?: CutAIState | null
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

export type ProjectType = 'video_to_video' | 'narration'

export interface Project {
  id: string
  name: string
  project_type: ProjectType
  description: string | null
  cut_count?: number
  segment_count?: number
  metadata?: Record<string, unknown> | null
  cuts?: Cut[]
  created_at: string
  updated_at: string
}

export interface InferenceServiceHealth {
  key: string
  name: string
  url: string
  healthy: boolean
  error: string | null
}

export interface InferenceServicesHealthResponse {
  status: 'ok' | 'degraded'
  checked_at: string
  healthy_services: number
  total_services: number
  services: InferenceServiceHealth[]
}

export type NarrationService = 'dia' | 'magpie'
export type NarrationSegmentStatus = 'pending' | 'generating' | 'done' | 'error'

export interface NarrationSegment {
  id: number
  project_id: string
  position: number
  text: string
  sanitized_text: string
  service: NarrationService | string
  status: NarrationSegmentStatus | string
  audio_path: string | null
  duration_seconds: number | null
  error_message: string | null
  selected_variant_id: number | null
  voice_sample_id: number | null
  magpie_voice: string | null
  original_text: string | null
  created_at: string
  updated_at: string
}

export interface NarrationVariant {
  id: number
  segment_id: number
  text: string
  sanitized_text: string
  service: NarrationService | string
  audio_path: string | null
  duration_seconds: number | null
  created_at: string
}

export interface NarrationVoiceSample {
  id: number
  name: string
  audio_path: string
  transcript: string
  created_at: string
}

export interface NarrationWord {
  word: string
  start: number
  end: number
}

export interface NarrationTranscription {
  id: number
  segment_id: number
  text: string
  words: NarrationWord[]
  created_at: string
}
