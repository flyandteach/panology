"""
Descriptive prose diagnostics for the Draft Wringer agent.

Stdlib only. Assigns stable paragraph IDs and reports sentence-length
distribution, repeated sentence openings, recurring phrases,
paragraph-length patterns, and similar paragraph pairs. These signals flag
passages for human review; they are not an authorship test and do not
prescribe rewrites.

Usage:
    python3 -I draft_wringer/diagnostics.py DRAFT [--json]
"""

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

METHOD_NOTES = [
    "Paragraphs are split on blank lines only, so a heading or list separated "
    "by blank lines counts as its own paragraph and a list without blank lines "
    "counts as one.",
    "Sentences are split on . ! ? followed by whitespace and an uppercase "
    "letter, quote, or digit; abbreviations (e.g., 'U.S. Navy', 'Dr. Smith') "
    "can cause false splits.",
    "Sentence length is a whitespace word count.",
    "Opening = first two lowercase words of a sentence; reported when it "
    "occurs 3 or more times.",
    "Recurring phrases = word 4-grams occurring 2 or more times, excluding "
    "4-grams made up only of very common function words.",
    "Similar paragraphs = Jaccard overlap of content-word sets >= 0.35 "
    "(paragraphs with at least 8 content words).",
    "Counts describe surface patterns only. Purposeful repetition (defined "
    "terms, parallel structure, recurring caveats) will also be flagged.",
]

FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at",
    "for", "by", "with", "from", "as", "is", "are", "was", "were", "be",
    "been", "it", "its", "this", "that", "these", "those", "which", "who",
    "not", "no", "than", "then", "so", "if", "into", "can", "may", "will",
    "would", "should", "could", "has", "have", "had", "do", "does", "did",
    "their", "they", "them", "we", "our", "i", "you", "he", "she", "his",
    "her", "also", "such", "more", "most", "all", "any", "each", "other",
}

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[A-Z0-9\"'(\[])")
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")


def split_paragraphs(text):
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def split_sentences(paragraph):
    flat = " ".join(paragraph.split())
    return [s for s in SENTENCE_SPLIT.split(flat) if s.strip()]


def words(text):
    return [w.lower() for w in WORD.findall(text)]


def content_words(text):
    return {w for w in words(text) if w not in FUNCTION_WORDS and len(w) > 2}


def analyze(text):
    paragraphs = split_paragraphs(text)
    para_records = []
    sentence_records = []
    for p_idx, para in enumerate(paragraphs, start=1):
        pid = f"P{p_idx}"
        sentences = split_sentences(para)
        para_records.append({
            "id": pid,
            "words": len(para.split()),
            "sentences": len(sentences),
            "preview": " ".join(para.split())[:80],
        })
        for s_idx, sent in enumerate(sentences, start=1):
            sentence_records.append({
                "id": f"{pid}.S{s_idx}",
                "words": len(sent.split()),
                "text": sent,
            })

    lengths = [s["words"] for s in sentence_records]
    sentence_stats = {}
    if lengths:
        sentence_stats = {
            "count": len(lengths),
            "mean": round(statistics.mean(lengths), 1),
            "median": statistics.median(lengths),
            "stdev": round(statistics.stdev(lengths), 1) if len(lengths) > 1 else 0.0,
            "min": min(lengths),
            "max": max(lengths),
            "buckets": {
                "1-8": sum(1 for n in lengths if n <= 8),
                "9-16": sum(1 for n in lengths if 9 <= n <= 16),
                "17-25": sum(1 for n in lengths if 17 <= n <= 25),
                "26-40": sum(1 for n in lengths if 26 <= n <= 40),
                "41+": sum(1 for n in lengths if n >= 41),
            },
        }

    # Runs of 3+ consecutive short sentences (<= 8 words) within a paragraph.
    short_runs = []
    for para in para_records:
        sents = [s for s in sentence_records if s["id"].startswith(para["id"] + ".")]
        run = []
        for s in sents + [None]:
            if s is not None and s["words"] <= 8:
                run.append(s["id"])
                continue
            if len(run) >= 3:
                short_runs.append(run)
            run = []

    openings = Counter()
    opening_locs = {}
    for s in sentence_records:
        ws = words(s["text"])[:2]
        if len(ws) == 2:
            key = " ".join(ws)
            openings[key] += 1
            opening_locs.setdefault(key, []).append(s["id"])
    repeated_openings = [
        {"opening": k, "count": n, "locations": opening_locs[k]}
        for k, n in openings.most_common() if n >= 3
    ]

    gram_locs = {}
    for para in para_records:
        para_text = paragraphs[int(para["id"][1:]) - 1]
        ws = words(para_text)
        for i in range(len(ws) - 3):
            gram = tuple(ws[i:i + 4])
            if all(w in FUNCTION_WORDS for w in gram):
                continue
            gram_locs.setdefault(" ".join(gram), []).append(para["id"])
    recurring_phrases = sorted(
        (
            {"phrase": g, "count": len(locs), "locations": sorted(set(locs), key=lambda x: int(x[1:]))}
            for g, locs in gram_locs.items() if len(locs) >= 2
        ),
        key=lambda r: (-r["count"], r["phrase"]),
    )[:25]

    para_lengths = [p["words"] for p in para_records]
    paragraph_stats = {}
    if para_lengths:
        paragraph_stats = {
            "count": len(para_lengths),
            "mean_words": round(statistics.mean(para_lengths), 1),
            "stdev_words": round(statistics.stdev(para_lengths), 1) if len(para_lengths) > 1 else 0.0,
            "sentences_per_paragraph": Counter(p["sentences"] for p in para_records).most_common(),
        }

    similar = []
    sets = {p["id"]: content_words(paragraphs[i]) for i, p in enumerate(para_records)}
    for a, b in combinations(sets, 2):
        sa, sb = sets[a], sets[b]
        if len(sa) < 8 or len(sb) < 8:
            continue
        jaccard = len(sa & sb) / len(sa | sb)
        if jaccard >= 0.35:
            similar.append({"pair": [a, b], "jaccard": round(jaccard, 2)})
    similar.sort(key=lambda r: -r["jaccard"])

    return {
        "paragraphs": para_records,
        "sentence_length": sentence_stats,
        "short_sentence_runs": short_runs,
        "repeated_openings": repeated_openings,
        "recurring_phrases": recurring_phrases,
        "paragraph_length": paragraph_stats,
        "similar_paragraphs": similar,
        "method_and_limitations": METHOD_NOTES,
    }


def to_markdown(result, source):
    out = [f"# Descriptive diagnostics: {source}", ""]
    out.append("## Paragraph map")
    for p in result["paragraphs"]:
        out.append(f"- **{p['id']}** ({p['words']} words, {p['sentences']} sentences): {p['preview']}")
    s = result["sentence_length"]
    if s:
        out += ["", "## Sentence length (words)",
                f"{s['count']} sentences; mean {s['mean']}, median {s['median']}, "
                f"stdev {s['stdev']}, range {s['min']}-{s['max']}.",
                "Buckets: " + ", ".join(f"{k}: {v}" for k, v in s["buckets"].items())]
    out += ["", "## Runs of 3+ short sentences (<= 8 words)"]
    out += [f"- {', '.join(r)}" for r in result["short_sentence_runs"]] or ["- none"]
    out += ["", "## Repeated sentence openings (3+)"]
    out += [f"- \"{r['opening']}\" x{r['count']}: {', '.join(r['locations'])}"
            for r in result["repeated_openings"]] or ["- none"]
    out += ["", "## Recurring 4-word phrases (2+)"]
    out += [f"- \"{r['phrase']}\" x{r['count']}: {', '.join(r['locations'])}"
            for r in result["recurring_phrases"]] or ["- none"]
    pstats = result["paragraph_length"]
    if pstats:
        dist = ", ".join(f"{n} sentences: {c}" for n, c in pstats["sentences_per_paragraph"])
        out += ["", "## Paragraph length",
                f"{pstats['count']} paragraphs; mean {pstats['mean_words']} words, stdev {pstats['stdev_words']}.",
                f"Sentences per paragraph: {dist}"]
    out += ["", "## Similar paragraph pairs (content-word Jaccard >= 0.35)"]
    out += [f"- {r['pair'][0]} / {r['pair'][1]}: {r['jaccard']}"
            for r in result["similar_paragraphs"]] or ["- none"]
    out += ["", "## Method and limitations"]
    out += [f"- {n}" for n in result["method_and_limitations"]]
    return "\n".join(out) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("draft", help="Path to a plain-text or Markdown draft")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown")
    args = parser.parse_args(argv)
    text = Path(args.draft).read_text(encoding="utf-8")
    result = analyze(text)
    if args.json:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(to_markdown(result, args.draft))


if __name__ == "__main__":
    main()
