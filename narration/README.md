# Narration Generator

Generate voice narration from script files using a TTS service with voice cloning.

## Setup

Install dependencies using uv:

```bash
uv sync
```

## Reference Voice

Place your reference voice files in the `sample/` directory:

- `sample/Alice.wav` - Reference audio file
- `sample/text.txt` - Transcript of the reference audio

## Usage

Generate audio for all lines in a script file:

```bash
uv run python generate.py script.txt
```

Specify a different host or port:

```bash
uv run python generate.py script.txt --host 192.168.5.253 --port 7860
```

## Output

Generated audio files are saved to the `output/` directory with filenames based on line number and content:

```
output/
  001_hi_i_want_to.wav
  002_waywo_takes_the_monthly.wav
  ...
```

## Script Format

Each line in the script file should contain the text to narrate. Lines can optionally include speaker tags like `[S1]`:

```
[S1] This is the first line of narration.
[S1] This is the second line.
```
