# YouTube Caption Tools

Two Python scripts that use the Claude API to automate the most tedious parts of
publishing long YouTube videos: fixing auto-generated subtitles and generating
chapter timestamps.

---

## Tools

### 1. `subtitle_fixer` — Clean auto-generated transcripts

Fixes YouTube's auto-generated captions using context-aware Claude API calls:
removes filler words, breaks run-on sentences, corrects domain-specific misheard
words, and delineates speaker changes with blank lines.

Processes the video in ~300-word chunks to maintain quality across long videos,
passing the last paragraph of each fixed chunk as context for the next call.

### 2. `chapter_generator` — Generate timestamped chapters

Takes a timestamped SRT or SBV caption file (downloaded from YouTube Studio) and
produces a `chapters.txt` ready to paste into the video description.

Uses a **two-pass approach** to maintain quality across long videos regardless of length:

- **Pass 1** — sends the transcript in overlapping chunks and asks Claude to identify
  only topic-shift markers (phrases that begin new sections). Lightweight: ~30–35 small
  API calls for a 90-minute video.
- **Pass 2** — sends each detected chapter segment to Claude individually for title
  generation. Because each call is focused, quality is consistent for every chapter.

---

## Workflow

```
Raw auto-generated transcript
    ↓ subtitle_fixer.py
Fixed subtitles (.txt)
    ↓ Import to YouTube
Timestamped captions (.srt or .sbv, download from YouTube Studio)
    ↓ chapter_generator.py
chapters.txt  (paste into video description)
```

Both tools can also be used independently.

---

## Setup

**Requirements**: Python 3.10+, an [Anthropic API key](https://console.anthropic.com/)

```bash
pip install anthropic
export ANTHROPIC_API_KEY=your_key_here   # or set in your environment
```

---

## Configuration

Both scripts have a clearly-marked **Channel Configuration** section near the top.
Fill in these constants before running:

```python
# subtitle_fixer.py / chapter_generator.py
CHANNEL_NAME    = "Your Channel Name"
HOST_NAME       = "the host"
CHANNEL_FORMAT  = "live Q&A"          # e.g. "podcast", "lecture", "interview"
CHANNEL_TOPICS  = "your channel's core subject matter"
CHANNEL_SOURCES = ""                  # optional: key traditions or reference texts
```

`chapter_generator.py` has one additional constant:

```python
SEO_TERMS = ""  # optional: comma-separated searchable keywords for titles
                # e.g. "Consciousness, Self-inquiry, Nonduality, Stoicism"
```

The system prompts are built from these constants at import time — no other changes needed.

---

## Usage

### Subtitle Fixer

Input: plain `.txt` file (paste the raw auto-generated transcript from YouTube Studio).

```bash
python subtitle_fixer/subtitle_fixer.py subtitle_fixer/Input/transcript.txt
# Output: subtitle_fixer/Output/transcript_fixed.txt
```

### Chapter Generator

Input: `.srt` or `.sbv` caption file (download from YouTube Studio after fixing subtitles).

```bash
python chapter_generator/chapter_generator.py chapter_generator/Input/captions.sbv
# Output: chapter_generator/Output/captions_chapters.txt

# Preview without writing a file:
python chapter_generator/chapter_generator.py chapter_generator/Input/captions.sbv --dry-run

# Set minimum chapter length (default: 2 minutes):
python chapter_generator/chapter_generator.py chapter_generator/Input/captions.sbv --min-chapter-mins 3
```

Paste the contents of `captions_chapters.txt` directly into the YouTube description.

---

## Cost

Both scripts use `claude-sonnet-4-6`. For a 90-minute video (~12,000–15,000 words):

| Tool | Calls | Approximate cost |
|---|---|---|
| Subtitle Fixer | ~30 chunks | < $0.05 |
| Chapter Generator (Pass 1) | ~33 chunks | < $0.03 |
| Chapter Generator (Pass 2) | ~15 titles | < $0.02 |

Total per video: **well under $0.10** (according to Claude). In practice it was AUD 0.48 over a 90 min video with two runs for the ChapterGenerator.

---

## File Structure

```
youtube-caption-tools/
  README.md
  subtitle_fixer/
    subtitle_fixer.py   ← main script
    Specs.md            ← problem statement and sample I/O
    Plan.md             ← implementation design
    Input/              ← place raw transcripts here
    Output/             ← fixed transcripts written here
  chapter_generator/
    chapter_generator.py  ← main script
    Specs.md              ← problem statement and design rationale
    Plan.md               ← implementation design
    Input/                ← place .srt / .sbv files here
    Output/               ← chapter lists written here
```
