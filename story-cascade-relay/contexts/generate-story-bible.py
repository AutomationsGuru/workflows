#!/usr/bin/env python3
"""Generate a synthetic ~1M-character story bible for cascade context tests."""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent / "story-bible-1m.md"
HIDDEN_FACTS = [
    "protagonist cannot see the color blue",
    "city clocks run 7 minutes slow",
    "antagonist refuses to cross bridges",
    "sacred phrase is `lantern under snow`",
    "map has one intentionally false island",
    "sidekick has a silver allergy",
    "final door opens only to a question",
    "storm season lasts 19 days",
    "archive books are shelved by scent",
    "nobody may speak names at noon",
]

section_template = """## Archive Fragment {i:04d}

The city of Veyr keeps records in nested districts, each with contradictory rumors and repeated civic rules. This fragment gives background texture, character pressure, scene motifs, and continuity constraints for the story cascade. The intended tone is luminous, tense, and humane. The story should avoid easy prophecy and should make every magical rule feel like a social habit.

Continuity reminder: Agent 1 owns the whole story bible; Agent 2 must packetize; Agent 3 must write only from bounded packets. Each scene should be useful even when read alone, but should also preserve global continuity.

Local motif {i:04d}: a bell, a wet stone stair, a witness who almost tells the truth, and a ledger entry that has been corrected twice.

"""

def main() -> None:
    parts = ["# Story Bible 1M Context Test", "", "## Hidden Facts", ""]
    for idx, fact in enumerate(HIDDEN_FACTS, start=1):
        parts.append(f"{idx}. {fact}")
    parts.extend(["", "## Mission Spine", "", "Write a six-scene speculative story about a courier carrying a forbidden question through a city that edits its own maps. Preserve hidden facts without listing them mechanically.", ""])

    text = "\n".join(parts)
    i = 1
    while len(text) < 1_020_000:
        text += section_template.format(i=i)
        if i % 73 == 0:
            fact = HIDDEN_FACTS[(i // 73) % len(HIDDEN_FACTS)]
            text += f"Embedded continuity shard: {fact}.\n\n"
        i += 1

    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {i-1} fragments)")

if __name__ == "__main__":
    main()
