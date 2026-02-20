from app.services.narration.dia import _ensure_s1_header


def test_ensure_s1_header_adds_missing_header():
    assert _ensure_s1_header("hello world") == "[S1] hello world"


def test_ensure_s1_header_keeps_existing_s1_header():
    assert _ensure_s1_header("[S1] already tagged") == "[S1] already tagged"


def test_ensure_s1_header_is_case_insensitive_for_s1():
    assert _ensure_s1_header("[s1] lowercase tag") == "[s1] lowercase tag"


def test_ensure_s1_header_rewrites_other_speaker_to_s1():
    assert _ensure_s1_header("[S2] different speaker") == "[S1] different speaker"


def test_ensure_s1_header_handles_empty_text():
    assert _ensure_s1_header("") == "[S1]"
    assert _ensure_s1_header(None) == "[S1]"
