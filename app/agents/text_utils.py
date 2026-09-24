"""
Text utilities shared by the quiet-signal custom agents
(TopicExtractAgent, HypeTermAgent).

Deliberately NOT ML: just regex tokenization, a stopword list, and
term-frequency / adjacent-bigram heuristics. Good enough to separate
"what is this article about" from stopwords/boilerplate without any
model calls.
"""

import re
from collections import Counter
from urllib.parse import urlparse

STOPWORDS = frozenset("""
a about above after again against all am an and any are aren't as at be
because been before being below between both but by can't cannot could
couldn't did didn't do does doesn't doing don't down during each few for
from further had hadn't has hasn't have haven't having he he'd he'll
he's her here here's hers herself him himself his how how's i i'd i'll
i'm i've if in into is isn't it it's its itself let's me more most
mustn't my myself no nor not of off on once only or other ought our
ours ourselves out over own same shan't she she'd she'll she's should
shouldn't so some such than that that's the their theirs them
themselves then there there's these they they'd they'll they're
they've this those through to too under until up very was wasn't we
we'd we'll we're we've were weren't what what's when when's where
where's which while who who's whom why why's with won't would
wouldn't you you'd you'll you're you've your yours yourself
yourselves new says say said gets get got via using use used just
like really also one two three first last new old big small

tell told tells telling tells reveal reveals revealed revealing
confirm confirms confirmed says report reports reported reporting
warn warns warned warning claim claims claimed according
discover discovers discovered discovering show shows showed shown
find finds found finding announce announces announced announcing
call calls called calling make makes made making take takes took
taking give gives gave given come comes came coming goes went gone
return returns returned returning repeat repeats repeated
defend defends defended defending vote votes voted voting
deny denies denied plan plans planned planning

system systems history world nation nations national global
international local regional country countries people person
group groups area areas place places thing things part parts
point points number numbers issue issues question questions
problem problems solution solutions update updates result results
example examples fact facts case cases kind kinds type types
way ways time times year years month months week weeks day days
period periods level levels set sets list lists

novel major key top large small high low long short recent
current latest former former past next main general major minor
early late great good best known official public private
brief full total complete entire single multiple various

american british french german chinese russian italian japanese
korean indian canadian australian european asian african latin
""".split())

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9'\-]{2,}")


def tokenize(text, min_length=4, stopwords=None):
    """Lowercase word tokens, stripped of stopwords and short words."""
    if not text:
        return []
    sw = stopwords if stopwords is not None else STOPWORDS
    words = [w.lower().strip("-'") for w in _WORD_RE.findall(text)]
    return [w for w in words if len(w) >= min_length and w and w not in sw and not w.isdigit()]


def top_terms_for_document(text, max_terms=3, min_length=4, stopwords=None):
    """
    Rank candidate terms within a single document (title/summary).

    Adjacent-word bigrams get a meaningful boost over lone unigrams, since
    two-word phrases ("supply chain", "carbon capture") are usually more
    informative than either word alone. Ties are broken by first-occurrence
    position (earlier = more likely to be the actual subject, especially
    since titles are prepended), NOT by string length - preferring the
    longest string on a tie tends to surface incidental noise phrases
    ("next infrastructure") over the real 2-word subject ("supply chain")
    whenever everything in a short document only appears once.
    """
    words = tokenize(text, min_length=min_length, stopwords=stopwords)
    if not words:
        return []

    first_seen = {}
    for i, w in enumerate(words):
        first_seen.setdefault(w, i)

    bigrams = [f'{a} {b}' for a, b in zip(words, words[1:])]
    for i, bg in enumerate(bigrams):
        first_seen.setdefault(bg, i)

    counts = Counter(words)
    bigram_counts = Counter(bigrams)

    candidates = Counter(counts)
    for bigram, count in bigram_counts.items():
        # Bigrams count double: two content words agreeing on a phrase is a
        # stronger signal than either word occurring alone.
        candidates[bigram] = candidates.get(bigram, 0) + (count * 2)

    ranked = sorted(candidates.items(), key=lambda kv: (-kv[1], first_seen.get(kv[0], 0)))
    return [term for term, _ in ranked[:max_terms]]


def document_term_set(text, min_length=4, stopwords=None):
    """Unique unigrams and bigrams in one document, for corpus-level
    document-frequency counting.

    Bigrams are included so HypeTermAgent's snapshot captures the same
    two-word phrases that TopicExtractAgent emits as topic_terms. Without
    bigrams, a phrase like 'agent skills' could slip past the hype check
    even when both constituent words individually fail to rank in the top-N
    unigrams — the phrase-level signal is missed entirely.
    """
    words = tokenize(text, min_length=min_length, stopwords=stopwords)
    bigrams = {f'{a} {b}' for a, b in zip(words, words[1:])}
    return set(words) | bigrams


def domain_from_url(url):
    """Best-effort bare domain (no scheme, no 'www.') for source-diversity counting."""
    if not url:
        return None
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return None
    if not netloc:
        return None
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    return netloc or None
