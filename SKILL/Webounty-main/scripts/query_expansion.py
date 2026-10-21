"""Small, auditable bilingual query expansion; no model or network is required.

Translations add recall candidates, never evidence or capability equivalence.
Only natural-language text is expanded; quoted literals, paths and identifiers
remain the responsibility of the original lexical query.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import re
import unicodedata


# Deliberately avoid identity, authorization and capability-type equivalences.
# Each group spends at most this weight across its additional lexical terms.
_GROUP_WEIGHT = 0.3
_GROUPS = (
    ("导出", "export"),
    ("下载", "download"),
    ("上传", "upload"),
    ("租户", "tenant", "tenants"),
    ("报告", "report", "reports"),
    ("回调", "callback"),
    ("重定向", "redirect"),
    ("缓存", "cache"),
    ("令牌", "token"),
    ("会话", "session"),
)
_PROTECTED = re.compile(
    # Quoted literals (including escaped quotes) and inline/fenced code.
    r'"(?:\\.|[^"\\\r\n])*"|\'(?:\\.|[^\'\\\r\n])*\''
    r'|`[^`]*`|“[^”]*”|‘[^’]*’|「[^」]*」|『[^』]*』'
    # URLs, Unix/Windows and relative paths; include non-ASCII path segments.
    r'|[a-zA-Z][a-zA-Z0-9+.-]*://[^\s\"\'`<>]+'
    r'|(?:[a-zA-Z]:)?[/\\][^\s\"\'`<>]+'
    r'|[\w.$-]+(?:[/\\][^\s\"\'`<>]+)+'
    # Dotted, snake_case and kebab-case identifiers.
    r'|(?<![\w$])[a-zA-Z_$][a-zA-Z0-9_$]*(?:[._-][a-zA-Z0-9_$]+)+'
    # camelCase/PascalCase and identifiers containing numeric suffixes.
    r'|(?<![\w$])(?:[a-z]+[A-Z][a-zA-Z0-9_]*'
    r'|[A-Z][a-z]+[A-Z][a-zA-Z0-9_]*|[a-zA-Z]+[0-9][a-zA-Z0-9_]*)'
)


def query_parts(query: str):
    """Yield normalized (text, is_literal) spans shared by query consumers."""
    text = unicodedata.normalize("NFKC", query)
    start = 0
    for match in _PROTECTED.finditer(text):
        yield text[start:match.start()], False
        yield match.group(), True
        start = match.end()
    yield text[start:], False


def _mentions(text: str, phrase: str) -> bool:
    if phrase.isascii():
        # Python's Unicode \b would prevent matching English beside Chinese.
        return re.search(r"(?<![a-z0-9_$])" + re.escape(phrase)
                         + r"(?![a-z0-9_$])", text) is not None
    return phrase in text


def expand_query(
    query: str,
    tokenize: Callable[[str], Iterable[str]],
    original_terms: set[str],
) -> dict[str, float]:
    """Return new, discounted terms without mutating or recursively expanding.

    Normalize like the lexical tokenizer, but detect code identifiers before
    case folding. Negations and conditions in the original query are untouched;
    callers must retain their original terms and their ordinary ranking weight.
    """
    text = " ".join(text for text, literal in query_parts(query) if not literal).casefold()
    expanded: dict[str, float] = {}
    for group in _GROUPS:
        if not any(_mentions(text, phrase) for phrase in group):
            continue
        additions = {term for phrase in group for term in tokenize(phrase)} - original_terms
        if additions:
            weight = _GROUP_WEIGHT / len(additions)
            for term in sorted(additions):
                expanded[term] = max(expanded.get(term, 0.0), weight)
    return expanded
