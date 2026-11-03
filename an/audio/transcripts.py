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
from itertools import groupby
from pathlib import Path
from typing import Any

__all__ = [
    "FORMATS",
    "TranscriptSegment",
    "AlignedWords",
    "detect_format",
    "parse_transcript",
    "parse_transcript_text",
    "parse_srt",
    "parse_vtt",
    "parse_plain",
    "parse_json",
    "parse_textgrid",
    "textgrid_text",
    "from_transcript_object",
    "parse_timestamp",
    "phone_alphabet_of",
    "ARPABET",
    "IPA",
    "ARPABET_PHONES",
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
    #: The segment's phone timings, ``(phone, start, end)`` as an aligner
    #: writes them (a TextGrid's ``phones`` tier, an#491), else ``None``.
    phones: tuple[WordTiming, ...] | None = None
    #: The alphabet ``phones`` are in (``"arpabet"``, ``"ipa"``) when the
    #: format says it (an#721): Gentle's always ARPAbet, an MFA grid's by its
    #: labels (:func:`phone_alphabet_of`); ``None`` when unknown.
    phone_alphabet: str | None = None

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
    TranscriptSegment(text='Hi.', start=None, end=None, speaker='ned', words=None, phones=None, phone_alphabet=None)
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
    return parse_transcript_text(text, fmt=fmt or detect_format(text, suffix=suffix))


def parse_transcript_text(
    text: str, *, fmt: str | None = None
) -> list[TranscriptSegment]:
    """The transcript ``text`` (never a path: what a store hands back, an#493)
    into segments; ``fmt`` (one of :data:`FORMATS`) overrides detection.

    >>> parse_transcript_text("note", fmt="plain")[0].text
    'note'
    """
    fmt = (fmt or detect_format(text)).lower()
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
    [TranscriptSegment(text='Hi there', start=0.5, end=1.0, speaker=None, words=None, phones=None, phone_alphabet=None)]
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
    [TranscriptSegment(text='Hello', start=1.0, end=2.0, speaker='Carl', words=None, phones=None, phone_alphabet=None)]
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
    A word's ``phones`` as Gentle writes them (durations from its start) become
    the segment's phones, and MFA's JSON (``tiers``) is read by
    :func:`parse_mfa_json` (an#715). In Gentle's JSON (``transcript`` and
    ``words``), a word whose ``case`` is not :data:`GENTLE_SAID_CASE` is
    dropped (an#721); any other JSON keeps every word.

    >>> segs = parse_json({"segments": [{"speaker": "carl", "words": [
    ...     {"word": "Hello", "start": 0.5, "end": 0.9}, ["there", 0.9, 1.2]]}]})
    >>> segs[0].text, segs[0].start, segs[0].end, segs[0].words
    ('Hello there', 0.5, 1.2, (('Hello', 0.5, 0.9), ('there', 0.9, 1.2)))
    """
    if _is_mfa_json(obj):
        return parse_mfa_json(obj)  # the Montreal Forced Aligner's JSON (an#715)
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
    gentle = _is_gentle_json(obj)
    out = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError(f"a transcript segment must be an object, got {item!r}")
        said = [x for x in item.get("words") or () if not gentle or _in_transcript(x)]
        words = tuple(w for w in (_word_from(x) for x in said) if w)
        phones = tuple(p for x in said for p in _gentle_phones(x))
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
                    phones=phones or None,
                    # Gentle's phones are stressless ARPAbet, always (an#721);
                    # another writer's are what their labels show
                    phone_alphabet=(
                        ARPABET if gentle else phone_alphabet_of(p[0] for p in phones)
                    )
                    if phones
                    else None,
                )
            )
    return out


#: A Gentle word's ``case`` when it was found in the transcript AND the audio;
#: ``not-found-in-transcript`` is a disfluency the transcript does not hold
#: ("um"), ``not-found-in-audio`` a word with no time (an#721).
GENTLE_SAID_CASE: str = "success"


def _is_gentle_json(obj: Any) -> bool:
    """Whether ``obj`` is Gentle's JSON: an object with both its ``transcript``
    and its ``words`` (an#721). Only there does a word's ``case`` mean Gentle's.

    >>> _is_gentle_json({"transcript": "hi", "words": []}), _is_gentle_json({"words": []})
    (True, False)
    """
    return isinstance(obj, Mapping) and "transcript" in obj and "words" in obj


def _in_transcript(word: Any) -> bool:
    """Whether a Gentle word belongs to the transcript: any word but one whose
    ``case`` is not :data:`GENTLE_SAID_CASE` (an#721). Read only for a Gentle
    JSON (:func:`_is_gentle_json`); another writer's ``case`` means nothing here.

    >>> [_in_transcript(w) for w in ({"word": "hi"}, {"word": "hi", "case": "success"},
    ...                               {"word": "um", "case": "not-found-in-transcript"})]
    [True, True, False]
    """
    return (
        not isinstance(word, Mapping)
        or word.get("case", GENTLE_SAID_CASE) == GENTLE_SAID_CASE
    )


#: The phone alphabets a reader can report (an#721), as the forced aligner's
#: ``phone_alphabet`` names them (an#637).
ARPABET: str = "arpabet"
IPA: str = "ipa"
#: The 39 ARPAbet phones of the CMU dictionary, without stress digits: every
#: label must be one of them (its stress digit dropped) for the labels to be
#: read as ARPAbet (cutan's ``ARPABET_TO_VISEME`` keys the same set).
ARPABET_PHONES: frozenset[str] = frozenset(
    {
        # vowels
        "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY",
        "OW", "OY", "UH", "UW",
        # consonants
        "B", "CH", "D", "DH", "F", "G", "HH", "JH", "K", "L", "M", "N", "NG",
        "P", "R", "S", "SH", "T", "TH", "V", "W", "Y", "Z", "ZH",
    }
)  # fmt: skip
#: The stress digits an ARPAbet vowel may carry (``AH0``, ``AY1``, ``ER2``).
_ARPABET_STRESS_DIGITS: str = "012"


def _is_one_case(labels: Sequence[str]) -> bool:
    """Whether ``labels`` (stress digits dropped) are all upper or all lower case:
    a SAMPA ``V`` beside a lowercase ``l`` is not ARPAbet.

    >>> _is_one_case(["HH", "AH"]), _is_one_case(["hh", "ah"]), _is_one_case(["l", "V"])
    (True, True, False)
    """
    letters = [x.rstrip(_ARPABET_STRESS_DIGITS) for x in labels]
    return all(x.isupper() for x in letters) or all(x.islower() for x in letters)


def phone_alphabet_of(labels: Iterable[str]) -> str | None:
    """The alphabet aligner phone ``labels`` show, or ``None`` when they show
    none (an#721). :data:`ARPABET` when every label is ASCII, in one letter
    case throughout, and in :data:`ARPABET_PHONES` once its stress digit is
    dropped (cutan's rule for a clip, so its own can be ``phone_alphabet_of(p)
    or "ipa"``); :data:`IPA` when any label is non-ASCII; otherwise unknown,
    and the lip-sync decides it per clip. Silences are not labels.

    >>> phone_alphabet_of(["HH", "AH0", "L"]), phone_alphabet_of(["h", "ə", "l"])
    ('arpabet', 'ipa')
    >>> phone_alphabet_of(["AH", "T"]), phone_alphabet_of(["ai1", "ou3"]) is None
    ('arpabet', True)
    """
    spoken = [x for x in (str(y).strip() for y in labels) if _is_speech(x)]
    if any(not x.isascii() for x in spoken):
        return IPA
    if (
        spoken
        and all(
            x.upper().rstrip(_ARPABET_STRESS_DIGITS) in ARPABET_PHONES for x in spoken
        )
        and _is_one_case(spoken)
    ):
        return ARPABET
    return None


#: Gentle's phones carry their place in the word (``hh_B``: begin, ``_I``
#: inside, ``_E`` end, ``_S`` a one-phone word); the phone is what precedes it.
_GENTLE_POSITION = re.compile(r"_[BIES]$")


def _gentle_phones(word: Any) -> list[WordTiming]:
    """A Gentle word's phones (``{"phones": [{"phone", "duration"}], "start"}``),
    timed from the word's start one after another; ``[]`` for any other shape.

    >>> _gentle_phones({"word": "hi", "start": 1.0, "end": 1.3, "phones": [
    ...     {"phone": "hh_B", "duration": 0.1}, {"phone": "ay_E", "duration": 0.2}]})
    [('HH', 1.0, 1.1), ('AY', 1.1, 1.3)]
    """
    phones = word.get("phones") if isinstance(word, Mapping) else None
    start = _number(word, "start", "start_ms") if isinstance(word, Mapping) else None
    if not isinstance(phones, list) or start is None:
        return []
    out, t = [], float(start)
    for p in phones:
        if not isinstance(p, Mapping) or p.get("duration") is None:
            return []
        label = _GENTLE_POSITION.sub("", str(p.get("phone", ""))).upper()
        end = t + float(p["duration"])
        if label and _is_speech(label):
            out.append((label, round(t, 6), round(end, 6)))
        t = end
    return out


def _is_mfa_json(obj: Any) -> bool:
    """Whether ``obj`` is MFA's JSON: ``tiers`` of ``{"entries": [...]}``, and
    no ``segments``/``words`` of its own (which another writer's would be)."""
    if not isinstance(obj, Mapping) or "segments" in obj or "words" in obj:
        return False
    tiers = obj.get("tiers")
    return (
        isinstance(tiers, Mapping)
        and bool(tiers)
        and all(
            isinstance(t, Mapping) and isinstance(t.get("entries"), list)
            for t in tiers.values()
        )
    )


def parse_mfa_json(obj: Mapping[str, Any]) -> list[TranscriptSegment]:
    """The Montreal Forced Aligner's JSON (``--output_format json``):
    ``{"tiers": {name: {"entries": [[start, end, label], ...]}}}`` read as its
    TextGrid is (:func:`segments_from_tiers`), words and phones.

    >>> parse_mfa_json({"tiers": {"take - words": {"entries": [[0.5, 0.9, "hello"]]},
    ...                           "take - phones": {"entries": [[0.5, 0.6, "HH"], [0.6, 0.9, "AH0"]]}}})[0].phones
    (('HH', 0.5, 0.6), ('AH0', 0.6, 0.9))
    """
    tiers: dict[str, list[tuple[float, float, str]]] = {}
    for name, tier in (obj.get("tiers") or {}).items():
        if not isinstance(tier, Mapping):
            continue
        entries = []
        for entry in tier.get("entries") or []:
            if not isinstance(entry, (list, tuple)) or len(entry) != 3:
                raise ValueError(
                    f"MFA JSON tier {name!r}: an entry is [start, end, label], got {entry!r}"
                )
            a, b, label = entry
            entries.append((float(a), float(b), str(label)))
        tiers[str(name)] = sorted(entries)  # MFA's JSON writer does not sort
    return segments_from_tiers(tiers)


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
#: The names a forced aligner gives its phone tier (Montreal Forced Aligner:
#: ``phones``; others ``phonemes``), read beside the words (an#491).
_TG_PHONE_TIERS: tuple[str, ...] = ("phones", "phone", "phonemes", "phoneme", "mau")
#: Every tier name read above (lower case): MFA's ``"<speaker> - <tier>"``
#: names a speaker only when ``<tier>`` is one of these (an#721), so a tier
#: called ``"notes - draft"`` is not a speaker's.
_TG_KNOWN_TIERS: frozenset[str] = frozenset(
    _TG_LINE_TIERS + _TG_WORD_TIERS + _TG_PHONE_TIERS
)
#: MFA's separator between a speaker and its tier's name (``"carl - words"``).
_TG_SPEAKER_SEP: str = " - "
#: How far (seconds) a timing may stick out of a span and still be inside it:
#: an aligner's float times for one boundary differ in the last digits.
_SPAN_EPS_S: float = 1e-6
#: Interval labels that are silence, not speech (compared lower-case): dropped
#: from words and phones, as is any label in ``<…>``, ``[…]`` or ``+…+``
#: (WebMAUS's ``<p:>``, a ``+breath+``, a ``[noise]``). ``spn`` is MFA's
#: unknown word, ``oov`` Gentle's (an#715).
_TG_SILENCE: frozenset[str] = frozenset({"sil", "sp", "spn", "oov", ""})
_TG_BRACKETS: tuple[tuple[str, str], ...] = (("<", ">"), ("[", "]"), ("+", "+"))


def _is_speech(label: str) -> bool:
    """Whether a TextGrid interval label is speech (not silence or a marker).

    >>> [_is_speech(x) for x in ("hello", "SIL", "<p:>", "+breath+", "[noise]", "AH0")]
    [True, False, False, False, False, True]
    """
    text = label.strip()
    if text.lower() in _TG_SILENCE:
        return False
    return not any(text.startswith(a) and text.endswith(b) for a, b in _TG_BRACKETS)


def _tier_named(tiers: Mapping[str, Any], names: Sequence[str]) -> str | None:
    """The tier whose name, or whose name after a speaker's prefix (MFA's
    ``"<speaker> - phones"``, :func:`_speaker_and_tier`), is one of ``names``
    (case-insensitive), by the order of ``names``.

    >>> _tier_named({"notes - draft": [], "carl - Words": []}, ("words",))
    'carl - Words'
    """
    for want in names:
        for name in tiers:
            if _speaker_and_tier(name)[1].strip().lower() == want:
                return name
    return None


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
    [TranscriptSegment(text='hello there', start=0.5, end=1.3, speaker=None, words=(('hello', 0.5, 0.9), ('there', 0.9, 1.3)), phones=None, phone_alphabet=None)]
    """
    tiers = _textgrid_tiers(text)
    if not tiers:
        raise ValueError("no IntervalTier found in the TextGrid")
    return segments_from_tiers(tiers)


def _speaker_and_tier(name: str) -> tuple[str | None, str]:
    """MFA's ``"<speaker> - words"`` → ``("<speaker>", "words")``. Only a known
    tier name after the separator (:data:`_TG_KNOWN_TIERS`) makes a speaker;
    any other name → ``(None, name)``.

    >>> _speaker_and_tier("carl - words"), _speaker_and_tier("notes - draft")
    (('carl', 'words'), (None, 'notes - draft'))
    """
    speaker, sep, bare = name.rpartition(_TG_SPEAKER_SEP)
    if sep and speaker.strip() and bare.strip().lower() in _TG_KNOWN_TIERS:
        return speaker.strip(), bare
    return None, name


Tiers = Mapping[str, Sequence[tuple[float, float, str]]]


def _tiers_by_speaker(tiers: Tiers) -> dict[str | None, dict[str, Any]]:
    """Partition ``tiers`` by their speaker prefix (:func:`_speaker_and_tier`):
    ``{speaker: {tier name: intervals}}``, the unprefixed ones under ``None``.

    >>> _tiers_by_speaker({"carl - words": [], "ned - phones": [], "notes": []})
    {'carl': {'carl - words': []}, 'ned': {'ned - phones': []}, None: {'notes': []}}
    """
    groups: dict[str | None, dict[str, Any]] = {}
    for name, intervals in tiers.items():
        groups.setdefault(_speaker_and_tier(name)[0], {})[name] = intervals
    return groups


def _speech(tiers: Tiers, name: str | None) -> list[WordTiming]:
    """The speech intervals of tier ``name`` as ``(label, start, end)``; ``[]``
    when there is no such tier."""
    if name is None:
        return []
    return [(t, a, b) for a, b, t in tiers[name] if _is_speech(t)]


def _within(timings: Sequence[WordTiming], a: float, b: float) -> tuple | None:
    """The timings inside ``[a, b]`` (give or take :data:`_SPAN_EPS_S`), or ``None``."""
    inside = tuple(
        x for x in timings if x[1] >= a - _SPAN_EPS_S and x[2] <= b + _SPAN_EPS_S
    )
    return inside or None


def textgrid_text(
    tiers: Mapping[str, Sequence[tuple[float, float, str]]], *, xmax: float
) -> str:
    """A long-form Praat TextGrid of interval ``tiers`` (``{name: [(start, end,
    label), ...]}``) spanning ``0..xmax``: what :func:`parse_textgrid` reads
    back, and what a forced aligner takes as a transcript of timed lines
    (an#716). The gaps between intervals are filled with empty ones, as Praat
    requires a tier to cover its span; a ``"`` in a label is doubled.

    >>> grid = textgrid_text({"take": [(0.5, 1.2, 'say "hi"')]}, xmax=2.0)
    >>> _textgrid_tiers(grid)
    {'take': [(0.0, 0.5, ''), (0.5, 1.2, 'say "hi"'), (1.2, 2.0, '')]}
    """

    def tiled(intervals: Sequence[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
        out, t = [], 0.0
        for a, b, label in sorted(intervals):
            if a > t:
                out.append((t, a, ""))
            out.append((a, b, label))
            t = b
        return out + ([(t, xmax, "")] if t < xmax else [])

    lines = ['File type = "ooTextFile"', 'Object class = "TextGrid"', "",
             "xmin = 0", f"xmax = {xmax}", "tiers? <exists>", f"size = {len(tiers)}",
             "item []:"]  # fmt: skip
    for i, (name, intervals) in enumerate(tiers.items(), start=1):
        cells = tiled(intervals)
        lines += [f"    item [{i}]:", '        class = "IntervalTier"',
                  f'        name = "{name}"', "        xmin = 0", f"        xmax = {xmax}",
                  f"        intervals: size = {len(cells)}"]  # fmt: skip
        for j, (a, b, label) in enumerate(cells, start=1):
            text = label.replace('"', '""')
            lines += [f"        intervals [{j}]:", f"            xmin = {a}",
                      f"            xmax = {b}", f'            text = "{text}"']  # fmt: skip
    return "\n".join(lines) + "\n"


def segments_from_tiers(tiers: Tiers) -> list[TranscriptSegment]:
    """An aligner's interval tiers (``{name: [(start, end, label), ...]}``,
    as a TextGrid or MFA's JSON carries them) → segments.

    One speaker (or none): the words from a tier named ``words`` (else the
    first that is neither phones nor lines), the phones from a ``phones``
    tier, one segment per interval of a lines tier when there is one.

    MFA names a speaker's tiers ``"<speaker> - words"`` (a known tier name
    after the separator, :data:`_TG_KNOWN_TIERS`). With two speakers or more
    the conversation is cut into TURNS (an#721): every speaker's words in one
    time-ordered stream, a new segment at each change of speaker, its phones
    that speaker's within the turn (:func:`_turn_segments`). There, a tier
    with no speaker prefix is ignored (it is nobody's), and so is a speaker
    with no words tier: phones are never read as words (an#491).

    >>> segments_from_tiers({"words": [(0.5, 0.9, "hello")], "phones": [(0.5, 0.6, "HH"), (0.6, 0.9, "AH0")]})[0].phones
    (('HH', 0.5, 0.6), ('AH0', 0.6, 0.9))
    >>> [(s.speaker, s.text) for s in segments_from_tiers({
    ...     "carl - words": [(0.0, 0.4, "hi"), (2.0, 2.4, "bye")],
    ...     "ned - words": [(0.5, 0.9, "yo")]})]
    [('carl', 'hi'), ('ned', 'yo'), ('carl', 'bye')]
    """
    groups = _tiers_by_speaker(tiers)
    speakers = [k for k in groups if k is not None]
    if len(speakers) <= 1:  # one speaker (or none): its tiers, and any unnamed
        return _speaker_segments(tiers, speaker=next(iter(speakers), None))
    return _turn_segments(
        {
            who: (
                _speech(groups[who], _tier_named(groups[who], _TG_WORD_TIERS)),
                _speech(groups[who], _tier_named(groups[who], _TG_PHONE_TIERS)),
            )
            for who in speakers
        }
    )


def _turn_segments(
    timings: Mapping[str, tuple[Sequence[WordTiming], Sequence[WordTiming]]],
) -> list[TranscriptSegment]:
    """``{speaker: (words, phones)}`` → one segment per TURN (an#721): all the
    speakers' words in time order, cut at every change of speaker. A turn's
    words are that run, its span from its first word's start to its last's
    end, its phones the speaker's inside that span, in the alphabet the
    speaker's phones show (:func:`phone_alphabet_of`).

    >>> [(t.speaker, t.text, t.start, t.end, t.phones) for t in _turn_segments({
    ...     "carl": ([("hi", 0.0, 0.5), ("bye", 2.0, 2.5)], [("HH", 0.0, 0.2), ("B", 2.0, 2.1)]),
    ...     "ned": ([("yo", 0.8, 1.5)], [])})]  # doctest: +NORMALIZE_WHITESPACE
    [('carl', 'hi', 0.0, 0.5, (('HH', 0.0, 0.2),)), ('ned', 'yo', 0.8, 1.5, None),
     ('carl', 'bye', 2.0, 2.5, (('B', 2.0, 2.1),))]
    """
    stream = sorted(
        ((word, who) for who, (words, _) in timings.items() for word in words),
        key=lambda item: (item[0][1], item[0][2]),
    )
    alphabets = {
        who: phone_alphabet_of(p[0] for p in phones) if phones else None
        for who, (_, phones) in timings.items()
    }
    out = []
    for who, run in groupby(stream, key=lambda item: item[1]):
        words = tuple(word for word, _ in run)
        start, end = words[0][1], words[-1][2]
        phones = _within(timings[who][1], start, end)
        out.append(
            TranscriptSegment(
                text=" ".join(w[0] for w in words),
                start=start,
                end=end,
                speaker=who,
                words=words,
                phones=phones,
                phone_alphabet=alphabets[who] if phones else None,
            )
        )
    return out


def _speaker_segments(tiers: Tiers, *, speaker: str | None) -> list[TranscriptSegment]:
    """One speaker's tiers → segments (:func:`segments_from_tiers`); a line
    tier's own ``speaker: text`` wins over ``speaker``."""
    if not tiers:
        return []
    phone_tier = _tier_named(tiers, _TG_PHONE_TIERS)
    line_tier = _tier_named(tiers, _TG_LINE_TIERS)
    # Without a tier named for words, the first tier that is neither the
    # phones nor the lines (a phones tier read as words would put "HH AH0" in
    # the captions, an#491).
    word_tier = _tier_named(tiers, _TG_WORD_TIERS) or next(
        (n for n in tiers if n not in (phone_tier, line_tier)), next(iter(tiers))
    )
    words = _speech(tiers, word_tier)
    phones = _speech(tiers, phone_tier) if phone_tier != word_tier else []
    alphabet = phone_alphabet_of(p[0] for p in phones) if phones else None

    if line_tier is None:
        if not words:
            return []
        return [
            TranscriptSegment(
                text=" ".join(w[0] for w in words),
                start=words[0][1],
                end=words[-1][2],
                speaker=speaker,
                words=tuple(words),
                phones=tuple(phones) or None,
                phone_alphabet=alphabet,
            )
        ]
    out = []
    for a, b, t in tiers[line_tier]:
        if not t:
            continue
        said_by, body = _speaker_and_text(t)
        inside = _within(phones, a, b)
        out.append(
            TranscriptSegment(
                text=body,
                start=a,
                end=b,
                speaker=said_by or speaker,
                words=_within(words, a, b),
                phones=inside,
                phone_alphabet=alphabet if inside else None,
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
    """``words`` (or phones: any ``(label, start, end)`` timings) re-timed from
    ``start`` (a cut's start): the clip-relative timings a line keeps.

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
