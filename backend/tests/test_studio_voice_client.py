from app.clients.studio_voice.client import StudioVoiceClient


def test_grpc_targets_prefers_explicit_target():
    client = StudioVoiceClient(
        url="http://192.168.6.3:8000",
        health_url="http://192.168.6.3:8000/v1/health/ready",
        grpc_target="192.168.5.173:9001",
    )

    targets = client._grpc_targets()

    assert targets[0] == "192.168.5.173:9001"
    assert "192.168.5.173:8001" in targets
    assert "192.168.5.173:8000" in targets


def test_grpc_targets_default_to_8001_for_http_api_url():
    client = StudioVoiceClient(
        url="http://192.168.6.3:8000",
        health_url="http://192.168.6.3:8000/v1/health/ready",
        grpc_target=None,
    )

    targets = client._grpc_targets()

    assert targets[0] == "192.168.5.173:8001"
    assert targets[1] == "192.168.5.173:8000"


def test_serialize_deserialize_chunk_round_trip():
    chunk = b"studio-voice-audio-chunk"

    encoded = StudioVoiceClient._serialize_request_chunk(chunk)
    decoded = StudioVoiceClient._deserialize_response_chunk(encoded)

    assert decoded == chunk
