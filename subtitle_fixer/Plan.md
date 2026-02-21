# Plan: YouTube Subtitle Fixer

## Context

Auto-generated YouTube subtitles are low quality — run-on sentences, missing punctuation,
filler words, misheard domain-specific terms, and no speaker change delineation. Manual
fixing is time-consuming. This script automates the cleanup using Claude with channel-aware
context provided through a configurable system prompt.

## Output

A single Python script: `subtitle_fixer.py`

Usage: `python subtitle_fixer.py <input.txt> [output.txt]`

- Default output: `Output/<input_stem>_fixed.txt`
- Script creates the Output directory automatically if it doesn't exist.

---

## Implementation Plan

### 1. Channel Configuration Section

A clearly-marked block at the top of the script holds all channel-specific values:

- `CHANNEL_NAME` — used in the system prompt header
- `HOST_NAME` — the main speaker / teacher
- `CHANNEL_FORMAT` — e.g. "live Q&A", "podcast", "interview"
- `CHANNEL_TOPICS` — core subjects, used for context-aware word correction
- `CHANNEL_SOURCES` — optional; key traditions or reference texts
- `CAPITALISATION_RULES` — optional; domain-specific capitalisation instructions

The `SYSTEM_PROMPT` is built at import time from these constants via `_build_system_prompt()`.

### 2. System Prompt Structure

The prompt provides Claude with:

- **Channel context**: name, host, format, topics, sources
- **Formatting rules**: sentence breaking, blank lines, speaker delineation, punctuation
- **Filler word removal**: "um", "uh", filler "like", repetitive "right?", filler "yeah"
- **Word correction**: use domain context to fix misheard words; replace unresolvable names with `[unclear]`
- **Capitalisation**: standard rules plus any domain-specific overrides from config
- **Output constraints**: plain text only, one to three sentences per paragraph

### 3. Chunking Strategy

- Split input on double newlines (`\n\n`) into paragraphs
- Group paragraphs until word count reaches ~300 words
- For a 60–90 minute video (~10,000 words) this yields ~25–30 chunks
- Each chunk is ~400–600 tokens — a good balance of quality and cost

### 4. Overlap / Context Passing

- After fixing each chunk, pass the **last paragraph** of the fixed output as context to the next call
- Marked with: `[CONTEXT FROM PREVIOUS SECTION — read for continuity, do NOT include this in your output]`
- Allows Claude to infer speaker changes, active vocabulary, and sentence continuity across boundaries

### 5. Script Structure

```
subtitle_fixer.py
  CHANNEL_NAME, HOST_NAME, ...  (configuration constants)
  _build_system_prompt() -> str
  SYSTEM_PROMPT               (built at import time)
  load_transcript(filepath) -> str
  split_into_chunks(text, words_per_chunk=300) -> list[str]
  get_overlap(fixed_text) -> str
  fix_chunk(client, chunk, prev_fixed=None) -> str
  default_output_path(input_path) -> str
  main()
```

**Model**: `claude-sonnet-4-6`
**Max output tokens**: `2048` per chunk
**API key**: read from `ANTHROPIC_API_KEY` environment variable

### 6. Progress & Output

- Print `Processing chunk X/N...` to stdout during processing
- Join fixed chunks with `\n\n` and write to output file

---

## Verification

1. Run with the sample input from `Specs.md` (paste it into `Input/transcript.txt`)
2. Compare output against the manually fixed sample in `Specs.md`
3. Check:
   - Misheard words corrected using domain context
   - Unrecognised names replaced with `[unclear]`
   - "um", "uh" removed throughout
   - Sentence breaks and blank lines match the expected structure
   - Any configured capitalisation rules applied correctly

## Dependencies

- Python 3.10+
- `anthropic` package: `pip install anthropic`
- `ANTHROPIC_API_KEY` environment variable set

## Run Command

```
python subtitle_fixer/subtitle_fixer.py subtitle_fixer/Input/transcript.txt
```
