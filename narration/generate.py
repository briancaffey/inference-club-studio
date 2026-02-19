#!/usr/bin/env python3
"""
Voice narration generator script.

Reads lines from a script file and generates individual audio files
using a text-to-speech service with voice cloning.
"""

import argparse
import json
import logging
import os
import re
import requests
import time

# Configuration
CONFIG = {
    "host": "localhost",
    "port": 7860,
}

# Reference voice sample files
REFERENCE_AUDIO = os.path.join("sample", "Alice.wav")
REFERENCE_TEXT_FILE = os.path.join("sample", "text.txt")

# Output directory
OUTPUT_DIR = "output"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def get_base_url():
    """Get the base URL for the API."""
    return f"http://{CONFIG['host']}:{CONFIG['port']}"


def sanitize_filename(text, max_words=5, max_length=50):
    """
    Create a sanitized filename from the first few words of text.

    Args:
        text: The text to create a filename from
        max_words: Maximum number of words to include
        max_length: Maximum length of the filename

    Returns:
        A sanitized filename string
    """
    # Remove speaker tags like [S1]
    clean_text = re.sub(r'\[S\d+\]\s*', '', text)

    # Get first few words
    words = clean_text.split()[:max_words]

    # Join and sanitize
    filename = "_".join(words)
    filename = re.sub(r'[^\w\s-]', '', filename)  # Remove special chars
    filename = re.sub(r'\s+', '_', filename)  # Replace spaces with underscores
    filename = filename.lower()

    # Truncate if too long
    if len(filename) > max_length:
        filename = filename[:max_length]

    return filename


def load_reference_text():
    """Load the reference text from the sample file."""
    with open(REFERENCE_TEXT_FILE, "r") as f:
        return f.read().strip()


def generate_audio_from_prompt(text, output_filename):
    """
    Generate audio from text using the voice cloning service.

    Args:
        text: The text to generate audio for
        output_filename: The filename for the output audio

    Returns:
        Path to the generated audio file, or None if failed
    """
    base_url = get_base_url()

    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    logging.info(f"Generating audio for: {text[:60]}...")

    # Load reference text (transcript of what's said in the reference audio)
    reference_text = load_reference_text()

    # Text to generate: the new content with [S2] at the end to avoid cutoff
    text_to_generate = f"{text}\n[S2]"

    logging.info(f"Reference text: {reference_text}")
    logging.info(f"Text to generate: {text_to_generate}")

    try:
        # Upload the reference audio file
        with open(REFERENCE_AUDIO, "rb") as audio_file:
            files = {
                'files': ('Alice.wav', audio_file, 'audio/wav')
            }
            upload_response = requests.post(
                f"{base_url}/gradio_api/upload",
                files=files
            )

            if upload_response.status_code != 200:
                logging.error(f"Failed to upload audio file. Status: {upload_response.status_code}")
                return None

            upload_data = upload_response.json()
            if not isinstance(upload_data, list) or len(upload_data) == 0:
                logging.error("Invalid response from upload endpoint")
                return None

            uploaded_file_path = upload_data[0]
            logging.info(f"Uploaded reference audio: {uploaded_file_path}")

    except Exception as e:
        logging.error(f"Failed to upload audio file: {e}")
        return None

    # Initiate audio generation
    try:
        response = requests.post(
            f"{base_url}/gradio_api/call/generate_audio",
            headers={"Content-Type": "application/json"},
            json={
                "data": [
                    text_to_generate,  # text_input - text to generate
                    reference_text,     # audio_prompt_text_input - transcript of reference audio
                    {
                        "path": uploaded_file_path,
                        "meta": {"_type": "gradio.FileData"}
                    },  # audio_prompt_input - reference audio file
                    3072,   # max_new_tokens
                    3.0,    # cfg_scale
                    1.3,    # temperature
                    0.95,   # top_p
                    30,     # cfg_filter_top_k
                    0.94,   # speed_factor
                    -1      # seed (-1 for random)
                ]
            }
        )

        response_data = response.json()
        logging.info(f"Initial response: {response_data}")

        if "event_id" not in response_data:
            logging.error(f"No event_id in response: {response_data}")
            return None

        event_id = response_data["event_id"]
        logging.info(f"Received event ID: {event_id}")

    except Exception as e:
        logging.error(f"Failed to initiate generation: {e}")
        return None

    # Get the generated audio (may take a while for generation)
    try:
        audio_response = requests.get(
            f"{base_url}/gradio_api/call/generate_audio/{event_id}",
            stream=True,
            timeout=300  # 5 minute timeout for long generations
        )

        if audio_response.status_code != 200:
            logging.error(f"Failed to get audio. Status: {audio_response.status_code}")
            return None

        # Process SSE response to find audio URL
        # The stream sends multiple events; we need to wait for the complete event
        audio_url = None
        all_events = []
        for line in audio_response.iter_lines():
            if line:
                line = line.decode('utf-8')
                all_events.append(line)
                logging.info(f"SSE: {line[:100]}")

                if line.startswith('data: '):
                    try:
                        data = json.loads(line[6:])
                        if isinstance(data, list) and len(data) > 0:
                            audio_data = data[0]
                            if isinstance(audio_data, dict) and 'url' in audio_data:
                                audio_url = audio_data['url']
                                logging.info(f"Found audio URL: {audio_url}")
                                break
                    except json.JSONDecodeError:
                        continue

        if not audio_url:
            logging.error("Could not find audio URL in response")
            logging.error(f"All events received: {all_events}")
            return None

        # Download the audio file
        logging.info(f"Downloading audio from: {audio_url}")
        audio_file_response = requests.get(audio_url)

        if audio_file_response.status_code != 200:
            logging.error(f"Failed to download audio. Status: {audio_file_response.status_code}")
            return None

        # Save the audio file
        output_path = os.path.join(OUTPUT_DIR, f"{output_filename}.wav")
        with open(output_path, "wb") as f:
            f.write(audio_file_response.content)

        file_size = os.path.getsize(output_path)
        logging.info(f"Saved: {output_path} ({file_size} bytes)")
        return output_path

    except Exception as e:
        logging.error(f"Failed to retrieve audio: {e}")
        return None


def process_script_file(script_path):
    """
    Process a script file and generate audio for each line.

    Args:
        script_path: Path to the script file
    """
    logging.info(f"Processing script file: {script_path}")

    with open(script_path, "r") as f:
        lines = [line.strip() for line in f if line.strip()]

    logging.info(f"Found {len(lines)} lines to process")

    for i, line in enumerate(lines, 1):
        # Create filename from line number and first few words
        sanitized = sanitize_filename(line)
        output_filename = f"{i:03d}_{sanitized}"

        logging.info(f"Processing line {i}/{len(lines)}")
        result = generate_audio_from_prompt(line, output_filename)

        if result:
            logging.info(f"Successfully generated: {result}")
        else:
            logging.error(f"Failed to generate audio for line {i}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate voice narration from a script file"
    )
    parser.add_argument(
        "script_file",
        help="Path to the script file containing lines to narrate"
    )
    parser.add_argument(
        "--host",
        default=CONFIG["host"],
        help=f"Hostname of the TTS service (default: {CONFIG['host']})"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=CONFIG["port"],
        help=f"Port of the TTS service (default: {CONFIG['port']})"
    )

    args = parser.parse_args()

    # Update config from args
    CONFIG["host"] = args.host
    CONFIG["port"] = args.port

    # Verify reference files exist
    if not os.path.exists(REFERENCE_AUDIO):
        logging.error(f"Reference audio not found: {REFERENCE_AUDIO}")
        return 1

    if not os.path.exists(REFERENCE_TEXT_FILE):
        logging.error(f"Reference text not found: {REFERENCE_TEXT_FILE}")
        return 1

    if not os.path.exists(args.script_file):
        logging.error(f"Script file not found: {args.script_file}")
        return 1

    process_script_file(args.script_file)
    return 0


if __name__ == "__main__":
    exit(main())
