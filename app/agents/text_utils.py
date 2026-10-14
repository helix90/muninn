"""
Text utilities shared by the quiet-signal custom agents
(TopicExtractAgent, HypeTermAgent).

Deliberately NOT ML: just regex tokenization, a stopword list, and
term-frequency / adjacent-bigram heuristics. Good enough to separate
"what is this article about" from stopwords/boilerplate without any
model calls.
"""

import html
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

# Promotional / clickbait vocabulary. These words say how loudly a story is
# being sold, not what it is about, so they are never topic terms - and
# TopicExtractAgent reports which ones it saw so SignalScoreAgent can drop
# items that lean on them.
HYPE_LANGUAGE_WORDS = frozenset("""
revolutionary revolutionize revolutionizes revolutionizing revolution
game-changing game-changer gamechanger groundbreaking ground-breaking
breakthrough breakthroughs disruptive disrupt disrupts disrupting
unprecedented mind-blowing jaw-dropping insane shocking stunning
incredible amazing astonishing ultimate must-read must-see must-have
viral exclusive breaking skyrocket skyrockets skyrocketing soar soars
soaring explodes exploding slams destroys epic next-gen next-generation
cutting-edge bleeding-edge world-class best-in-class industry-leading
unveil unveils unveiled supercharge supercharges turbocharge 10x
hottest hype hyped massive huge
""".split())

HYPE_LANGUAGE_PHRASES = (
    "you won't believe", "here's why", "here is why", "what you need to know",
    "everything you need to know", "changes everything", "change everything",
    "the future of", "this one trick", "will blow your mind", "is dead",
    "is here", "goes viral", "taking over", "nobody is talking about",
)

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9'\-]{2,}")

# Every word-like run, including short words and numbers, so that a dropped
# token (stopword, too-short word) can be seen as a gap between two content
# words rather than silently collapsed.
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")

# Sentence/clause punctuation that should stop a bigram forming across it.
_BOUNDARY_RE = re.compile(
    r"[.,;:!?|]+(?=\s|$)|[()\[\]{}\"\u2013\u2014\u201c\u201d\n\r\t]|\s-+\s"
)

_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

# Boilerplate injected by common feed generators. Left in, it dominates term
# counts: every hnrss.org item's summary repeats "Article URL / Comments URL /
# Points / # Comments" plus two URLs, so before cleaning, EVERY Hacker News
# item got the same topic_key ("href https") and clustered together.
_FEED_BOILERPLATE_RES = [
    re.compile(p, re.IGNORECASE) for p in (
        r"\b(?:article|comments)\s+url\s*:",                    # hnrss.org
        r"\bpoints\s*:\s*\d+",                                 # hnrss.org
        r"#?\s*\bcomments\s*:\s*\d+",                           # hnrss.org
        r"\b(?:show|ask|tell|launch)\s+hn\s*:",                  # HN title prefixes
        r"\barxiv:\S+(?:\s+announce\s+type:\s*\S+)?",            # arXiv listing header
        r"\babstract\s*:",                                      # arXiv
        r"\bthe\s+post\s+.{0,200}?\s+appeared\s+first\s+on\s+[^.]*\.?",  # WordPress footer
        r"\b(?:continue\s+reading|read\s+more|read\s+the\s+full\s+(?:story|article))\b",
        r"\bsubmitted\s+by\s+/?u/\S+",                          # reddit
        r"\[(?:link|comments)\]",                               # reddit
    )
]


def clean_text(text):
    """
    Strip markup and feed boilerplate from RSS title/summary text.

    Tags become clause boundaries (so "</p><p>" can't glue the last word of
    one paragraph to the first word of the next), entities are decoded, and
    URLs plus known feed-generator boilerplate are removed.
    """
    if not text:
        return ''
    text = _TAG_RE.sub(' \n ', str(text))
    text = html.unescape(text)
    text = _URL_RE.sub(' ', text)
    for pattern in _FEED_BOILERPLATE_RES:
        text = pattern.sub(' \n ', text)
    return text


def _segments(text, min_length, stopwords):
    """
    Split text into runs of consecutive content words.

    A run ends at clause punctuation or at any token that gets dropped
    (stopword, short word, number), so adjacent-word bigrams only come from
    words that were actually adjacent in the source: "state of the art"
    yields no "state art", and "Rust. Python tooling" yields no "rust python".
    """
    segments = []
    for chunk in _BOUNDARY_RE.split(text):
        current = []
        for raw in _TOKEN_RE.findall(chunk):
            w = raw.lower().strip("-'")
            if (len(w) >= min_length and w[0].isalpha()
                    and w not in stopwords and not w.isdigit()):
                current.append(w)
            elif current:
                segments.append(current)
                current = []
        if current:
            segments.append(current)
    return segments


def tokenize(text, min_length=4, stopwords=None):
    """Lowercase word tokens, stripped of stopwords and short words."""
    if not text:
        return []
    sw = stopwords if stopwords is not None else STOPWORDS
    words = [w.lower().strip("-'") for w in _WORD_RE.findall(text)]
    return [w for w in words if len(w) >= min_length and w and w not in sw and not w.isdigit()]


def _words_and_bigrams(text, min_length, stopwords):
    sw = stopwords if stopwords is not None else STOPWORDS
    words, bigrams = [], []
    for seg in _segments(text or '', min_length, sw):
        words.extend(seg)
        bigrams.extend(f'{a} {b}' for a, b in zip(seg, seg[1:]))
    return words, bigrams


def top_terms_for_document(text, max_terms=3, min_length=4, stopwords=None):
    """
    Rank candidate terms within a single document (title/summary).

    Adjacent-word bigrams get a meaningful boost over lone unigrams, since
    two-word phrases ("supply chain", "carbon capture") are usually more
    informative than either word alone. Bigrams are only formed from words
    that were truly adjacent (see _segments). Ties are broken by first-
    occurrence position (earlier = more likely to be the actual subject,
    especially since titles are prepended), NOT by string length - preferring
    the longest string on a tie tends to surface incidental noise phrases
    ("next infrastructure") over the real 2-word subject ("supply chain")
    whenever everything in a short document only appears once.
    """
    words, bigrams = _words_and_bigrams(text, min_length, stopwords)
    if not words:
        return []

    first_seen = {}
    for i, w in enumerate(words):
        first_seen.setdefault(w, i)
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


def _phrase_re(phrase):
    return re.compile(r'(?<![a-z0-9])' + re.escape(phrase) + r'(?![a-z0-9])', re.IGNORECASE)


def strip_hype_phrases(text, extra_phrases=()):
    """Replace multi-word hype phrases with a clause boundary so they can't
    surface as topic bigrams ("changes everything")."""
    if not text:
        return ''
    for phrase in list(HYPE_LANGUAGE_PHRASES) + [p for p in extra_phrases if ' ' in p]:
        text = _phrase_re(phrase.lower().strip()).sub(' \n ', text)
    return text


def hype_language_hits(text, extra_terms=None):
    """
    Promotional/clickbait words and phrases present in text, sorted and
    de-duplicated. extra_terms extends the built-in lexicon (single words or
    multi-word phrases, case-insensitive).
    """
    if not text:
        return []
    words = {w.lower().strip("-'") for w in _TOKEN_RE.findall(text)}

    hits = {w for w in words if w in HYPE_LANGUAGE_WORDS}
    phrases = list(HYPE_LANGUAGE_PHRASES)
    for term in extra_terms or []:
        term = term.lower().strip()
        if not term:
            continue
        if ' ' in term:
            phrases.append(term)
        elif term in words:
            hits.add(term)
    for phrase in phrases:
        if _phrase_re(phrase).search(text):
            hits.add(phrase)
    return sorted(hits)


def document_term_set(text, min_length=4, stopwords=None):
    """Unique unigrams and bigrams in one document, for corpus-level
    document-frequency counting.

    Bigrams are included so HypeTermAgent's snapshot captures the same
    two-word phrases that TopicExtractAgent emits as topic_terms. Without
    bigrams, a phrase like 'agent skills' could slip past the hype check
    even when both constituent words individually fail to rank in the top-N
    unigrams — the phrase-level signal is missed entirely.
    """
    words, bigrams = _words_and_bigrams(text, min_length, stopwords)
    return set(words) | set(bigrams)


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
