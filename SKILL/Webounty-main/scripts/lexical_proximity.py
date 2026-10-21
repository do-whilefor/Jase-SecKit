"""Compact ordered-neighbour signals; no text is stored or treated as evidence."""

from collections import deque
import re
import unicodedata


PREFIX = "\x1f"
_TOKENS = re.compile(r"[a-z0-9_]+(?:[-/.][a-z0-9_]+)*|[\u3400-\u9fff]+", re.I)
_BREAK = re.compile(r"[.!?;。！？；\r\n]")


def pairs(text, allowed=None):
    """Return strongest ordered pair within three positions, inside one sentence.

    Chinese units overlap by one character, matching the lexical bigrams.
    Identifier components are deliberately not separate positions. Repetition
    cannot inflate this signal. Original lexical terms remain fully indexed.
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    recent, found, previous_end = deque(maxlen=3), {}, 0
    for match in _TOKENS.finditer(text):
        if _BREAK.search(text[previous_end:match.start()]):
            recent.clear()
        token = match.group()
        units = ([token[i:i + 2] for i in range(len(token) - 1)]
                 if len(token) > 1 and "\u3400" <= token[0] <= "\u9fff" else [token])
        for unit in units:
            for distance, left in enumerate(reversed(recent), 1):
                if left == unit or (allowed is not None and (left not in allowed or unit not in allowed)):
                    continue
                key = PREFIX + left + PREFIX + unit
                found[key] = max(found.get(key, 0), {1: 4, 2: 2, 3: 1}[distance])
            recent.append(unit)
        previous_end = match.end()
    return found


def lexical_length(counts):
    return sum(count for term, count in counts.items() if not term.startswith(PREFIX))
