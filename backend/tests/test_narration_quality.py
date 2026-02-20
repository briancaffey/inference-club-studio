from app.services.narration.quality import (
    _fallback_quality_result,
    _parse_quality_response,
)


def test_parse_quality_response_supports_json_code_fence():
    payload = (
        "```json\n"
        '{"score": 8.7, "should_regenerate": false, '
        '"reason": "Minor punctuation only"}\n'
        "```"
    )
    result = _parse_quality_response(payload)
    assert result.score == 8.7
    assert result.should_regenerate is False
    assert "Minor punctuation" in result.reason


def test_parse_quality_response_clamps_score_and_defaults_reason():
    result = _parse_quality_response(
        '{"score": 42, "should_regenerate": true, "reason": ""}'
    )
    assert result.score == 10.0
    assert result.should_regenerate is True
    assert result.reason == "No reason provided"


def test_fallback_quality_result_sets_regenerate_for_low_similarity():
    result = _fallback_quality_result(
        original_text="The quick brown fox jumps over the lazy dog.",
        transcription_text="Completely unrelated sentence",
    )
    assert result.score < 8.0
    assert result.should_regenerate is True
