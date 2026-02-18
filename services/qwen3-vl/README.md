# Qwen3-VL on vLLM (RTX 4090, 24GB VRAM)

Serve Qwen3-VL-4B-Instruct locally via vLLM, exposing an OpenAI-compatible API.

## Hardware

- GPU: NVIDIA RTX 4090 (24GB VRAM)
- OS: Linux
- CUDA: 12.x recommended
- NVIDIA driver: 535+ recommended

## Model

### Qwen3-VL-4B-Instruct

- **HuggingFace:** <https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct>
- 4B parameters, BF16
- ~8GB model weights — comfortably fits on 24GB with room for longer contexts
- Native 256K context (expandable to 1M)
- Vision capabilities: image understanding, video understanding, OCR (32 languages), spatial reasoning

## Setup

### 1. Create a Python environment

```bash
uv venv
source .venv/bin/activate
```

### 2. Install vLLM and dependencies

```bash
uv pip install -U vllm
uv pip install qwen-vl-utils==0.0.14
```

Requires vLLM >= 0.11.0.

## Serving the Model

```bash
vllm serve Qwen/Qwen3-VL-4B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --trust-remote-code
```

**Notes on these flags:**

- `--gpu-memory-utilization 0.90` — Uses 90% of VRAM (~21.6GB). The 4B model leaves plenty of headroom.
- `--max-model-len 32768` — Generous context window. Can be increased further if needed since the model is small.
- `--trust-remote-code` — Required for Qwen3-VL model code.

## Running with Docker

Using Docker avoids installing vLLM, CUDA libraries, and Python dependencies on the host. The official image `vllm/vllm-openai` comes with everything pre-installed.

### Prerequisites

- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed and configured
- Docker Engine with GPU support (`docker run --gpus all nvidia/cuda:12.8.0-base-ubuntu24.04 nvidia-smi` should work)

### Run interactively

```bash
docker run --rm \
  --gpus all \
  --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  vllm/vllm-openai:v0.15.1 \
  --model Qwen/Qwen3-VL-4B-Instruct \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --trust-remote-code
```

With HuggingFace cache on a separate drive (e.g. WSL2 with D: mount):

```bash
docker run --rm \
  --gpus all \
  --ipc=host \
  -v /mnt/d/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  vllm/vllm-openai:v0.15.1 \
  --model Qwen/Qwen3-VL-4B-Instruct \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --trust-remote-code
```

### Run in the background

```bash
docker run -d \
  --name qwen3-vl \
  --gpus all \
  --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  vllm/vllm-openai:v0.15.1 \
  --model Qwen/Qwen3-VL-4B-Instruct \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768 \
  --trust-remote-code
```

Then manage with:

```bash
docker logs -f qwen3-vl    # Follow logs (watch for "Uvicorn running on ...")
docker stop qwen3-vl       # Stop the server
docker start qwen3-vl      # Restart it
docker rm qwen3-vl         # Remove the container
```

### Docker flags explained

| Flag | Purpose |
|------|---------|
| `--gpus all` | Exposes the GPU(s) to the container |
| `--ipc=host` | Shares host shared memory with the container. Required because PyTorch uses shared memory for inter-process tensor operations. Without this you'll get crashes or hangs. |
| `-v ~/.cache/huggingface:/root/.cache/huggingface` | Mounts the HuggingFace cache so model downloads persist across container restarts. Without this, the model re-downloads every time. |
| `-p 8000:8000` | Maps the vLLM server port to your host |
| `--rm` | Auto-removes the container on exit (optional, drop if you want to inspect logs after stopping) |

### Checking available vLLM versions

All commands above pin to `v0.15.1`. To check for newer versions:

```bash
# Browse tags at https://hub.docker.com/r/vllm/vllm-openai/tags
# Or pull a different version:
docker pull vllm/vllm-openai:v0.16.0
```

Qwen3-VL requires **vLLM >= 0.11.0** and **Transformers >= 4.57.0**. Do not use versions older than v0.11.0.

### Private/gated models

If the model requires HuggingFace authentication, pass your token:

```bash
docker run --rm --gpus all --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -e HUGGING_FACE_HUB_TOKEN=hf_your_token_here \
  -p 8000:8000 \
  vllm/vllm-openai:v0.15.1 \
  --model Qwen/Qwen3-VL-4B-Instruct \
  --trust-remote-code \
  --gpu-memory-utilization 0.90 \
  --max-model-len 32768
```

## Testing the Server

Once the server is running, verify it with curl:

```bash
# List available models
curl http://localhost:8000/v1/models

# Text-only request
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-VL-4B-Instruct",
    "messages": [
      {"role": "user", "content": "Hello, what can you do?"}
    ],
    "max_tokens": 256
  }'

# Image request (URL)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-VL-4B-Instruct",
    "messages": [
      {
        "role": "user",
        "content": [
          {"type": "image_url", "image_url": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png"}},
          {"type": "text", "text": "Describe this image."}
        ]
      }
    ],
    "max_tokens": 512
  }'
```

## Python Client Example

```python
from openai import OpenAI

client = OpenAI(
    api_key="not-needed",
    base_url="http://localhost:8000/v1",
)

# Text-only
response = client.chat.completions.create(
    model="Qwen/Qwen3-VL-4B-Instruct",
    messages=[{"role": "user", "content": "Describe what you can do."}],
    max_tokens=256,
)
print(response.choices[0].message.content)

# With image
response = client.chat.completions.create(
    model="Qwen/Qwen3-VL-4B-Instruct",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "https://example.com/photo.jpg"},
                },
                {"type": "text", "text": "What do you see in this image?"},
            ],
        }
    ],
    max_tokens=512,
)
print(response.choices[0].message.content)
```

## Recommended Generation Parameters

```
temperature=0.7
top_p=0.8
top_k=20
repetition_penalty=1.0
presence_penalty=1.5
max_tokens=16384
```

## Troubleshooting

### "does not recognize this architecture" / `qwen3_vl` not found

```
ValueError: The checkpoint you are trying to load has model type `qwen3_vl`
but Transformers does not recognize this architecture.
```

This means your vLLM image bundles a Transformers version older than 4.57.0. Fix: use a vLLM image **>= v0.11.0** (we pin `v0.15.1` above). Do **not** use `vllm/vllm-openai:latest` — the `latest` tag may lag behind actual releases.

### Slow first request

The first request is slow because vLLM warms up the model and (if not using `--enforce-eager`) captures CUDA graphs. Subsequent requests will be faster.

### Model download

Models are downloaded from HuggingFace on first run. Make sure you have enough disk space and a stable connection. Downloads are cached in `~/.cache/huggingface/`.

## References

- [vLLM Qwen3-VL Recipe](https://docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-VL.html)
- [Qwen3-VL-4B-Instruct on HuggingFace](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct)
- [vLLM Documentation](https://docs.vllm.ai/)
