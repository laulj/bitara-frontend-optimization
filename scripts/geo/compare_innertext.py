#!/usr/bin/env python
"""Triage helper for P0-1 — is the reduced variant duplicate-stripped, or genuinely smaller?

`render_parity.mjs` measures how much text the reduced variant loses. It cannot say *what
kind* of loss it is, and the P0-1 triage depends on exactly that:

  (b) the full variant is inflated  -> the lost text is a *repeat* of text that is still
      present in the reduced variant (a duplicated ticker / carousel / market strip)
  (c) genuine UA-conditional content -> the lost text exists nowhere in the reduced variant

Method: whitespace-normalise both rendered `innerText` dumps, then compare whole-word
tokens and 8-gram counts. Line-by-line diffs are useless here — the DOM layouts differ, so
the same sentence wraps at different points (measured: "Build, Launch & Scale" +
"Web3 Ecosystems" vs "Build, Launch & Scale Web3 Ecosystems").

Usage:
  python scripts/geo/compare_innertext.py <baseline.innerText.txt> <other.innerText.txt>
"""

from __future__ import annotations

import re
import sys
from collections import Counter

TOKEN = re.compile(r"[a-z0-9%.,'&-]+")
NGRAM = 8


def tokens(path: str) -> list[str]:
    """Whole-word tokens, trailing sentence punctuation stripped.

    Stripping matters: the two variants wrap text at different points, so the same word
    arrives as `allocation` on one side and `allocation.` on the other. Left alone, that
    noise reads as "unique content on both sides" and inverts the verdict.
    """
    text = re.sub(r"\s+", " ", open(path, encoding="utf-8").read().lower())
    return [t for t in (raw.strip(".,;:") for raw in TOKEN.findall(text)) if t]


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    base_path, other_path = sys.argv[1], sys.argv[2]
    base, other = tokens(base_path), tokens(other_path)

    print(f"baseline {base_path}: {len(base)} tokens, vocab {len(set(base))}")
    print(f"other    {other_path}: {len(other)} tokens, vocab {len(set(other))} "
          f"({len(other) / max(1, len(base)):.3f}x)")
    print()

    # 1. Is the reduced text a vocabulary subset? (a superset of tokens it shares)
    missing_vocab = sorted(set(base) - set(other))
    extra_vocab = sorted(set(other) - set(base))
    print(f"tokens in baseline absent from other: {len(missing_vocab)}")
    print(f"  {missing_vocab[:25]}")
    print(f"tokens in other absent from baseline: {len(extra_vocab)}")
    print(f"  {extra_vocab[:25]}")
    print()

    # 2. Repetition test: text the baseline says MORE often than the other does.
    def grams(words: list[str]) -> Counter:
        return Counter(" ".join(words[i:i + NGRAM]) for i in range(len(words) - NGRAM + 1))

    gb, go = grams(base), grams(other)
    repeats = sorted(((gb[k] - go.get(k, 0), k) for k in gb if gb[k] > go.get(k, 0)),
                     reverse=True)
    baseline_only = [k for k in go if k not in gb]

    print(f"top {NGRAM}-grams the baseline repeats more than the other "
          f"(count_baseline > count_other):")
    for delta, gram in repeats[:10]:
        print(f"  +{delta}  (b={gb[gram]} o={go.get(gram, 0)})  {gram[:110]}")
    print()
    print(f"{NGRAM}-grams present ONLY in the other (unique content the baseline lacks): "
          f"{len(baseline_only)}")
    for gram in baseline_only[:5]:
        print(f"  * {gram[:110]}")
    print()

    # 2b. Per-token counts — this is what separates "the variant says it fewer times"
    #     (repetition/list-instance difference) from "the variant never says it"
    #     (content absence). An n-gram test cannot tell those apart.
    count_base, count_other = Counter(base), Counter(other)
    rows = [{"token": t, "base": n, "other": count_other.get(t, 0), "delta": n - count_other.get(t, 0)}
            for t, n in count_base.items() if n > count_other.get(t, 0)]
    rows.sort(key=lambda r: r["delta"], reverse=True)
    total_lost = len(base) - len(other)
    print("top tokens by count difference (delta, baseline, other):")
    for row in rows[:15]:
        print(f"  {row['delta']:>4} {row['base']:>6} {row['other']:>6}  {row['token'][:60]}")
    print()

    # 3. Reading. This is a LEXICAL test: it can rank the candidate classes, never decide
    #    between them. Only reading the template code (or the edge config) can do that.
    absent = [r for r in rows if r["other"] == 0]
    fewer = [r for r in rows if r["other"] > 0]
    absent_mass = sum(r["delta"] for r in absent)
    fewer_mass = sum(r["delta"] for r in fewer)
    # Vocabulary the other variant has that the baseline does not. Near-zero (ignoring
    # punctuation-only variants) means the reduced text is a SUBSET, i.e. nothing is shown
    # to bots that a browser cannot see.
    punctuation_only = {".", ",", "'", "&", "-", "%"}
    substantive_extra = [t for t in extra_vocab if t not in punctuation_only and len(t) > 2]

    print(f"tokens absent from the other variant:        {len(absent)} "
          f"(mass {absent_mass})")
    print(f"tokens present but fewer times in the other: {len(fewer)} "
          f"(mass {fewer_mass})")
    print(f"substantive vocabulary unique to the other:  {len(substantive_extra)} "
          f"{substantive_extra[:10]}")
    print()
    print("lexical reading (rank the class, never decide it):")
    if total_lost <= 0:
        print("  no lexical loss.")
    elif len(substantive_extra) <= 5 and absent_mass < fewer_mass:
        print("  SUBSET WITH FEWER INSTANCES — the reduced variant repeats list/ticker content")
        print("  less often; it shows nothing a browser cannot see. Class (b) candidate:")
        print("  check for a duplicated marquee/carousel in the full variant. Still requires")
        print("  the template code or edge config to confirm.")
    elif len(substantive_extra) <= 5:
        print("  SUBSET — no unique content on the reduced side, but a large lexical mass is")
        print("  absent, concentrated in specific blocks. Inspect which blocks (see the top")
        print("  n-grams above); class (b) vs (c) cannot be settled without the code.")
    else:
        print("  BOTH SIDES HAVE UNIQUE CONTENT — this is not a simple subset. That is the")
        print("  shape of genuinely different pages per UA: treat as class (c) until proven")
        print("  otherwise, and escalate rather than optimise around it.")
    print()
    print("REMINDER: this test compares rendered innerText only. A section that exists in")
    print("both but renders fewer items is indistinguishable here from a section that is")
    print("missing entirely. Read the template code before acting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
