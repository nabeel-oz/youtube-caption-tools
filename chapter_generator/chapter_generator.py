"""
YouTube Chapter Generator
Generates timestamped chapter titles from SRT/SBV caption files using a
two-pass Claude API approach.

Usage:
    python chapter_generator.py <input.srt|sbv> [output.txt] [--dry-run] [--min-chapter-mins N]

If output path is omitted, writes to Output/<input_stem>_chapters.txt

Requirements:
    pip install anthropic
    export ANTHROPIC_API_KEY=your_key_here
"""

import argparse
import bisect
import difflib
import json
import os
import re
from dataclasses import dataclass

import anthropic


# ── Channel Configuration — edit before use ──────────────────────────────────

# The name of your channel
CHANNEL_NAME = "Your Channel Name"

# Content format — e.g. "live Q&A", "podcast", "interview", "lecture"
CHANNEL_FORMAT = "live Q&A"

# The main speaker / host
HOST_NAME = "the host"

# Core topics covered — used in both Pass 1 (segmentation) and Pass 2 (titles)
# e.g. "philosophy of mind, Stoicism, meditation"
CHANNEL_TOPICS = "the channel's core subject matter"

# Optional: key people, sources, or reference texts
# Leave as "" to omit from prompts.
CHANNEL_SOURCES = ""

# SEO terms relevant to your channel — included in the title generation prompt
# to help Claude surface searchable concepts naturally.
SEO_TERMS = ""

# ─────────────────────────────────────────────────────────────────────────────


# ── Constants ─────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-6"
PASS1_MAX_TOKENS = 300
PASS2_MAX_TOKENS = 40
DEFAULT_MIN_CHAPTER_MINS = 2
DEFAULT_WORDS_PER_CHUNK = 450
OVERLAP_WORDS = 50


# ── Prompts ───────────────────────────────────────────────────────────────────

def _build_pass1_system() -> str:
    sources_line = (
        f" Sources referenced include {CHANNEL_SOURCES}." if CHANNEL_SOURCES else ""
    )
    return f"""You are analyzing a transcript from "{CHANNEL_NAME}," a {CHANNEL_FORMAT} \
channel covering {CHANNEL_TOPICS}.{sources_line} \
Your only task is to identify points where the topic or focus meaningfully shifts.

Return ONLY a JSON array of short phrases (5–15 words each), where each phrase \
is the exact sentence or clause from the text that BEGINS a new section.
Example: ["So my question is about how this actually works in practice", \
          "Let me come at this from a completely different angle", \
          "The key thing I want to highlight here is"]

What counts as a new chapter:
- A new participant question that introduces a genuinely new subject.
- The opening monologue and the first Q&A question are always distinct chapters.
- Within a long answer: a clear pivot to a new sub-point, a vivid metaphor or \
  analogy introduced to make a distinct point, a practical exercise or worked \
  example, or a moment of conclusion that could stand on its own.
- A shift from abstract explanation to concrete application, or vice versa.

What does NOT count:
- A new speaker asking a question that continues the same topic.
- Short digressions that return to the same theme within a sentence or two.
- Music, applause, or silence markers.
- Return [] if this chunk contains no meaningful shift."""


def _build_pass2_system() -> str:
    sources_line = (
        f" Sources: {CHANNEL_SOURCES}." if CHANNEL_SOURCES else ""
    )
    seo_line = (
        f"\n- SEO-aware: include searchable concepts naturally where present: {SEO_TERMS}."
        if SEO_TERMS
        else "\n- SEO-aware: include searchable concepts from your channel's topic area where they arise naturally."
    )
    return f"""You generate YouTube chapter titles for "{CHANNEL_NAME}," a {CHANNEL_FORMAT} \
channel. Host: {HOST_NAME}.{sources_line}

Return ONLY the chapter title — nothing else, no explanation, no quotes.

Core principle: find the most specific, memorable phrase or insight in the \
segment and build the title from that. Avoid generic topic labels. If the \
content uses a vivid metaphor, a direct quote, or a specific pointer, use or \
adapt those exact words — they are almost always better than a description.

Title guidelines:
- 3–9 words.
- Phrase-based over topic-based: "Why Most People Get This Backwards" \
  beats "Overview of the Topic." "Who Is Actually in Charge?" beats "Leadership Q&A."{seo_line}
- Curiosity gap: phrase so a newcomer wants to know the answer.
- Authentic voice — precision and depth over marketing copy.
- If the segment is clearly a Q&A exchange, prefix with "Q&A — " only if it \
  adds clarity. Many Q&A segments yield better titles without the prefix."""


PASS1_SYSTEM = _build_pass1_system()
PASS2_SYSTEM = _build_pass2_system()


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class Caption:
    start_secs: float
    text: str


# ── Parsing ───────────────────────────────────────────────────────────────────

def _ts_to_secs(ts: str) -> float:
    """Convert a timestamp string (HH:MM:SS,mmm or H:MM:SS.mmm) to seconds."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def _is_bracket_only(text: str) -> bool:
    """Return True if the text is solely a bracket annotation like [Music]."""
    return bool(re.fullmatch(r"\[.*?\]", text.strip()))


def _parse_srt(content: str) -> list[Caption]:
    """Parse SRT subtitle format into Caption objects."""
    captions: list[Caption] = []
    blocks = re.split(r"\n\s*\n", content.strip())
    ts_pattern = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{3})"
    )
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        ts_line_idx = None
        for i, line in enumerate(lines):
            if ts_pattern.match(line):
                ts_line_idx = i
                break
        if ts_line_idx is None:
            continue
        m = ts_pattern.match(lines[ts_line_idx])
        start_secs = _ts_to_secs(m.group(1))
        text_lines = [
            ln for ln in lines[ts_line_idx + 1 :] if not _is_bracket_only(ln)
        ]
        if not text_lines:
            continue
        captions.append(Caption(start_secs=start_secs, text=" ".join(text_lines)))
    return sorted(captions, key=lambda c: c.start_secs)


def _parse_sbv(content: str) -> list[Caption]:
    """Parse SBV subtitle format into Caption objects."""
    captions: list[Caption] = []
    blocks = re.split(r"\n\s*\n", content.strip())
    ts_pattern = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}\.\d{3}),(\d{1,2}:\d{2}:\d{2}\.\d{3})"
    )
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue
        m = ts_pattern.match(lines[0])
        if not m:
            continue
        start_secs = _ts_to_secs(m.group(1))
        text_lines = [ln for ln in lines[1:] if not _is_bracket_only(ln)]
        if not text_lines:
            continue
        captions.append(Caption(start_secs=start_secs, text=" ".join(text_lines)))
    return sorted(captions, key=lambda c: c.start_secs)


def parse_captions(filepath: str) -> list[Caption]:
    """Parse an SRT or SBV caption file into a list of Caption objects."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".srt":
        return _parse_srt(content)
    elif ext == ".sbv":
        return _parse_sbv(content)
    else:
        print(f"Warning: unknown extension '{ext}', attempting SBV parse.")
        return _parse_sbv(content)


# ── Text utilities ─────────────────────────────────────────────────────────────

def captions_to_prose(captions: list[Caption]) -> str:
    """Join caption texts into clean prose (timestamps stripped)."""
    return " ".join(c.text for c in captions)


def split_into_chunks(
    text: str,
    words_per_chunk: int = DEFAULT_WORDS_PER_CHUNK,
    overlap_words: int = OVERLAP_WORDS,
) -> list[str]:
    """Split prose into overlapping chunks of ~words_per_chunk words.

    Each chunk (after the first) begins with the last overlap_words words of
    the previous chunk so that topic shifts at boundaries are not missed.
    """
    words = text.split()
    chunks: list[str] = []
    i = 0
    while i < len(words):
        start = max(0, i - overlap_words) if chunks else 0
        end = i + words_per_chunk
        chunks.append(" ".join(words[start:end]))
        i = end
    return chunks


def extract_segment(
    captions: list[Caption], start: float, end: float | None
) -> str:
    """Return the prose text for a chapter segment bounded by start/end times."""
    texts = []
    for cap in captions:
        if cap.start_secs < start:
            continue
        if end is not None and cap.start_secs >= end:
            break
        texts.append(cap.text)
    return " ".join(texts)


# ── Pass 1 ────────────────────────────────────────────────────────────────────

def detect_boundaries(
    client: anthropic.Anthropic, chunks: list[str]
) -> list[str]:
    """Pass 1: send each chunk to Claude and collect unique boundary phrases."""
    all_phrases: list[str] = []
    seen: set[str] = set()
    for i, chunk in enumerate(chunks, 1):
        print(f"  Pass 1 — chunk {i}/{len(chunks)}...")
        response = client.messages.create(
            model=MODEL,
            max_tokens=PASS1_MAX_TOKENS,
            system=PASS1_SYSTEM,
            messages=[{"role": "user", "content": chunk}],
        )
        raw = response.content[0].text.strip()
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if not m:
            continue
        try:
            phrases = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        for phrase in phrases:
            if isinstance(phrase, str) and phrase not in seen:
                seen.add(phrase)
                all_phrases.append(phrase)
    return all_phrases


# ── Timestamp mapping ─────────────────────────────────────────────────────────

def find_timestamp(phrase: str, captions: list[Caption]) -> float | None:
    """Map a boundary phrase to the start time of the matching caption.

    Tries exact substring match first; falls back to fuzzy matching via
    difflib.SequenceMatcher if no exact match is found.
    """
    offsets: list[int] = []
    start_times: list[float] = []
    concat = ""
    for cap in captions:
        offsets.append(len(concat))
        start_times.append(cap.start_secs)
        concat += cap.text + " "

    # 1. Exact substring match
    idx = concat.lower().find(phrase.lower())
    if idx != -1:
        cap_idx = bisect.bisect_right(offsets, idx) - 1
        return start_times[cap_idx]

    # 2. Fuzzy match against individual caption texts
    phrase_lower = phrase.lower()
    best_ratio = 0.0
    best_secs: float | None = None
    for cap in captions:
        ratio = difflib.SequenceMatcher(
            None, phrase_lower, cap.text.lower()
        ).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_secs = cap.start_secs

    if best_ratio >= 0.55:
        return best_secs
    return None


# ── Filtering ─────────────────────────────────────────────────────────────────

def apply_min_duration(timestamps: list[float], min_secs: int) -> list[float]:
    """Drop chapter boundaries that fall within min_secs of the previous one.

    The first (lowest) timestamp is always kept.
    """
    if not timestamps:
        return []
    sorted_ts = sorted(timestamps)
    result = [sorted_ts[0]]
    for ts in sorted_ts[1:]:
        if ts - result[-1] >= min_secs:
            result.append(ts)
    return result


# ── Pass 2 ────────────────────────────────────────────────────────────────────

def generate_title(client: anthropic.Anthropic, segment_text: str) -> str:
    """Pass 2: generate a single chapter title for one segment."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=PASS2_MAX_TOKENS,
        system=PASS2_SYSTEM,
        messages=[{"role": "user", "content": segment_text}],
    )
    return response.content[0].text.strip()


# ── Output formatting ─────────────────────────────────────────────────────────

def format_ts(secs: float) -> str:
    """Format seconds as M:SS or H:MM:SS for YouTube chapter timestamps."""
    total = int(round(secs))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def default_output_path(input_path: str) -> str:
    input_dir = os.path.dirname(os.path.abspath(input_path))
    chapter_gen_dir = os.path.dirname(input_dir)
    output_dir = os.path.join(chapter_gen_dir, "Output")
    stem = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(output_dir, f"{stem}_chapters.txt")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate YouTube chapter timestamps from an SRT or SBV caption file."
    )
    parser.add_argument("input", help="Path to the SRT or SBV caption file")
    parser.add_argument(
        "output",
        nargs="?",
        help="Output path (default: Output/<stem>_chapters.txt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print results to terminal without writing a file",
    )
    parser.add_argument(
        "--min-chapter-mins",
        type=int,
        default=DEFAULT_MIN_CHAPTER_MINS,
        metavar="N",
        help=f"Minimum chapter length in minutes (default: {DEFAULT_MIN_CHAPTER_MINS})",
    )
    args = parser.parse_args()

    input_path = args.input
    output_path = args.output or default_output_path(input_path)
    min_secs = args.min_chapter_mins * 60

    # ── Parse captions ────────────────────────────────────────────────────────
    print(f"Loading: {input_path}")
    captions = parse_captions(input_path)
    print(f"Parsed {len(captions)} captions\n")

    prose = captions_to_prose(captions)
    chunks = split_into_chunks(prose)
    print(f"Split into {len(chunks)} chunks for Pass 1\n")

    client = anthropic.Anthropic()

    # ── Pass 1: detect topic boundaries ──────────────────────────────────────
    print("Pass 1 — Structure Detection")
    boundary_phrases = detect_boundaries(client, chunks)
    print(f"\nDetected {len(boundary_phrases)} boundary phrase(s)\n")

    raw_timestamps: list[float] = []
    for phrase in boundary_phrases:
        ts = find_timestamp(phrase, captions)
        if ts is not None:
            raw_timestamps.append(ts)

    # Ensure 0:00 is always present; track whether it was synthetic
    synthetic_start = not any(ts <= 5.0 for ts in raw_timestamps)
    if synthetic_start:
        raw_timestamps.append(0.0)

    # Apply minimum chapter duration filter
    chapter_timestamps = apply_min_duration(raw_timestamps, min_secs)

    # Snap the first chapter to exactly 0:00 (YouTube requirement; the first
    # caption rarely starts at precisely 0.0 seconds)
    if chapter_timestamps:
        chapter_timestamps[0] = 0.0

    if len(chapter_timestamps) < 3:
        print(
            f"Warning: only {len(chapter_timestamps)} chapter(s) detected "
            "(YouTube requires at least 3).\n"
        )

    # ── Pass 2: generate chapter titles ──────────────────────────────────────
    print(f"Pass 2 — Title Generation ({len(chapter_timestamps)} chapters)")
    chapters: list[tuple[float, str]] = []

    for i, start in enumerate(chapter_timestamps):
        end = chapter_timestamps[i + 1] if i + 1 < len(chapter_timestamps) else None
        print(
            f"  Generating title for chapter {i + 1}/{len(chapter_timestamps)}"
            f" (starts at {format_ts(start)})..."
        )
        if start == 0.0 and synthetic_start:
            title = "Introduction"
        else:
            segment_text = extract_segment(captions, start, end)
            title = generate_title(client, segment_text)
        chapters.append((start, title))

    # ── Assemble and emit output ──────────────────────────────────────────────
    lines = [f"{format_ts(secs)} {title}" for secs, title in chapters]
    output_text = "\n".join(lines)

    print("\n--- Chapters ---")
    print(output_text)

    if args.dry_run:
        print("\n(Dry run — no file written.)")
    else:
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output_text)
        print(f"\nWritten to: {output_path}")


if __name__ == "__main__":
    main()
