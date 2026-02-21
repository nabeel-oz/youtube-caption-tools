# YouTube Subtitle Fixer — Specs

## Problem

- Poor quality auto-generated YouTube subtitles, especially for longer live Q&A videos.
- Time-consuming to fix manually.
- Naive LLM calls without channel context miss domain-specific word corrections and produce
  inconsistent results across long videos.

## Solution

A Python script that:

1. Loads a raw auto-generated transcript (`.txt`).
2. Splits it into logical chunks (~300 words each, on paragraph boundaries).
3. Calls Claude to fix each chunk with channel-aware context and the last paragraph of the
   previous fixed chunk for continuity.
4. Writes a single cleaned output file.

## Special Considerations

- **Context-aware word correction** — the correct word can often be inferred from context.
  For example, in a philosophy channel a misheard "taught" is likely "thought". The system
  prompt supplies enough domain context for Claude to make these calls reliably.
- **Unknown names** — if a participant's name is misheard and cannot be confidently resolved,
  Claude replaces it with `[unclear]` rather than guessing.
- **Filler words** — "um", "uh", repetitive "right?", and filler "yeah" are removed.
  A genuine "yeah" at the start of a reply is preserved.
- **Speaker delineation** — live Q&A calls involve multiple participants. Speaker changes
  are marked with a blank line; no explicit labels are added.

## Sample Input (raw auto-generated)

Replace this block with a short excerpt (~2–3 paragraphs) of raw auto-generated transcript
from your channel. Good examples show:
- Run-on sentences with missing punctuation
- Filler words ("um", "uh", repetitive "right?")
- A misheard domain-specific word that context can correct
- A speaker change mid-block

```
[paste raw auto-generated transcript excerpt here]
```

## Sample Manually Fixed Output

Replace this block with the expected clean output for the excerpt above. Good examples show:
- Sentences broken into short, clear lines separated by blank lines
- Filler words removed
- The misheard word corrected using domain context
- A blank line marking the speaker change (no label)
- Any domain-specific capitalisation rules applied

```
[paste the expected fixed output here]
```
