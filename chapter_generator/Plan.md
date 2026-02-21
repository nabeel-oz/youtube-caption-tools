# Plan: YouTube Chapter Generator

## Context

YouTube does not reliably auto-generate chapters for longer videos. Manual chapter creation
requires re-watching the video. Feeding the full transcript to Claude in one call produces
progressively degrading output. This script solves both problems with a two-pass approach:
lightweight topic segmentation across the full video (Pass 1), then focused, high-quality
title generation per chapter (Pass 2).

## Output

A single Python script: `chapter_generator.py`

Usage: `python chapter_generator.py <input.srt|sbv> [output.txt] [--dry-run] [--min-chapter-mins N]`

- Default output: `Output/<stem>_chapters.txt`
- Script creates the Output directory automatically.

---

## Implementation Plan

### 1. Channel Configuration Section

A clearly-marked block at the top holds all channel-specific values:

- `CHANNEL_NAME` — used in both Pass 1 and Pass 2 system prompts
- `HOST_NAME` — the main speaker
- `CHANNEL_FORMAT` — e.g. "live Q&A", "podcast", "lecture"
- `CHANNEL_TOPICS` — core subjects, for Pass 1 context
- `CHANNEL_SOURCES` — optional; traditions or reference texts
- `SEO_TERMS` — optional; comma-separated searchable concepts for Pass 2 titles

Both system prompts are built at import time via `_build_pass1_system()` and
`_build_pass2_system()`.

### 2. Argument Parsing (argparse)

`argparse` is used (rather than `sys.argv`) because of the named flags:

```
python chapter_generator.py <input> [output] [--dry-run] [--min-chapter-mins N]
```

### 3. SRT / SBV Parser

Detect format by file extension.

**SRT block pattern:**
```
<index>
<HH:MM:SS,mmm> --> <HH:MM:SS,mmm>
<text lines>

```

**SBV block pattern:**
```
<H:MM:SS.mmm>,<H:MM:SS.mmm>
<text lines>

```

Both convert start timestamps to float seconds via `_ts_to_secs()`.
Lines that are solely bracket annotations (`[Music]`, `[Applause]`) are skipped.
Output: `list[Caption]` sorted by `start_secs`.

### 4. Pass 1 — Structure Detection

**Prose assembly**: join all caption texts (timestamps stripped) into a single string.

**Chunking**: split into words; accumulate ~450 words per chunk; prepend last 50 words of
the previous chunk as overlap. Yields ~30–35 chunks for a 90-minute video.

**Pass 1 system prompt** instructs Claude to:
- Return ONLY a JSON array of exact phrases (5–15 words) that BEGIN new sections.
- Count: new participant questions on genuinely new topics; meaningful sub-shifts within long
  answers (a new sub-point, a vivid analogy, a moment that could stand on its own).
- Not count: speaker changes on the same topic, short digressions, music/applause markers.

**API call per chunk**: `max_tokens=300`, model `claude-sonnet-4-6`.
Parse JSON array from response; deduplicate across chunks.

### 5. Boundary → Timestamp Mapping

For each boundary phrase:
1. Exact substring match in concatenated caption text → locate by character offset using
   `bisect` on cumulative offsets → return `caption.start_secs`.
2. If no exact match: `difflib.SequenceMatcher` against each caption's text; pick the
   best ratio above 0.55 threshold.

### 6. Minimum Duration Filter

Sort all boundary timestamps. Walk through them; drop any boundary within `min_secs` of
the previous one. The first (lowest) timestamp is always kept.

### 7. YouTube Constraint Enforcement

After filtering:
- Snap `chapter_timestamps[0]` to `0.0` unconditionally (YouTube requires 0:00; the first
  caption rarely starts at exactly 0.0 seconds).
- Track `synthetic_start` flag: if no boundary was detected within the first 5 seconds,
  `0.0` was added artificially and its chapter title is set to `"Introduction"` without an
  API call.
- If chapter count < 3, print a warning.

### 8. Pass 2 — Title Generation

**Pass 2 system prompt** instructs Claude to:
- Return ONLY the title (3–9 words), nothing else.
- Build the title from the most specific, memorable phrase or insight in the segment.
- Avoid generic topic labels.
- Apply SEO terms and channel voice from configuration.

For each chapter: call Claude with `max_tokens=40` and the segment's prose text.

### 9. Output Assembly

```python
lines = [f"{format_ts(secs)} {title}" for secs, title in chapters]
output_text = "\n".join(lines)
```

`format_ts(secs)`:
- `secs < 3600` → `"M:SS"` (e.g., `"4:22"`)
- `secs >= 3600` → `"H:MM:SS"` (e.g., `"1:14:03"`)

Print to stdout always. Write to file unless `--dry-run`.

---

## Module-Level Constants

```python
MODEL = "claude-sonnet-4-6"
PASS1_MAX_TOKENS = 300
PASS2_MAX_TOKENS = 40
DEFAULT_MIN_CHAPTER_MINS = 2
DEFAULT_WORDS_PER_CHUNK = 450
OVERLAP_WORDS = 50
```

---

## Script Structure

```
chapter_generator.py
  CHANNEL_NAME, HOST_NAME, ...   (configuration constants)
  _build_pass1_system() -> str
  _build_pass2_system() -> str
  PASS1_SYSTEM, PASS2_SYSTEM     (built at import time)

  Caption                        (dataclass: start_secs, text)

  _ts_to_secs(ts) -> float
  _is_bracket_only(text) -> bool
  _parse_srt(content) -> list[Caption]
  _parse_sbv(content) -> list[Caption]
  parse_captions(filepath) -> list[Caption]

  captions_to_prose(captions) -> str
  split_into_chunks(text, words_per_chunk, overlap_words) -> list[str]
  extract_segment(captions, start, end) -> str

  detect_boundaries(client, chunks) -> list[str]    # Pass 1
  find_timestamp(phrase, captions) -> float | None
  apply_min_duration(timestamps, min_secs) -> list[float]
  generate_title(client, segment_text) -> str       # Pass 2

  format_ts(secs) -> str
  default_output_path(input_path) -> str
  main()
```

---

## Verification

1. **Parser**: confirm caption count and first/last timestamps look correct.
2. **Pass 1 sanity**: run `--dry-run` and check boundary phrases correspond to real
   topic shifts in the transcript.
3. **Timestamp accuracy**: verify `format_ts()` output matches expected video positions.
4. **Min-duration filter**: test `--min-chapter-mins 5` to confirm micro-chapters merge.
5. **YouTube constraint**: verify output always starts with `0:00`.
6. **End-to-end**: paste output into YouTube Studio description — it should be accepted.

## Dependencies

- Python 3.10+
- `anthropic` package: `pip install anthropic`
- `ANTHROPIC_API_KEY` environment variable set
- Standard library only otherwise (`argparse`, `bisect`, `difflib`, `json`, `os`, `re`, `dataclasses`)

## Run Command

```
python chapter_generator/chapter_generator.py chapter_generator/Input/captions.sbv
```
