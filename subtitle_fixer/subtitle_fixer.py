"""
YouTube Subtitle Fixer
Cleans auto-generated YouTube transcripts using context-aware Claude API calls.

Usage:
    python subtitle_fixer.py <input.txt> [output.txt]

If output path is omitted, writes to Output/<input_stem>_fixed.txt

Requirements:
    pip install anthropic
    export ANTHROPIC_API_KEY=your_key_here
"""

import re
import sys
import os
import anthropic


# ── Channel Configuration — edit before use ──────────────────────────────────

# The name of your channel (used in the system prompt for context)
CHANNEL_NAME = "Your Channel Name"

# The main speaker / host who presents and answers questions
HOST_NAME = "the host"

# Content format — e.g. "live Q&A", "podcast", "interview", "lecture"
CHANNEL_FORMAT = "live Q&A"

# Core topics covered — helps Claude make context-aware word corrections
CHANNEL_TOPICS = "the channel's core subject matter"

# Optional: key people, texts, or sources referenced on the channel
# Leave as "" to omit this line from the prompt.
CHANNEL_SOURCES = ""

# Optional: domain-specific capitalisation rules as plain English instructions.
# Example: 'Always capitalise "[Term]"
CAPITALISATION_RULES = ""

# ─────────────────────────────────────────────────────────────────────────────


def _build_system_prompt() -> str:
    sources_line = (
        f"- Sources: {CHANNEL_SOURCES}\n" if CHANNEL_SOURCES else ""
    )
    cap_section = (
        f"\nCAPITALISATION RULES — apply these precisely:\n{CAPITALISATION_RULES}\n"
        if CAPITALISATION_RULES
        else "\nCAPITALISATION:\n- Follow standard English capitalisation rules.\n"
    )
    return f"""You are cleaning and fixing auto-generated YouTube subtitles for "{CHANNEL_NAME}".

CHANNEL CONTEXT:
- Host/main speaker: {HOST_NAME} (teaches, presents, answers questions)
- Format: {CHANNEL_FORMAT} — other participants may ask questions and offer comments
{sources_line}- Core topics: {CHANNEL_TOPICS}

YOUR TASK:
Fix the chunk of raw auto-generated transcript text provided. Apply the rules below exactly.

FORMATTING:
- Break long run-on sentences into shorter, clear sentences
- Place each distinct thought or sentence on its own line, separated by a blank line
- Add a blank line whenever the speaker changes — this is the only speaker delineation needed (no labels)
- Use proper punctuation throughout
- Use ellipses (...) for genuine trailing-off pauses or a speaker rephrasing mid-sentence, not for every pause

FILLER WORD REMOVAL:
- Remove: "um", "uh", filler uses of "like", repetitive "right?" at the end of sentences
- Remove filler "yeah" — but keep "yeah" when it is a genuine response (e.g., at the very start of a reply)
- Do not remove meaningful content words

WORD AND NAME CORRECTION:
- Use domain context to correct misheard words (e.g., a word that makes no sense in context is likely a mishearing)
- If a name or word is unclear or seems to be a mishearing you cannot confidently resolve, replace it with [unclear]
- Do not invent or guess names
{cap_section}
PRESERVE:
- The speaker's actual meaning and content
- Natural speech rhythms where they add authenticity
- First-person voice exactly as spoken

OUTPUT:
- Plain text only — no markdown, no headers, no labels
- One to three sentences per paragraph, separated by blank lines
- Blank lines between speaker changes
"""


SYSTEM_PROMPT = _build_system_prompt()


def load_transcript(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def split_into_chunks(text: str, words_per_chunk: int = 300) -> list[str]:
    """Split transcript into chunks of ~words_per_chunk words, on paragraph boundaries."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks = []
    current: list[str] = []
    current_words = 0

    for para in paragraphs:
        para_words = len(para.split())
        if current_words + para_words > words_per_chunk and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_words = para_words
        else:
            current.append(para)
            current_words += para_words

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def get_overlap(fixed_text: str) -> str:
    """Return the last paragraph of a fixed chunk to use as context for the next call."""
    paragraphs = [p.strip() for p in fixed_text.split("\n\n") if p.strip()]
    return paragraphs[-1] if paragraphs else ""


def clean_output(text: str) -> str:
    """Strip trailing whitespace from every line and collapse runs of 3+ newlines."""
    lines = [line.rstrip() for line in text.split("\n")]
    cleaned = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", cleaned)


def fix_chunk(client: anthropic.Anthropic, chunk: str, prev_fixed: str | None) -> str:
    if prev_fixed:
        user_content = (
            f"[CONTEXT FROM PREVIOUS SECTION — read for continuity, do NOT include this in your output]\n"
            f"{prev_fixed}\n\n"
            f"[TEXT TO FIX — output only the corrected version of this]\n"
            f"{chunk}"
        )
    else:
        user_content = chunk

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return clean_output(response.content[0].text.strip())


def default_output_path(input_path: str) -> str:
    input_dir = os.path.dirname(os.path.abspath(input_path))
    subtitle_fixer_dir = os.path.dirname(input_dir)
    output_dir = os.path.join(subtitle_fixer_dir, "Output")
    stem = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(output_dir, f"{stem}_fixed.txt")


def main():
    if len(sys.argv) < 2:
        print("Usage: python subtitle_fixer.py <input.txt> [output.txt]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else default_output_path(input_path)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"Loading: {input_path}")
    text = load_transcript(input_path)

    chunks = split_into_chunks(text, words_per_chunk=300)
    print(f"Split into {len(chunks)} chunks")
    print(f"Output: {output_path}\n")

    client = anthropic.Anthropic()
    fixed_chunks: list[str] = []

    for i, chunk in enumerate(chunks, 1):
        print(f"Processing chunk {i}/{len(chunks)}...")
        prev_fixed = get_overlap(fixed_chunks[-1]) if fixed_chunks else None
        fixed = fix_chunk(client, chunk, prev_fixed)
        fixed_chunks.append(fixed)

    output = "\n\n".join(fixed_chunks)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output)

    # YouTube-ready version: collapse blank lines so YouTube doesn't render
    # each blank line as an empty subtitle frame during active speech.
    stem, ext = os.path.splitext(output_path)
    youtube_path = f"{stem}_youtube{ext}"
    youtube_output = output.replace("\n\n", "\n")
    with open(youtube_path, "w", encoding="utf-8") as f:
        f.write(youtube_output)

    print(f"\nDone.")
    print(f"  Review copy : {output_path}")
    print(f"  YouTube copy: {youtube_path}")


if __name__ == "__main__":
    main()
