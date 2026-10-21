"""Streaming local evidence I/O. Buffer sizes control memory, never corpus size."""

from __future__ import annotations

import codecs
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import unicodedata


BUFFER_BYTES = 1024 * 1024
TEXT_CHUNK_BYTES = 64 * 1024
TEXT_OVERLAP_BYTES = 256


def fingerprint(path):
    path = Path(path)
    stat = path.stat()
    return (str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino)


def scan(path):
    before = fingerprint(path)
    checksum, size = hashlib.sha256(), 0
    decoder = codecs.getincrementaldecoder("utf-8")()
    text = True
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(BUFFER_BYTES), b""):
            checksum.update(data)
            size += len(data)
            if text:
                try:
                    decoder.decode(data)
                    text = b"\0" not in data
                except UnicodeError:
                    text = False
    if text:
        try:
            decoder.decode(b"", final=True)
        except UnicodeError:
            text = False
    if before != fingerprint(path):
        raise ValueError("source changed while reading")
    return {"sha256": checksum.hexdigest(), "bytes": size,
            "text_encoding": "utf-8" if text else None, "fingerprint": before}


@dataclass
class FileCopy:
    """A proposed immutable file, copied only after publication validation."""

    source: Path
    metadata: dict

    def write_to(self, stream):
        checksum, size = hashlib.sha256(), 0
        with self.source.open("rb") as source:
            for data in iter(lambda: source.read(BUFFER_BYTES), b""):
                checksum.update(data)
                size += len(data)
                stream.write(data)
        if checksum.hexdigest() != self.metadata["sha256"] or size != self.metadata["bytes"]:
            raise ValueError("source changed before publication; submit the current source")


_IDENTIFIER_CHAR = re.compile(r"[a-z0-9_./-]+", re.I)


def _identifier_char(char):
    # The lexical index normalizes before splitting identifiers. Keep combining
    # marks with their base too, so a window cannot invent an unnormalized term.
    # One compatibility character can expand into several tokens (e.g. ㎧).
    # Conservatively retain the whole atom if any part can join an identifier.
    return bool(_IDENTIFIER_CHAR.search(unicodedata.normalize("NFKC", char))) or unicodedata.combining(char) != 0


def _cjk(char):
    return all("\u3400" <= unit <= "\u9fff" for unit in unicodedata.normalize("NFKC", char))


def _text_tail(text):
    raw = text.encode("utf-8")[-TEXT_OVERLAP_BYTES:]
    while raw and raw[0] & 0xC0 == 0x80:
        raw = raw[1:]
    start = len(text) - len(raw.decode("utf-8"))
    # A complete identifier already appeared in the preceding window. Discard
    # a partial overlap instead of indexing an invented suffix of that word.
    if 0 < start < len(text) and _identifier_char(text[start - 1]):
        while start < len(text) and _identifier_char(text[start]):
            start += 1
    # Chinese is indexed as overlapping bigrams. Keep a two-character ending,
    # or discard an isolated overlap character from an already complete run.
    if 0 < start < len(text) and _cjk(text[start - 1]) and _cjk(text[start]):
        if start + 1 == len(text):
            start -= 1
        elif not _cjk(text[start + 1]):
            start += 1
    return text[start:]


def text_chunks(path):
    """Yield UTF-8 source windows with byte locators, preserving every source byte.

    The overlap is only for raw lexical matching; Wiki judgments stay whole.
    No extracted window is a new independent observation.
    """
    # Hold an unfinished identifier until its boundary, even when it exceeds
    # the target window size. Memory scales with a window plus the longest
    # identifier; long Chinese prose remains a stream of bigram windows.
    tail, pending, offset = "", [], 0
    with Path(path).open("rb") as stream:
        while True:
            data = stream.read(TEXT_CHUNK_BYTES)
            final = not data
            # Finish the last UTF-8 code point before assigning a byte locator.
            while True:
                try:
                    data.decode("utf-8")
                    break
                except UnicodeDecodeError as exc:
                    if exc.reason != "unexpected end of data":
                        raise
                    extra = stream.read(1)
                    if not extra:
                        raise
                    data += extra
            text = data.decode("utf-8")
            cut = len(text)
            if not final:
                while cut and _identifier_char(text[cut - 1]):
                    cut -= 1
                if cut == len(text) and cut and _cjk(text[-1]) and (cut == 1 or not _cjk(text[-2])):
                    cut -= 1
                if cut == 0:
                    pending.append(text)
                    continue
            body = "".join(pending) + text[:cut]
            pending = [text[cut:]]
            if body:
                window = (tail + body).encode("utf-8")
                yield {"offset": offset - len(tail.encode("utf-8")), "length": len(window),
                       "sha256": hashlib.sha256(window).hexdigest()}, tail + body
                offset += len(body.encode("utf-8"))
                tail = _text_tail(tail + body)
            if final:
                break
