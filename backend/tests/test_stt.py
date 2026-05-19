from app.services.narration.stt import (
    _normalize_openai_base_url,
    _parse_word_list,
    _synthesize_word_timestamps,
)


def test_normalize_base_url_appends_v1_when_missing():
    assert _normalize_openai_base_url("http://host:8000") == "http://host:8000/v1"


def test_normalize_base_url_keeps_v1_when_present():
    assert _normalize_openai_base_url("http://host:8000/v1") == "http://host:8000/v1"


def test_normalize_base_url_strips_trailing_slash():
    assert _normalize_openai_base_url("http://host:8000/v1/") == "http://host:8000/v1"
    assert _normalize_openai_base_url("http://host:8000/") == "http://host:8000/v1"


def test_normalize_base_url_empty_passthrough():
    assert _normalize_openai_base_url("") == ""
    assert _normalize_openai_base_url("   ") == ""


def test_synthesize_word_timestamps_uniform_distribution():
    words = _synthesize_word_timestamps("hello world foo bar", duration=4.0)
    assert len(words) == 4
    assert words[0] == {"word": "hello", "start": 0.0, "end": 1.0}
    assert words[-1] == {"word": "bar", "start": 3.0, "end": 4.0}


def test_synthesize_word_timestamps_empty_inputs():
    assert _synthesize_word_timestamps("", duration=5.0) == []
    assert _synthesize_word_timestamps("hi there", duration=0.0) == []
    assert _synthesize_word_timestamps("hi there", duration=-1.0) == []


def test_parse_word_list_normalizes_openai_shape():
    raw = [
        {"word": "hi", "start": 0.0, "end": 0.5},
        {"text": "there", "start": "0.5", "end": "1.0"},
        "skip-me",
        {"word": "bad", "start": "nan-string", "end": 2.0},
        {"word": "ok", "start": 1.0, "end": 1.5},
    ]
    out = _parse_word_list(raw)
    assert out == [
        {"word": "hi", "start": 0.0, "end": 0.5},
        {"word": "there", "start": 0.5, "end": 1.0},
        {"word": "ok", "start": 1.0, "end": 1.5},
    ]


def test_parse_word_list_handles_non_list():
    assert _parse_word_list(None) == []
    assert _parse_word_list({}) == []
    assert _parse_word_list("not-a-list") == []
