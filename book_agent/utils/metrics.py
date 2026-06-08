"""
TextMetrics: Computational text analysis without heavy NLP dependencies.
Uses stdlib + textstat only.
"""

import re
import string
import statistics
from collections import Counter
from typing import Any

import textstat

# Hardcoded English stopwords (common set, no NLTK required)
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need", "dare",
    "ought", "used", "this", "that", "these", "those", "i", "you", "he",
    "she", "it", "we", "they", "me", "him", "her", "us", "them", "my",
    "your", "his", "its", "our", "their", "what", "which", "who", "whom",
    "when", "where", "why", "how", "all", "each", "every", "both", "few",
    "more", "most", "other", "some", "such", "no", "not", "only", "same",
    "so", "than", "too", "very", "just", "as", "if", "about", "also",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "up", "down", "then", "once", "here", "there",
    "s", "t", "re", "ve", "ll", "d", "m", "ain", "aren", "couldn",
    "didn", "doesn", "hadn", "hasn", "haven", "isn", "ma", "mightn",
    "mustn", "needn", "shan", "shouldn", "wasn", "weren", "won", "wouldn",
}

# Passive voice auxiliary verbs
PASSIVE_AUXILIARIES = {"was", "were", "been", "being", "is", "are", "am"}

# Simple past participle pattern: ends in -ed or common irregular forms
IRREGULAR_PAST_PARTICIPLES = {
    "written", "known", "shown", "given", "taken", "made", "done", "seen",
    "gone", "said", "told", "found", "thought", "left", "brought", "built",
    "bought", "caught", "taught", "kept", "met", "sent", "set", "put",
    "read", "led", "felt", "held", "heard", "lost", "meant", "spent",
    "grown", "drawn", "driven", "eaten", "fallen", "forgotten", "frozen",
    "gotten", "hidden", "ridden", "risen", "spoken", "stolen", "worn",
    "chosen", "broken", "woken", "begun", "run", "come", "become",
}


class TextMetrics:
    """Analyse a prose passage and return a metrics dictionary."""

    def analyze(self, text: str) -> dict:
        """Return a full metrics dict for the given text."""
        if not text or not text.strip():
            return self._empty_metrics()

        sentences = self._split_sentences(text)
        paragraphs = self._split_paragraphs(text)
        tokens = self._tokenize(text)
        words = [t for t in tokens if t.isalpha()]
        lower_words = [w.lower() for w in words]

        word_count = len(words)
        sentence_count = max(len(sentences), 1)
        paragraph_count = max(len(paragraphs), 1)

        sentence_lengths = [len(self._tokenize(s)) for s in sentences if s.strip()]
        avg_sentence_length = statistics.mean(sentence_lengths) if sentence_lengths else 0.0
        sentence_length_std = (
            statistics.stdev(sentence_lengths) if len(sentence_lengths) > 1 else 0.0
        )

        para_lengths = [len(self._tokenize(p)) for p in paragraphs if p.strip()]
        avg_paragraph_length = statistics.mean(para_lengths) if para_lengths else 0.0
        paragraph_length_std = (
            statistics.stdev(para_lengths) if len(para_lengths) > 1 else 0.0
        )

        unique_words = set(lower_words)
        type_token_ratio = len(unique_words) / word_count if word_count else 0.0

        trigrams = self._ngrams(lower_words, 3)
        fourgrams = self._ngrams(lower_words, 4)
        trigram_counts = Counter(trigrams)
        fourgram_counts = Counter(fourgrams)

        repeated_3grams = [
            (" ".join(ng), cnt)
            for ng, cnt in trigram_counts.most_common(20)
            if cnt > 2
        ]
        repeated_4grams = [
            (" ".join(ng), cnt)
            for ng, cnt in fourgram_counts.most_common(10)
            if cnt > 1
        ]

        repeated_sentence_openings = self._find_repeated_openings(sentences)

        content_words = [w for w in lower_words if w not in STOPWORDS and len(w) > 2]
        word_freq = Counter(content_words)
        top_repeated_words = word_freq.most_common(10)

        readability_score = textstat.flesch_reading_ease(text)
        passive_count = self._estimate_passive(sentences)

        return {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_length": round(avg_sentence_length, 2),
            "sentence_length_std": round(sentence_length_std, 2),
            "paragraph_count": paragraph_count,
            "avg_paragraph_length": round(avg_paragraph_length, 2),
            "paragraph_length_std": round(paragraph_length_std, 2),
            "type_token_ratio": round(type_token_ratio, 4),
            "repeated_3grams": repeated_3grams,
            "repeated_4grams": repeated_4grams,
            "repeated_sentence_openings": repeated_sentence_openings,
            "top_repeated_words": top_repeated_words,
            "readability_score": round(readability_score, 2),
            "passive_voice_estimate": passive_count,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _empty_metrics(self) -> dict:
        return {
            "word_count": 0,
            "sentence_count": 0,
            "avg_sentence_length": 0.0,
            "sentence_length_std": 0.0,
            "paragraph_count": 0,
            "avg_paragraph_length": 0.0,
            "paragraph_length_std": 0.0,
            "type_token_ratio": 0.0,
            "repeated_3grams": [],
            "repeated_4grams": [],
            "repeated_sentence_openings": [],
            "top_repeated_words": [],
            "readability_score": 0.0,
            "passive_voice_estimate": 0,
        }

    def _split_sentences(self, text: str) -> list:
        """Split text into sentences using punctuation heuristics."""
        # Split on .!? followed by whitespace and capital letter or end
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", text.strip())
        # Further split very long parts on semicolons
        sentences = []
        for part in parts:
            if part.strip():
                sentences.append(part.strip())
        return sentences if sentences else [text.strip()]

    def _split_paragraphs(self, text: str) -> list:
        """Split on double newlines or blank lines."""
        paras = re.split(r"\n\s*\n", text.strip())
        return [p.strip() for p in paras if p.strip()]

    def _tokenize(self, text: str) -> list:
        """Simple whitespace + punctuation tokenizer."""
        return text.split()

    def _ngrams(self, tokens: list, n: int) -> list:
        """Return list of n-gram tuples."""
        return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]

    def _find_repeated_openings(self, sentences: list) -> list:
        """Find sentence-opening words that repeat more than twice."""
        first_words = []
        for s in sentences:
            words = s.strip().split()
            if words:
                # Take first content word (skip quotes/em-dashes)
                first = re.sub(r"[^a-zA-Z]", "", words[0]).lower()
                if first:
                    first_words.append(first)

        counts = Counter(first_words)
        return [word for word, cnt in counts.items() if cnt > 2]

    def _estimate_passive(self, sentences: list) -> int:
        """Heuristic count of passive constructions."""
        passive_count = 0
        passive_pattern = re.compile(
            r"\b(was|were|been|being|is|are|am)\s+(\w+ed|"
            + "|".join(IRREGULAR_PAST_PARTICIPLES)
            + r")\b",
            re.IGNORECASE,
        )
        for sentence in sentences:
            if passive_pattern.search(sentence):
                passive_count += 1
        return passive_count
