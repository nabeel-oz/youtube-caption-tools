# YouTube Chapter Generator — Specs

## Problem

- YouTube does not reliably auto-generate chapters for longer videos (75–90 minutes).
- Creating chapters manually is time-consuming and requires re-watching the video.
- Feeding the full transcript to Claude in a single call degrades quality progressively:
  good output for the first 10–15 minutes, losing coherence in the middle, and
  hallucinating or drifting by the end.
- Chapter titles generated without structural awareness of the full video tend to be
  generic, miss key turning points, and fail to serve SEO or viewer navigation.

## Workflow Context

This tool sits downstream of the **Subtitle Fixer** pipeline:

```
Raw auto-generated transcript
    ↓ subtitle_fixer.py
Fixed subtitles (.txt)
    ↓ Import to YouTube
Timestamped captions (.srt or .sbv, downloaded from YouTube Studio)
    ↓ chapter_generator.py
chapters.txt  (ready to paste into video description)
```

The input is a **timestamped caption file** (SRT or SBV format) — not a raw transcript.
Every line of dialogue carries a precise timestamp, which the script uses directly to
assign chapter start times without guessing.

## Solution

A Python script (`chapter_generator.py`) that uses a combination of traditional string
parsing and targeted Claude API calls to produce a list of YouTube chapters with timestamps
and titles.

The script uses **two sequential passes** to balance quality and API cost:

**Pass 1 — Structure Detection (AI-assisted)**
Feed the full transcript (timestamps stripped, text only) to Claude in overlapping chunks.
Claude's only job is to return a list of topic-shift markers — the sentence or phrase that
signals where a new chapter should begin. No titles are generated yet. This is a lightweight
task Claude handles reliably with minimal tokens.

**Pass 2 — Title Generation (AI-assisted, per chapter)**
For each detected chapter segment, send the chunk of transcript text to Claude and ask for
one chapter title. Because each call has focused context (just one segment), Claude performs
at full quality for every chapter regardless of video length.

Traditional code handles all timestamp lookups, file parsing, and final output assembly.

## Input Format

The script accepts:

- **SRT** (`.srt`) — the standard subtitle format YouTube exports
- **SBV** (`.sbv`) — YouTube's native caption format

Both formats embed timestamps with every line of dialogue, which the parser uses to map
detected chapter boundaries back to precise start times.

## Two-Pass Design

### Pass 1: Topic Segmentation

- Strip timestamps from the parsed captions to produce clean prose.
- Split prose into overlapping chunks (~450 words, with ~50-word overlap to preserve
  context across boundaries).
- For each chunk, call Claude asking: *"Identify any points in this text where the topic
  or focus meaningfully shifts. Return the exact phrase or sentence that begins each new
  section."*
- Collect all returned boundary phrases and deduplicate.
- Use fuzzy string matching to locate each boundary phrase in the original timestamped
  caption data, then record the timestamp of the caption line where it appears.
- Apply a **minimum chapter duration filter** (default: 2 minutes) to prevent
  micro-chapters from noise or minor transitions. Adjacent chapters below the threshold
  are merged.

This pass makes a relatively small number of API calls (one per chunk) and uses low
`max_tokens` since the output is just a list of short phrases.

### Pass 2: Chapter Title Generation

- For each detected chapter segment, extract its full transcript text.
- Call Claude once per chapter, providing:
  - The segment text.
  - Channel context (format, topics, sources — configured at the top of the script).
  - Title guidelines (see below).
- Claude returns a single chapter title per call.
- Collect titles and pair with their timestamps.

This pass scales linearly with chapter count. A 90-minute video typically yields
10–20 chapters, so 10–20 small API calls — cost-effective and high-quality.

## Chapter Title Guidelines (Pass 2 prompt)

- **Phrase-based over topic-based** — build the title from the most specific, memorable
  phrase or insight in the segment.
- **Depth over clickbait** — capture the genuine insight, not just the topic.
- **SEO-aware** — include searchable concepts where they arise naturally (configured via
  the `SEO_TERMS` constant).
- **Curiosity gap** — phrase titles so a newcomer wants to know the answer.
- **Authentic voice** — precision and depth over marketing copy.
- **Concise** — 3–9 words is the target range.

### Sample Chapter Titles

Replace with a representative selection of chapter titles from your own channel.
Good examples show the range of styles the script can produce:
- Opening monologue titles
- Q&A chapter titles (with and without the "Q&A —" prefix)
- Phrase-based titles drawn directly from the content

```
[paste sample chapter titles here]
```

## Output Format

A plain `.txt` file formatted for direct paste into the YouTube description chapter field:

```
0:00 [Opening chapter title]
X:XX [Chapter title]
X:XX [Chapter title]
...
```

YouTube requires:
- At least 3 chapters.
- First chapter must start at `0:00`.
- Each timestamp on its own line, followed by the title.

The script enforces these constraints automatically, snapping the first chapter to `0:00`
and inserting an `Introduction` chapter if none was detected near the start.

## Special Considerations

- **Speaker changes are not chapter boundaries** — a new participant asking a question
  is only a chapter break if it introduces a genuinely new topic.
- **Sub-insights within long answers** — a vivid metaphor, a distinct realisation, or a
  meaningful shift in approach within a long answer counts as a chapter boundary.
- **Music or silence markers** — `[Music]` or `[Applause]` tags are ignored.
- **Long pauses / tangents** — short digressions that return to the same topic are not
  chapter boundaries.
- **Dry run / preview mode** — `--dry-run` prints detected chapters to the terminal
  without writing a file.

## CLI Usage

```
python chapter_generator.py <input.srt> [output.txt] [--dry-run] [--min-chapter-mins N]
```

- `input.srt` — timestamped caption file (SRT or SBV).
- `output.txt` — optional; defaults to `Output/<stem>_chapters.txt`.
- `--dry-run` — print results without writing a file.
- `--min-chapter-mins` — minimum chapter length in minutes (default: 2).

## Cost Estimate

For a 90-minute video (~12,000–15,000 words):

- **Pass 1**: ~30–35 chunk calls × ~500 tokens in, ~100 tokens out ≈ small.
- **Pass 2**: ~15 chapter calls × ~800 tokens in, ~20 tokens out ≈ very small.

Total per video: well under $0.10 at current Claude Sonnet pricing.
