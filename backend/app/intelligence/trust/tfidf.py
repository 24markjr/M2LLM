r"""TF-IDF relevance, the way Member 4's verifier computed it, without scikit-learn.

Ported from `trust/verifier.py:relevance_scores`. The original fitted
`sklearn.feature_extraction.text.TfidfVectorizer(stop_words="english")` on the claim plus the
evidence and took cosine similarity between the claim row and each evidence row. This module
computes the same numbers with the same defaults:

- lowercase; tokens match `(?u)\b\w\w+\b` (two or more word characters)
- scikit-learn's English stop-word list, below
- raw term counts (`sublinear_tf=False`)
- smoothed idf: `ln((1 + n) / (1 + df)) + 1`
- each row L2-normalised; cosine similarity is then the dot product

**Why reimplement rather than depend on scikit-learn.** The original treated scikit-learn as
optional and fell back to word overlap without it, and the fallback is wrong in the way that
matters most: it marked a wrong arrival date `SUPPORTED` at 0.83 and dropped benchmark accuracy
from 60/60 to 46/60 (measured 2026-10-03, see `.claude/integrations/teammate-port.md`). A
verifier that silently gets weaker when a package is missing is worse than none. Thirty lines
of arithmetic remove the dependency and the failure mode together. Parity with scikit-learn
1.9.1 is checked in `tests/unit/test_trust.py`.

The stop-word list is scikit-learn's `ENGLISH_STOP_WORDS` (BSD-3-Clause, from the Glasgow
Information Retrieval Group list), 318 words, copied verbatim so scores match exactly.
"""

from __future__ import annotations

import math
import re
from collections import Counter

# fmt: off
ENGLISH_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "about", "above", "across", "after", "afterwards", "again", "against", "all", "almost",
        "alone", "along", "already", "also", "although", "always", "am", "among", "amongst",
        "amoungst", "amount", "an", "and", "another", "any", "anyhow", "anyone", "anything",
        "anyway", "anywhere", "are", "around", "as", "at", "back", "be", "became", "because",
        "become", "becomes", "becoming", "been", "before", "beforehand", "behind", "being", "below",
        "beside", "besides", "between", "beyond", "bill", "both", "bottom", "but", "by", "call",
        "can", "cannot", "cant", "co", "con", "could", "couldnt", "cry", "de", "describe", "detail",
        "do", "done", "down", "due", "during", "each", "eg", "eight", "either", "eleven", "else",
        "elsewhere", "empty", "enough", "etc", "even", "ever", "every", "everyone", "everything",
        "everywhere", "except", "few", "fifteen", "fifty", "fill", "find", "fire", "first", "five",
        "for", "former", "formerly", "forty", "found", "four", "from", "front", "full", "further",
        "get", "give", "go", "had", "has", "hasnt", "have", "he", "hence", "her", "here",
        "hereafter", "hereby", "herein", "hereupon", "hers", "herself", "him", "himself", "his",
        "how", "however", "hundred", "i", "ie", "if", "in", "inc", "indeed", "interest", "into",
        "is", "it", "its", "itself", "keep", "last", "latter", "latterly", "least", "less", "ltd",
        "made", "many", "may", "me", "meanwhile", "might", "mill", "mine", "more", "moreover",
        "most", "mostly", "move", "much", "must", "my", "myself", "name", "namely", "neither",
        "never", "nevertheless", "next", "nine", "no", "nobody", "none", "noone", "nor", "not",
        "nothing", "now", "nowhere", "of", "off", "often", "on", "once", "one", "only", "onto",
        "or", "other", "others", "otherwise", "our", "ours", "ourselves", "out", "over", "own",
        "part", "per", "perhaps", "please", "put", "rather", "re", "same", "see", "seem", "seemed",
        "seeming", "seems", "serious", "several", "she", "should", "show", "side", "since",
        "sincere", "six", "sixty", "so", "some", "somehow", "someone", "something", "sometime",
        "sometimes", "somewhere", "still", "such", "system", "take", "ten", "than", "that", "the",
        "their", "them", "themselves", "then", "thence", "there", "thereafter", "thereby",
        "therefore", "therein", "thereupon", "these", "they", "thick", "thin", "third", "this",
        "those", "though", "three", "through", "throughout", "thru", "thus", "to", "together",
        "too", "top", "toward", "towards", "twelve", "twenty", "two", "un", "under", "until", "up",
        "upon", "us", "very", "via", "was", "we", "well", "were", "what", "whatever", "when",
        "whence", "whenever", "where", "whereafter", "whereas", "whereby", "wherein", "whereupon",
        "wherever", "whether", "which", "while", "whither", "who", "whoever", "whole", "whom",
        "whose", "why", "will", "with", "within", "without", "would", "yet", "you", "your", "yours",
        "yourself", "yourselves",
    }
)
# fmt: on

_TOKEN = re.compile(r"(?u)\b\w\w+\b")
# Member 4's fallback tokenizer, used only by `word_overlap`.
_OVERLAP_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """scikit-learn's default analyzer with English stop words removed."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in ENGLISH_STOP_WORDS]


def tfidf_cosine(query: str, documents: list[str]) -> list[float] | None:
    """Cosine similarity of `query` to each document, fitted on all of them together.

    Returns None when the vocabulary is empty after stop-word removal, the case in which
    scikit-learn raises `ValueError` and the original fell back to word overlap.
    """
    if not documents:
        return []
    corpus = [tokenize(query), *(tokenize(d) for d in documents)]
    vocabulary = {term for tokens in corpus for term in tokens}
    if not vocabulary:
        return None

    n = len(corpus)
    df = Counter(term for tokens in corpus for term in set(tokens))
    idf = {term: math.log((1 + n) / (1 + df[term])) + 1.0 for term in vocabulary}

    vectors = [
        _normalised({term: count * idf[term] for term, count in Counter(tokens).items()})
        for tokens in corpus
    ]
    head = vectors[0]
    return [
        sum(weight * row.get(term, 0.0) for term, weight in head.items()) for row in vectors[1:]
    ]


def _normalised(vector: dict[str, float]) -> dict[str, float]:
    norm = math.sqrt(sum(w * w for w in vector.values()))
    if norm == 0.0:
        return {}
    return {term: weight / norm for term, weight in vector.items()}


def word_overlap(a: str, b: str) -> float:
    """Member 4's fallback: the share of `a`'s tokens that also appear in `b`."""
    ta, tb = set(_OVERLAP_TOKEN.findall(a.lower())), set(_OVERLAP_TOKEN.findall(b.lower()))
    if not ta:
        return 0.0
    return len(ta & tb) / len(ta)


def relevance_scores(claim: str, contents: list[str]) -> list[float]:
    """One relevance score per evidence text, in [0, 1].

    TF-IDF cosine. Word overlap is used only when the vocabulary is empty, the one case the
    original reached it with scikit-learn installed. It is no longer reachable by a missing
    package.
    """
    if not contents:
        return []
    scores = tfidf_cosine(claim, contents)
    if scores is None:
        return [word_overlap(claim, c) for c in contents]
    # Floating-point dot products of unit vectors can land a hair above 1.
    return [min(1.0, max(0.0, s)) for s in scores]
