"""Transcripts as INPUT: SRT, WebVTT, Praat TextGrid, word-timed JSON and plain
text read into timed segments, and a known text matched to a transcriber's words.

Every package in the fleet writes subtitles (:mod:`an.captions`, ``mixing.srt``,
scribed's ``Transcript.srt``); this module is the reading direction, for a
performer's recording that arrives with its words already written down. Three
shapes come in:

- **timed segments** — SRT, WebVTT, a word-timed JSON, a TextGrid: each line
  of dialogue has a start and an end in the recording, so the take can be cut
  at them with no model at all;
- **plain text** — the lines, one per line, optionally ``speaker: text`` (the
  ``scene.md`` grammar). No times: either each line is its own audio file, or
  a transcriber's timed words are matched to the text (:func:`align_words`);
- **a transcriber's result** — any object shaped like scribed's ``Transcript``
  (segments with ``text``/``start``/``end``/``speaker``/``words``), read by
  :func:`from_transcript_object`.

All times are seconds from the start of the recording they describe.

>>> segs = parse_transcript("1\\n00:00:01,000 --> 00:00:02,500\\ncarl: Hello there.\\n\\n"
...                         "2\\n00:00:03,000 --> 00:00:03,800\\nned: Hi.\\n")
>>> [(s.speaker, s.text, s.start, s.end) for s in segs]
[('carl', 'Hello there.', 1.0, 2.5), ('ned', 'Hi.', 3.0, 3.8)]
>>> aligned = align_words(["Hello", "there,", "friend"],
...                       [("hello", 0.5, 0.9), ("there", 0.9, 1.2), ("fred", 1.3, 1.6)])
>>> aligned.words
[('Hello', 0.5, 0.9), ('there,', 0.9, 1.2), ('friend', 1.3, 1.6)]
>>> aligned.matched, aligned.total
(2, 3)
"""

from __future__ import annotations

import difflib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "FORMATS",
    "TranscriptSegment",
    "AlignedWords",
    "detect_format",
    "parse_transcript",
    "parse_srt",
    "parse_vtt",
    "parse_plain",
    "parse_json",
    "parse_textgrid",
    "from_transcript_object",
    "parse_timestamp",
    "normalize_tokens",
    "normalize_text",
    "align_words",
    "segment_lines",
    "cut_spans",
    "rebase_words",
]

#: One word's slice in time, ``(text, start_s, end_s)`` — ``an.audio.lipsync.WordTiming``.
WordTiming = tuple[str, float, float]

#: The transcript formats read here, in detection order.
FORMATS: tuple[str, ...] = ("vtt", "textgrid", "json", "srt", "plain")

#: File suffixes that name a format outright.
_SUFFIX_FORMATS: dict[str, str] = {
    ".srt": "srt",
    ".vtt": "vtt",
    ".webvtt": "vtt",
    ".textgrid": "textgrid",
    ".json": "json",
    ".txt": "plain",
    ".md": "plain",
}

#: Silence kept on each side of a cut line, seconds (the performer's breath,
#: not the gap: the gap becomes the next line's ``pause``).
DFLT_CUT_PAD_S: float = 0.05

_TIME_RE = re.compile(
    r"^\s*(?:(?P<h>\d+):)?(?P<m>\d{1,2}):(?P<s>\d{1,2})(?:[.,](?P<ms>\d{1,3}))?\s*$"
)
_SECONDS_RE = re.compile(r"^\s*(?P<s>\d+(?:\.\d*)?|\.\d+)\s*s?\s*$")
_ARROW_RE = re.compile(r"^\s*(?P<a>[^\s]+)\s+-->\s+(?P<b>[^\s]+)(?P<rest>.*)$")
_SRT_CUE_RE = re.compile(
    r"\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}\s+-->\s+\d{1,2}:\d{2}:\d{2}[,.]\d{1,3}"
)
#: ``speaker: text`` — the same speaker shape as a ``scene.md`` dialogue line.
_SPEAKER_RE = re.compile(r"^\s*(?P<speaker>[\w-]+)\s*:\s*(?P<text>.*)$")
_VTT_VOICE_RE = re.compile(r"<v(?:\.[^\s>]*)?\s+(?P<name>[^>]+)>")
_TAG_RE = re.compile(r"<[^>]+>")
_TOKEN_RE = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """One spoken line of a transcript: its text, and when and who, if known.

    ``start``/``end`` are seconds from the recording's start, ``None`` for an
    untimed (plain) transcript; ``words`` are the segment's own word timings
    when the format carries them (word JSON, TextGrid), else ``None``.
    """

    text: str
    start: float | None = None
    end: float | None = None
    speaker: str | None = None
    words: tuple[WordTiming, ...] | None = None

    @property
    def timed(self) -> bool:
        """Whether both ``start`` and ``end`` are known."""
        return self.start is not None and self.end is not None


@dataclass(frozen=True, slots=True)
class AlignedWords:
    """:func:`align_words`'s result: the reference words timed, and how many
    of them a transcribed word actually anchored (the rest are interpolated)."""

    words: list[WordTiming]
    matched: int
    total: int

    @property
    def coverage(self) -> float:
        """The share of reference words anchored by a transcribed word, 0..1."""
        return self.matched / self.total if self.total else 1.0


# --- reading ------------------------------------------------------------------


def detect_format(text: str, *, suffix: str = "") -> str:
    """Which of :data:`FORMATS` ``text`` is, by its file suffix first, then its content.

    >>> detect_format("WEBVTT\\n\\n00:01.000 --> 00:02.000\\nhi")
    'vtt'
    >>> detect_format("1\\n00:00:01,000 --> 00:00:02,000\\nhi"), detect_format("hi there")
    ('srt', 'plain')
    >>> detect_format('{"segments": []}'), detect_format("", suffix=".TextGrid")
    ('json', 'textgrid')
    """
    fmt = _SUFFIX_FORMATS.get(suffix.lower())
    if fmt is not None:
        return fmt
    head = text.lstrip()
    if head.startswith("WEBVTT"):
        return "vtt"
    if head.startswith('File type = "ooTextFile"') or '"IntervalTier"' in head[:4000]:
        return "textgrid"
    if head[:1] in ("{", "["):
        return "json"
    if _SRT_CUE_RE.search(text):
        return "srt"
    return "plain"


def parse_transcript(
    source: str | Path, *, fmt: str | None = None
) -> list[TranscriptSegment]:
    """Read ``source`` — a path to a transcript file, or the transcript text
    itself — into segments. ``fmt`` (one of :data:`FORMATS`) overrides detection.

    >>> parse_transcript("carl: Hello.\\nned: Hi.")[1]
    TranscriptSegment(text='Hi.', start=None, end=None, speaker='ned', words=None)
    """
    suffix = ""
    text: str
    path = (
        Path(source)
        if isinstance(source, (str, Path)) and len(str(source)) < 4096
        else None
    )
    if path is not None and path.is_file():
        text = path.read_text(encoding="utf-8-sig")
        suffix = path.suffix
    else:
        text = str(source)
    fmt = (fmt or detect_format(text, suffix=suffix)).lower()
    if fmt == "srt":
        return parse_srt(text)
    if fmt == "vtt":
        return parse_vtt(text)
    if fmt == "json":
        return parse_json(json.loads(text))
    if fmt == "textgrid":
        return parse_textgrid(text)
    if fmt == "plain":
        return parse_plain(text)
    raise ValueError(f"unknown transcript format {fmt!r}; known: {FORMATS}")


def parse_timestamp(value: str) -> float:
    """``HH:MM:SS,mmm`` / ``MM:SS.mmm`` / plain seconds → seconds.

    >>> parse_timestamp("00:01:02,500"), parse_timestamp("01:02.5"), parse_timestamp("7.25")
    (62.5, 62.5, 7.25)
    """
    m = _TIME_RE.match(value)
    if m:
        ms = (m.group("ms") or "0").ljust(3, "0")
        return (
            int(m.group("h") or 0) * 3600
            + int(m.group("m")) * 60
            + int(m.group("s"))
            + int(ms) / 1000.0
        )
    m = _SECONDS_RE.match(value)
    if m:
        return float(m.group("s"))
    raise ValueError(f"not a timestamp: {value!r}")


def _speaker_and_text(text: str) -> tuple[str | None, str]:
    """``'carl: Hello'`` → ``('carl', 'Hello')``; a line with no ``speaker:`` prefix keeps ``None``."""
    m = _SPEAKER_RE.match(text)
    if m and m.group("text").strip():
        return m.group("speaker"), m.group("text").strip()
    return None, text.strip()


def _cue_blocks(text: str) -> Iterable[list[str]]:
    block: list[str] = []
    for line in text.splitlines():
        if line.strip():
            block.append(line.rstrip("\r"))
        elif block:
            yield block
            block = []
    if block:
        yield block


def _timed_cue(lines: list[str]) -> TranscriptSegment | None:
    """A cue block (an optional id line, the time line, the text) → a segment."""
    for i, line in enumerate(lines[:2]):
        arrow = _ARROW_RE.match(line)
        if arrow:
            start, end = (
                parse_timestamp(arrow.group("a")),
                parse_timestamp(arrow.group("b")),
            )
            body = " ".join(part.strip() for part in lines[i + 1 :]).strip()
            speaker = None
            voice = _VTT_VOICE_RE.search(body)
            if voice:
                speaker = voice.group("name").strip()
            body = _TAG_RE.sub("", body).strip()
            if speaker is None:
                speaker, body = _speaker_and_text(body)
            return TranscriptSegment(text=body, start=start, end=end, speaker=speaker)
    return None


def parse_srt(text: str) -> list[TranscriptSegment]:
    """SubRip cues → timed segments; a ``speaker:`` prefix names the speaker.

    >>> parse_srt("1\\n00:00:00,500 --> 00:00:01,000\\nHi\\nthere\\n")
    [TranscriptSegment(text='Hi there', start=0.5, end=1.0, speaker=None, words=None)]
    """
    out = []
    for block in _cue_blocks(text):
        cue = _timed_cue(block)
        if cue is not None and cue.text:
            out.append(cue)
    return out


def parse_vtt(text: str) -> list[TranscriptSegment]:
    """WebVTT cues → timed segments; ``<v Name>`` or a ``speaker:`` prefix names the speaker.

    >>> parse_vtt("WEBVTT\\n\\n00:01.000 --> 00:02.000\\n<v Carl>Hello</v>\\n")
    [TranscriptSegment(text='Hello', start=1.0, end=2.0, speaker='Carl', words=None)]
    """
    out = []
    for block in _cue_blocks(text):
        if block[0].startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        cue = _timed_cue(block)
        if cue is not None and cue.text:
            out.append(cue)
    return out


def parse_plain(text: str) -> list[TranscriptSegment]:
    """One non-empty line per segment, untimed; ``speaker: text`` names the speaker.

    >>> [s.speaker for s in parse_plain("carl: Hi.\\n\\nJust a line.\\n")]
    ['carl', None]
    """
    out = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        speaker, body = _speaker_and_text(line)
        if body:
            out.append(TranscriptSegment(text=body, speaker=speaker))
    return out


def _number(obj: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in obj and obj[key] is not None:
            value = float(obj[key])
            return value / 1000.0 if key.endswith("_ms") else value
    return None


def _word_from(item: Any) -> WordTiming | None:
    if isinstance(item, Mapping):
        text = item.get("text", item.get("word"))
        start, end = _number(item, "start", "start_ms"), _number(item, "end", "end_ms")
    elif isinstance(item, Sequence) and len(item) == 3 and not isinstance(item, str):
        text, start, end = item[0], float(item[1]), float(item[2])
    else:
        return None
    if text is None or start is None or end is None:
        return None
    return (str(text), float(start), float(end))


def parse_json(obj: Any) -> list[TranscriptSegment]:
    """A word-timed JSON → segments. Accepted: ``{"segments": [...]}`` or a list
    of segments, each ``{"text", "start", "end", "speaker", "words": [{"text"|"word",
    "start", "end"}, ...]}`` (``start_ms``/``end_ms`` are read too, and a word may
    be a ``[text, start, end]`` list); or a bare list of words, read as one segment.

    >>> segs = parse_json({"segments": [{"speaker": "carl", "words": [
    ...     {"word": "Hello", "start": 0.5, "end": 0.9}, ["there", 0.9, 1.2]]}]})
    >>> segs[0].text, segs[0].start, segs[0].end, segs[0].words
    ('Hello there', 0.5, 1.2, (('Hello', 0.5, 0.9), ('there', 0.9, 1.2)))
    """
    if isinstance(obj, Mapping):
        items = obj.get("segments")
        if items is None:
            items = obj.get("words")
            if items is None:
                raise ValueError(
                    "a transcript JSON needs a 'segments' (or 'words') list"
                )
            items = [{"words": items}]
    else:
        items = list(obj)
    if items and all(_word_from(it) is not None for it in items):
        items = [{"words": items}]  # a bare list of words: one line
    out = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError(f"a transcript segment must be an object, got {item!r}")
        words = tuple(w for w in (_word_from(x) for x in item.get("words") or ()) if w)
        text = item.get("text")
        if text is None:
            text = " ".join(w[0] for w in words)
        start = _number(item, "start", "start_ms")
        end = _number(item, "end", "end_ms")
        if words:
            start = words[0][1] if start is None else start
            end = words[-1][2] if end is None else end
        speaker = item.get("speaker")
        if (
            speaker is None
            and words is not None
            and isinstance(item.get("words"), list)
        ):
            speaker = next(
                (
                    w.get("speaker")
                    for w in item["words"]
                    if isinstance(w, Mapping) and w.get("speaker")
                ),
                None,
            )
        speaker_, text = (
            (speaker, str(text).strip()) if speaker else _speaker_and_text(str(text))
        )
        if text:
            out.append(
                TranscriptSegment(
                    text=text,
                    start=start,
                    end=end,
                    speaker=str(speaker_) if speaker_ else None,
                    words=words or None,
                )
            )
    return out


_TG_TIER_RE = re.compile(
    r'class\s*=\s*"IntervalTier"\s*\n\s*name\s*=\s*"(?P<name>[^"]*)"', re.S
)
_TG_INTERVAL_RE = re.compile(
    r'xmin\s*=\s*(?P<a>[\d.]+)\s*\n\s*xmax\s*=\s*(?P<b>[\d.]+)\s*\n\s*text\s*=\s*"(?P<t>(?:[^"]|"")*)"'
)
_TG_SHORT_TIER_RE = re.compile(r'"IntervalTier"\s*\n\s*"(?P<name>[^"]*)"\s*\n')
_TG_SHORT_INTERVAL_RE = re.compile(
    r'(?P<a>\d+(?:\.\d+)?)\s*\n\s*(?P<b>\d+(?:\.\d+)?)\s*\n\s*"(?P<t>(?:[^"]|"")*)"'
)
#: Tier names whose intervals are the LINES (one segment each), by preference.
_TG_LINE_TIERS: tuple[str, ...] = (
    "utterances",
    "utterance",
    "lines",
    "line",
    "sentences",
    "sentence",
    "segments",
)
#: Tier names whose intervals are the WORDS, by preference.
_TG_WORD_TIERS: tuple[str, ...] = ("words", "word", "ortho", "orthography")


def _textgrid_tiers(text: str) -> dict[str, list[tuple[float, float, str]]]:
    """``{tier name: [(xmin, xmax, text), ...]}`` for every interval tier, long or short format."""
    tiers: dict[str, list[tuple[float, float, str]]] = {}
    long_form = list(_TG_TIER_RE.finditer(text))
    heads = long_form if long_form else list(_TG_SHORT_TIER_RE.finditer(text))
    interval_re = _TG_INTERVAL_RE if long_form else _TG_SHORT_INTERVAL_RE
    for i, head in enumerate(heads):
        chunk = text[
            head.end() : heads[i + 1].start() if i + 1 < len(heads) else len(text)
        ]
        intervals = [
            (
                float(m.group("a")),
                float(m.group("b")),
                m.group("t").replace('""', '"').strip(),
            )
            for m in interval_re.finditer(chunk)
        ]
        if not long_form:
            intervals = (
                intervals[1:]
                if intervals and intervals[0][2] == "" and len(intervals) > 1
                else intervals
            )
        tiers[head.group("name")] = intervals
    return tiers


def parse_textgrid(text: str) -> list[TranscriptSegment]:
    """A Praat TextGrid (long or short form, as a forced aligner writes it) → segments.

    The words come from a tier named ``words`` (else the first interval tier);
    a tier named ``utterances``/``lines``/``sentences`` gives one segment per
    non-empty interval, with the words inside it; without one, the whole grid
    is one segment.

    >>> tg = ('File type = "ooTextFile"\\nObject class = "TextGrid"\\nxmin = 0\\nxmax = 2\\n'
    ...       'tiers? <exists>\\nsize = 1\\nitem []:\\n    item [1]:\\n        class = "IntervalTier"\\n'
    ...       '        name = "words"\\n        xmin = 0\\n        xmax = 2\\n        intervals: size = 3\\n'
    ...       '        intervals [1]:\\n            xmin = 0\\n            xmax = 0.5\\n            text = ""\\n'
    ...       '        intervals [2]:\\n            xmin = 0.5\\n            xmax = 0.9\\n            text = "hello"\\n'
    ...       '        intervals [3]:\\n            xmin = 0.9\\n            xmax = 1.3\\n            text = "there"\\n')
    >>> parse_textgrid(tg)
    [TranscriptSegment(text='hello there', start=0.5, end=1.3, speaker=None, words=(('hello', 0.5, 0.9), ('there', 0.9, 1.3)))]
    """
    tiers = _textgrid_tiers(text)
    if not tiers:
        raise ValueError("no IntervalTier found in the TextGrid")
    lowered = {name.lower(): name for name in tiers}
    word_tier = next(
        (lowered[n] for n in _TG_WORD_TIERS if n in lowered), next(iter(tiers))
    )
    words = [
        (t, a, b)
        for a, b, t in tiers[word_tier]
        if t and t not in ("sil", "sp", "<unk>")
    ]
    line_tier = next((lowered[n] for n in _TG_LINE_TIERS if n in lowered), None)
    if line_tier is None:
        if not words:
            return []
        return [
            TranscriptSegment(
                text=" ".join(w[0] for w in words),
                start=words[0][1],
                end=words[-1][2],
                words=tuple(words),
            )
        ]
    out = []
    for a, b, t in tiers[line_tier]:
        if not t:
            continue
        inside = tuple(w for w in words if w[1] >= a - 1e-6 and w[2] <= b + 1e-6)
        speaker, body = _speaker_and_text(t)
        out.append(
            TranscriptSegment(
                text=body, start=a, end=b, speaker=speaker, words=inside or None
            )
        )
    return out


def from_transcript_object(obj: Any) -> list[TranscriptSegment]:
    """A transcriber's result — scribed's ``Transcript`` or anything shaped like
    it (iterable segments with ``text``, ``start``, ``end``, ``speaker`` and
    ``words`` having ``text``/``start``/``end``) — as segments.

    >>> from types import SimpleNamespace as NS
    >>> t = [NS(text="Hi there", start=0.2, end=0.9, speaker="A",
    ...         words=[NS(text="Hi", start=0.2, end=0.4), NS(text="there", start=0.5, end=0.9)])]
    >>> from_transcript_object(t)[0].words
    (('Hi', 0.2, 0.4), ('there', 0.5, 0.9))
    """
    if isinstance(obj, (list, tuple)) and all(
        isinstance(s, TranscriptSegment) for s in obj
    ):
        return list(obj)
    segments = getattr(obj, "segments", obj)
    out = []
    for seg in segments:
        if isinstance(seg, TranscriptSegment):
            out.append(seg)
            continue
        words = tuple(
            (str(w.text), float(w.start), float(w.end))
            for w in (getattr(seg, "words", None) or ())
            if getattr(w, "start", None) is not None
            and getattr(w, "end", None) is not None
        )
        text = str(getattr(seg, "text", "") or " ".join(w[0] for w in words)).strip()
        if not text:
            continue
        start = getattr(seg, "start", None)
        end = getattr(seg, "end", None)
        speaker = getattr(seg, "speaker", None)
        out.append(
            TranscriptSegment(
                text=text,
                start=(
                    float(start)
                    if start is not None
                    else (words[0][1] if words else None)
                ),
                end=(
                    float(end) if end is not None else (words[-1][2] if words else None)
                ),
                speaker=str(speaker) if speaker else None,
                words=words or None,
            )
        )
    return out


# --- matching words ------------------------------------------------------------


def normalize_tokens(text: str) -> list[str]:
    """The words of ``text`` for matching: case-folded, punctuation dropped,
    an apostrophe inside a word kept.

    >>> normalize_tokens("Hello, there — it's ME!")
    ['hello', 'there', "it's", 'me']
    """
    return _TOKEN_RE.findall(text.casefold())


def normalize_text(text: str) -> str:
    """:func:`normalize_tokens` joined by single spaces (what two lines are compared by)."""
    return " ".join(normalize_tokens(text))


def align_words(
    reference: Sequence[str],
    timed: Sequence[WordTiming],
    *,
    bounds: tuple[float, float] | None = None,
) -> AlignedWords:
    """Time the ``reference`` words (the text the performer was meant to say) by a
    transcriber's ``timed`` words of the same audio.

    Reference words that a transcribed word matches (same normalized form, in
    sequence — :class:`difflib.SequenceMatcher`) take that word's times. A run
    the transcriber heard differently (``friend`` heard as ``fred``) is spread
    over the misheard words' span; a run it did not hear at all is spread over
    the gap to the next anchor, in proportion to word length — so a misheard or
    dropped word still gets a plausible slot. ``bounds`` (``(start, end)`` of
    the audio) time the ends when no anchor does; without it the first and last
    transcribed words do. Words come back in reference order with
    non-decreasing starts.

    >>> align_words(["I", "did", "NOT", "ask"], [("i", 0.0, 0.1), ("did", 0.1, 0.3), ("ask", 0.6, 0.9)]).words
    [('I', 0.0, 0.1), ('did', 0.1, 0.3), ('NOT', 0.3, 0.6), ('ask', 0.6, 0.9)]
    """
    ref = [normalize_text(w) for w in reference]
    asr = [normalize_text(w[0]) for w in timed]
    first = bounds[0] if bounds else (float(timed[0][1]) if timed else 0.0)
    last = bounds[1] if bounds else (float(timed[-1][2]) if timed else 0.0)
    out: list[WordTiming] = []
    matched = 0
    prev_end = first

    def spread(indices: range, lo: float, hi: float) -> None:
        nonlocal prev_end
        lo = max(lo, prev_end)
        hi = max(hi, lo)
        weights = [max(1, len(ref[k]) or len(reference[k])) for k in indices]
        total = float(sum(weights)) or 1.0
        t = lo
        for k, w in zip(indices, weights):
            length = (hi - lo) * (w / total)
            out.append((reference[k], round(t, 6), round(t + length, 6)))
            t += length
        prev_end = hi

    opcodes = difflib.SequenceMatcher(None, ref, asr, autojunk=False).get_opcodes()
    for n, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            for k in range(i2 - i1):
                start, end = float(timed[j1 + k][1]), float(timed[j1 + k][2])
                start = max(start, prev_end)
                out.append((reference[i1 + k], start, max(end, start)))
                prev_end = max(end, start)
                matched += 1
        elif tag == "replace":
            spread(range(i1, i2), float(timed[j1][1]), float(timed[j2 - 1][2]))
        elif tag == "delete":
            # Not heard at all: the gap up to the next transcribed word, or the end.
            nxt = next(
                (float(timed[op[3]][1]) for op in opcodes[n + 1 :] if op[3] < op[4]),
                last,
            )
            spread(range(i1, i2), prev_end, nxt)
        else:  # "insert": words the transcriber heard that the text lacks — time passes
            prev_end = max(prev_end, float(timed[j2 - 1][2])) if j2 > j1 else prev_end
    return AlignedWords(words=out, matched=matched, total=len(ref))


def segment_lines(
    lines: Sequence[TranscriptSegment],
    timed: Sequence[WordTiming],
    *,
    bounds: tuple[float, float] | None = None,
) -> list[TranscriptSegment]:
    """Time untimed ``lines`` (a plain transcript) by a transcriber's ``timed``
    words of the whole recording: the lines' words are aligned as one text
    (:func:`align_words`) and handed back per line, each line spanning its
    first word's start to its last word's end, with its own ``words``.

    >>> lines = parse_plain("carl: Hello there.\\nned: Hi.")
    >>> timed = [("hello", 0.5, 0.9), ("there", 0.9, 1.3), ("hi", 2.0, 2.3)]
    >>> [(s.speaker, s.start, s.end, len(s.words)) for s in segment_lines(lines, timed)]
    [('carl', 0.5, 1.3, 2), ('ned', 2.0, 2.3, 1)]
    """
    per_line = [[tok for tok in _TOKEN_RE.findall(line.text)] for line in lines]
    flat = [tok for toks in per_line for tok in toks]
    aligned = align_words(flat, timed, bounds=bounds).words
    out = []
    cursor = 0
    for line, toks in zip(lines, per_line):
        words = tuple(aligned[cursor : cursor + len(toks)])
        cursor += len(toks)
        if not words:
            continue  # nothing to say: no slice of the recording is its own
        out.append(
            TranscriptSegment(
                text=line.text,
                start=words[0][1],
                end=words[-1][2],
                speaker=line.speaker,
                words=words,
            )
        )
    return out


def cut_spans(
    segments: Sequence[TranscriptSegment],
    *,
    total: float,
    pad_s: float = DFLT_CUT_PAD_S,
) -> list[tuple[float, float]]:
    """Where to cut the recording for each timed segment: its span widened by
    ``pad_s`` on each side, never past the midpoint to its neighbour or the
    recording's ends (``total`` seconds).

    >>> segs = [TranscriptSegment("a", 1.0, 2.0), TranscriptSegment("b", 2.04, 3.0)]
    >>> cut_spans(segs, total=3.02)
    [(0.95, 2.02), (2.02, 3.02)]
    """
    spans = []
    for i, seg in enumerate(segments):
        if not seg.timed:
            raise ValueError(f"segment {seg.text!r} has no times to cut at")
        lo = max(0.0, seg.start - pad_s)
        hi = min(total, seg.end + pad_s)
        if i > 0 and segments[i - 1].timed:
            lo = max(lo, (segments[i - 1].end + seg.start) / 2.0)
        if i + 1 < len(segments) and segments[i + 1].timed:
            hi = min(hi, (seg.end + segments[i + 1].start) / 2.0)
        spans.append((round(lo, 6), round(max(hi, lo), 6)))
    return spans


def rebase_words(
    words: Iterable[WordTiming] | None, start: float
) -> tuple[WordTiming, ...] | None:
    """``words`` re-timed from ``start`` (a cut's start): the clip-relative words a line keeps.

    >>> rebase_words([("hi", 1.0, 1.4)], 0.95)
    (('hi', 0.05, 0.45),)
    """
    if words is None:
        return None
    out = []
    for text, a, b in words:
        a2 = max(0.0, round(a - start, 6))
        out.append((text, a2, max(a2, round(b - start, 6))))
    return tuple(out)
