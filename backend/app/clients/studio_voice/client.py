"""Client for NVIDIA Studio Voice enhancement service."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_GRPC_METHOD = "/nvidia.maxine.studiovoice.v1.MaxineStudioVoice/EnhanceAudio"
_GRPC_CHUNK_SIZE = 64 * 1024
_DEFAULT_GRPC_PORT = 8001


class StudioVoiceError(RuntimeError):
    """Raised when Studio Voice enhancement fails."""


class StudioVoiceClient:
    """Transactional Studio Voice client using gRPC audio inference."""

    def __init__(
        self,
        url: str | None = None,
        health_url: str | None = None,
        grpc_target: str | None = None,
        model_type: str | None = None,
        timeout: float = 120.0,
    ):
        self.url = (url or settings.studio_voice_url).rstrip("/")
        self.health_url = (health_url or settings.studio_voice_health_url).rstrip("/")
        configured_target = (
            grpc_target
            if grpc_target is not None
            else settings.studio_voice_grpc_target
        )
        self.grpc_target = (configured_target or "").strip()
        self.model_type = model_type or settings.studio_voice_model_type
        self.timeout = timeout

    async def check_health(self) -> bool:
        """Check if the Studio Voice health endpoint is reachable."""
        health_candidates = [
            self.health_url,
            f"{self.url}/v1/health/ready",
            f"{self.url}/v1/health/live",
            f"{self.url}/health",
            f"{self.url}/",
        ]
        tried: set[str] = set()

        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            for endpoint in health_candidates:
                if not endpoint or endpoint in tried:
                    continue
                tried.add(endpoint)

                try:
                    response = await client.get(endpoint)
                    if response.status_code < 400:
                        return True
                except Exception as exc:
                    logger.debug(
                        "Studio Voice health check failed for %s: %s",
                        endpoint,
                        exc,
                    )

        return False

    async def enhance_audio(
        self,
        audio_bytes: bytes,
        *,
        filename: str = "audio.wav",
    ) -> bytes:
        """Enhance WAV bytes via Studio Voice gRPC and return cleaned bytes."""

        if not audio_bytes:
            raise StudioVoiceError("No audio bytes were provided")

        errors: list[str] = []
        for target in self._grpc_targets():
            try:
                return await asyncio.to_thread(
                    self._enhance_audio_via_grpc,
                    target,
                    audio_bytes,
                )
            except Exception as exc:
                logger.debug(
                    "Studio Voice gRPC enhancement failed for %s: %s",
                    target,
                    exc,
                )
                errors.append(f"{target}: {exc}")

        if not errors:
            raise StudioVoiceError("No Studio Voice gRPC targets were configured")
        raise StudioVoiceError(
            "Studio Voice enhancement failed: " + " ; ".join(errors[:4])
        )

    def _enhance_audio_via_grpc(self, target: str, audio_bytes: bytes) -> bytes:
        grpc = self._load_grpc_module()
        timeout: float | None = self.timeout if self.timeout > 0 else None

        try:
            with grpc.insecure_channel(target) as channel:
                enhance_audio = channel.stream_stream(
                    _GRPC_METHOD,
                    request_serializer=self._serialize_request_chunk,
                    response_deserializer=self._deserialize_response_chunk,
                )
                responses = enhance_audio(
                    self._request_chunks(audio_bytes),
                    timeout=timeout,
                )

                output = bytearray()
                for chunk in responses:
                    if chunk:
                        output.extend(chunk)
        except Exception as exc:
            raise StudioVoiceError(f"gRPC request failed: {exc}") from exc

        if not output:
            raise StudioVoiceError("gRPC response did not include audio bytes")
        return bytes(output)

    def _grpc_targets(self) -> list[str]:
        candidates: list[str] = []
        if self.grpc_target:
            normalized = self._normalize_target(self.grpc_target)
            if normalized:
                candidates.append(normalized)

        candidates.extend(self._targets_from_url(self.url))
        candidates.extend(self._targets_from_url(self.health_url))

        seen: set[str] = set()
        targets: list[str] = []
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            targets.append(candidate)
        return targets

    def _targets_from_url(self, endpoint: str) -> list[str]:
        parsed = urlparse(endpoint if "://" in endpoint else f"http://{endpoint}")
        host = parsed.hostname
        if not host:
            return []

        port = parsed.port
        ports: list[int] = []

        if port in (None, 8000):
            ports.append(_DEFAULT_GRPC_PORT)
        if port is not None:
            ports.append(port)
        if _DEFAULT_GRPC_PORT not in ports:
            ports.append(_DEFAULT_GRPC_PORT)

        return [f"{host}:{candidate_port}" for candidate_port in ports]

    def _normalize_target(self, target: str) -> str:
        candidate = (target or "").strip()
        if not candidate:
            return ""

        if "://" in candidate:
            parsed = urlparse(candidate)
            if not parsed.hostname:
                return ""
            port = parsed.port or _DEFAULT_GRPC_PORT
            return f"{parsed.hostname}:{port}"

        candidate = candidate.split("/", maxsplit=1)[0].strip()
        if ":" in candidate:
            return candidate
        return f"{candidate}:{_DEFAULT_GRPC_PORT}" if candidate else ""

    def _request_chunks(self, audio_bytes: bytes):
        for index in range(0, len(audio_bytes), _GRPC_CHUNK_SIZE):
            yield audio_bytes[index : index + _GRPC_CHUNK_SIZE]

    @staticmethod
    def _serialize_request_chunk(chunk: bytes) -> bytes:
        payload = chunk if isinstance(chunk, (bytes, bytearray)) else bytes(chunk)
        return b"\x0a" + StudioVoiceClient._encode_varint(len(payload)) + payload

    @staticmethod
    def _deserialize_response_chunk(message_bytes: bytes) -> bytes:
        data = (
            message_bytes if isinstance(message_bytes, bytes) else bytes(message_bytes)
        )
        position = 0

        while position < len(data):
            key, position = StudioVoiceClient._decode_varint(data, position)
            field_number = key >> 3
            wire_type = key & 0x07

            if wire_type == 2:
                length, position = StudioVoiceClient._decode_varint(data, position)
                end = position + length
                if end > len(data):
                    raise StudioVoiceError("Malformed gRPC response chunk")
                value = data[position:end]
                position = end
                if field_number == 1:
                    return value
                continue

            position = StudioVoiceClient._skip_unknown_field(data, position, wire_type)

        return b""

    @staticmethod
    def _skip_unknown_field(data: bytes, position: int, wire_type: int) -> int:
        if wire_type == 0:
            _, next_position = StudioVoiceClient._decode_varint(data, position)
            return next_position
        if wire_type == 1:
            next_position = position + 8
            if next_position > len(data):
                raise StudioVoiceError("Malformed gRPC response chunk")
            return next_position
        if wire_type == 5:
            next_position = position + 4
            if next_position > len(data):
                raise StudioVoiceError("Malformed gRPC response chunk")
            return next_position
        raise StudioVoiceError(f"Unsupported protobuf wire type: {wire_type}")

    @staticmethod
    def _encode_varint(value: int) -> bytes:
        if value < 0:
            raise StudioVoiceError("Invalid negative varint value")

        encoded = bytearray()
        while True:
            to_write = value & 0x7F
            value >>= 7
            if value:
                encoded.append(to_write | 0x80)
            else:
                encoded.append(to_write)
                break
        return bytes(encoded)

    @staticmethod
    def _decode_varint(data: bytes, position: int) -> tuple[int, int]:
        value = 0
        shift = 0

        while position < len(data):
            byte = data[position]
            position += 1
            value |= (byte & 0x7F) << shift
            if not (byte & 0x80):
                return value, position
            shift += 7
            if shift > 63:
                raise StudioVoiceError("Malformed varint in gRPC payload")

        raise StudioVoiceError("Unexpected end of gRPC payload")

    @staticmethod
    def _load_grpc_module():
        try:
            import grpc  # type: ignore

            return grpc
        except ImportError as exc:
            raise StudioVoiceError(
                "grpcio is required for Studio Voice inference. "
                "Install backend dependencies and rebuild the API/worker images."
            ) from exc
