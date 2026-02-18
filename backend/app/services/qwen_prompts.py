from dataclasses import dataclass

from app.models.cut import Cut


@dataclass(frozen=True)
class PromptProfile:
    key: str
    temperature: float
    top_p: float
    max_tokens: int


CLIP_OVERVIEW_PROFILE = PromptProfile(
    key="clip_overview_v1",
    temperature=0.2,
    top_p=0.8,
    max_tokens=900,
)

FIRST_FRAME_PROFILE = PromptProfile(
    key="first_frame_description_v1",
    temperature=0.2,
    top_p=0.8,
    max_tokens=700,
)

FLUX_STYLE_CONTENT_PROFILE = PromptProfile(
    key="flux_style_content_prompt_v1",
    temperature=0.4,
    top_p=0.8,
    max_tokens=500,
)


def build_clip_overview_prompt(cut: Cut) -> str:
    duration = f"{cut.duration:.2f}s" if cut.duration is not None else "unknown"
    resolution = (
        f"{cut.width}x{cut.height}"
        if cut.width is not None and cut.height is not None
        else "unknown"
    )
    fps = f"{cut.fps:.3f}" if cut.fps is not None else "unknown"

    return (
        "You are analyzing a video clip for downstream text-to-video prompt writing.\n"
        "Provide a concise but detailed overview of the entire clip.\n"
        "Focus on what matters for generative restyling and motion preservation.\n\n"
        f"Known metadata:\n"
        f"- filename: {cut.original_filename}\n"
        f"- duration: {duration}\n"
        f"- resolution: {resolution}\n"
        f"- fps: {fps}\n\n"
        "Output format:\n"
        "1) One paragraph summary (max 120 words).\n"
        "2) Bullet list with these labels:\n"
        "- Setting\n"
        "- Subjects\n"
        "- Key Actions/Events (chronological)\n"
        "- Camera Movement\n"
        "- Composition and Framing\n"
        "- Lighting/Color/Mood\n"
        "- Notable Objects/Props\n"
        "Keep it factual and avoid speculation."
    )


def build_first_frame_prompt(cut: Cut) -> str:
    resolution = (
        f"{cut.width}x{cut.height}"
        if cut.width is not None and cut.height is not None
        else "unknown"
    )
    return (
        "Describe only the FIRST FRAME of this clip in rich visual detail.\n"
        "This description will be used to write style-transfer prompts "
        "for Flux 2 Klein.\n"
        "Do not describe motion over time.\n\n"
        f"Known metadata:\n"
        f"- filename: {cut.original_filename}\n"
        f"- resolution: {resolution}\n\n"
        "Output format:\n"
        "1) One compact paragraph (max 110 words).\n"
        "2) Bullet list with labels:\n"
        "- Subjects and Pose\n"
        "- Environment/Background\n"
        "- Camera Angle and Lens Feel\n"
        "- Framing/Depth\n"
        "- Lighting\n"
        "- Color Palette\n"
        "- Texture/Material Details\n"
        "Stay concrete and visual."
    )


def build_flux_style_content_prompt(
    *,
    style: str,
    content: str,
    clip_overview: str | None = None,
    first_frame_description: str | None = None,
) -> str:
    clip_context = clip_overview or "N/A"
    frame_context = first_frame_description or "N/A"

    return (
        "Write a single production-ready prompt for Flux image generation.\n"
        "Goal: preserve content while applying the requested style.\n"
        "Output only the final prompt text. No commentary, no markdown.\n\n"
        f"Style instruction:\n{style}\n\n"
        f"Content instruction:\n{content}\n\n"
        f"Clip context (optional):\n{clip_context}\n\n"
        f"First-frame context (optional):\n{frame_context}\n\n"
        "Requirements for the final prompt:\n"
        "- Must include subject, setting, composition, lighting, palette, and mood.\n"
        "- Must preserve core scene content while translating style.\n"
        "- Avoid camera-motion language that implies video.\n"
        "- Keep it between 60 and 120 words."
    )
