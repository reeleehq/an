"""Captions from the word timings the audio pipeline already computes (an#175).

Epic #9 Wave 8, second slice. The audio pipeline stamps each dialogue line
with the provider's word timings (``Dialogue.word_timings``, line-relative,
an#96) for lip-sync; this module turns them into captions, opt-in through
``meta.captions`` (:class:`~an.ir.schema.Captions`).

**One cue list, two outputs.** :func:`caption_pages` is the single statement
of what is captioned and on which frames. Both outputs are derived from it:

- the picture — :func:`captioned_shot` adds each page as an OVERLAY text
  block (:mod:`an.text`; camera-immune, placed at a title-safe anchor) plus
  ordinary ``set`` actions that show it for exactly its frames, and
  optionally tint the word being spoken;
- the sidecar — :func:`caption_cues` places the same pages in FILM time and
  :func:`dump_srt` writes SubRip, stored through the ``captions`` store beside
  the delivered mp4.

So the two cannot disagree: a page's cue starts at the first frame that shows
it and ends at the first frame that does not. Times are frames, not seconds,
until the last step:

>>> from an.ir.schema import Dialogue, SceneIR, Shot, WordTimingIR
>>> line = Dialogue(speaker="a", text="Hello there, friend.", start=0.5, duration=1.5,
...     word_timings=[WordTimingIR(text=w, start=s, end=s + 0.3)
...                   for w, s in (("Hello", 0.0), ("there,", 0.4), ("friend.", 0.8))])
>>> scene = SceneIR(timeline=[Shot(id="s", duration=3.0, dialogue=[line])])
>>> [(p.start, p.end, p.text) for p in caption_pages(scene, fps=10)]
[(5, 20, 'Hello there, friend.')]

**Film time follows the delivered timeline.** A cue's time is its shot's
first frame in the film (:func:`an.assemble.film_timeline` — the same
function the assembler lays the picture out with) plus its shot-local frame,
so a dissolve, which overlaps two shots and shortens the film, moves every
later cue earlier by exactly its overlap.

**Timing is materialised into ordinary actions**, the way :func:`an.text.stagger`
works: nothing in the compiler or the runtime knows what a caption is. The
caption blocks are added to the shot at RENDER time, never written back to
the scene — the word timings are the audio pipeline's output, and a caption
baked into ``scene.json`` would go stale the moment a line is re-voiced.

**When a line has no word timings** (the offline and Rhubarb providers keep
none), its words are spread evenly over the line's duration and a
:class:`CaptionTimingWarning` says so; ``Captions(strict=True)`` raises
instead. A line the audio pipeline has not placed (no ``start``) cannot be
captioned and is skipped the same loud way.

**The SubRip cue type is a pinned mirror of ``mixing.srt``**, not an import
(epic #9, Decision 2, departed from on measurement): ``mixing``'s package
facade is lazy, so importing ``mixing.srt`` is cheap — but INSTALLING
``mixing`` pulls ``moviepy``, ``opencv-contrib-python``, ``scipy`` and
``imageio-ffmpeg``, whose wheel ships an ffmpeg binary built with
``--enable-gpl``. A hard dependency would put a GPL binary inside every
``pip install an``, past a licence perimeter that reads declared metadata
(BSD-2) and would never see it. :class:`Cue`, :func:`seconds_to_srt_time` and
:func:`dump_srt` therefore mirror ``mixing.srt`` field for field and byte for
byte, and ``tests/test_captions.py`` pins both against ``mixing`` whenever it
is importable, and against a literal otherwise; thorwhalen/mixing#54 asks
for the light base install that would let this become an import. WebVTT is ``lacing``'s (its
adapter owns the body schema), so it is not written here.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from an.ir.schema import AssetRef, Captions, SceneIR, Shot

__all__ = [
    "CAPTION_ID_PREFIX",
    "CAPTION_PROP_REF",
    "CaptionError",
    "CaptionPage",
    "CaptionTimingWarning",
    "CaptionWarning",
    "Cue",
    "caption_cues",
    "caption_pages",
    "captioned_shot",
    "dump_srt",
    "paginate",
    "seconds_to_srt_time",
    "srt_for_scene",
    "wrap_words",
]

#: A caption page's entity id is this plus its index within the shot.
CAPTION_ID_PREFIX: str = "caption_"

#: The props-store key the caption blocks resolve against — a style-only
#: ``TextDescriptor`` supplied at render time, never stored in the project.
CAPTION_PROP_REF: str = "an.captions"

#: A word ending in one of these ends a sentence, and a new sentence starts a
#: new page: a page that straddles two sentences reads as one run-on thought.
_SENTENCE_ENDS: tuple[str, ...] = (".", "?", "!", "...", "…")

#: Tolerance when a time is turned into the first frame at or after it, so a
#: time that is a frame boundary in exact arithmetic is not pushed a frame
#: late by float error.
_FRAME_EPS: float = 1e-9

#: Where, between two frames, a caption's ``set`` lands: half a frame before
#: the frame it takes effect on, so no float disagreement between Python and
#: the runtime about ``i / fps`` can move it a frame.
_SET_OFFSET_FRAMES: float = 0.5


class CaptionError(ValueError):
    """Captions cannot be built as asked. Carries the fix."""


class CaptionWarning(UserWarning):
    """Captions were built, but not everything was captioned as asked."""


class CaptionTimingWarning(CaptionWarning):
    """A line is captioned on estimated timing, or not at all."""


# -----------------------------------------------------------------------------
# SubRip — a pinned mirror of `mixing.srt` (see the module docstring)
# -----------------------------------------------------------------------------


@dataclass
class Cue:
    """One SubRip cue — ``mixing.srt.Cue``'s fields, in its order.

    >>> Cue(index=1, start=0.5, end=2.0, text="Hi").duration
    1.5
    """

    index: int
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        """Cue duration in seconds (never negative)."""
        return max(0.0, self.end - self.start)


def seconds_to_srt_time(seconds: float) -> str:
    """``HH:MM:SS,mmm``, milliseconds ROUNDED with carry; negatives clamp to 0.

    >>> seconds_to_srt_time(2592.187), seconds_to_srt_time(-3)
    ('00:43:12,187', '00:00:00,000')
    """
    ms_total = max(0, int(round(seconds * 1000)))
    h, ms_total = divmod(ms_total, 3600 * 1000)
    m, ms_total = divmod(ms_total, 60 * 1000)
    s, ms = divmod(ms_total, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def dump_srt(cues: Iterable[Cue]) -> str:
    """Serialize cues to SubRip text, renumbering from 1.

    >>> print(dump_srt([Cue(7, 1.0, 2.5, "Hello\\nthere")]))
    1
    00:00:01,000 --> 00:00:02,500
    Hello
    there
    <BLANKLINE>
    """
    parts = [
        f"{i}\n{seconds_to_srt_time(c.start)} --> {seconds_to_srt_time(c.end)}\n{c.text}\n"
        for i, c in enumerate(cues, 1)
    ]
    return "\n".join(parts)


# -----------------------------------------------------------------------------
# Pages — the one cue list
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class CaptionPage:
    """One caption as shown: which shot, which frames, which words.

    ``start``/``end`` are SHOT-local frames — the first that shows the page and
    the first that does not. ``lines`` are the words per line, broken by
    :func:`wrap_words`; ``word_frames[j]`` is the frame word ``j`` (in reading
    order) starts being spoken, clamped into the page.
    """

    shot: int
    start: int
    end: int
    lines: tuple[tuple[str, ...], ...]
    word_frames: tuple[int, ...]
    speaker: str | None = None

    @property
    def words(self) -> tuple[str, ...]:
        """Every word of the page, in reading order."""
        return tuple(w for line in self.lines for w in line)

    @property
    def text(self) -> str:
        """The page as both outputs write it: words joined by spaces, lines by
        newlines."""
        return "\n".join(" ".join(line) for line in self.lines)


def wrap_words(words: Sequence[str], max_chars: int) -> list[list[str]]:
    """Greedy line breaks at ``max_chars`` characters (spaces counted); a word
    longer than a line gets a line of its own and is never split.

    >>> wrap_words("the quick brown fox jumps".split(), 10)
    [['the', 'quick'], ['brown', 'fox'], ['jumps']]
    """
    lines: list[list[str]] = []
    width = 0
    for word in words:
        if lines and width + 1 + len(word) <= max_chars:
            lines[-1].append(word)
            width += 1 + len(word)
        else:
            lines.append([word])
            width = len(word)
    return lines


def paginate(words: Sequence[str], *, max_chars: int, max_lines: int) -> list[range]:
    """Split ``words`` into pages of at most ``max_lines`` wrapped lines, a new
    page starting after each sentence end. Returns index ranges.

    >>> paginate("One two. Three four five six".split(), max_chars=10, max_lines=1)
    [range(0, 2), range(2, 4), range(4, 6)]
    """
    pages: list[range] = []
    first = 0
    for i in range(1, len(words) + 1):
        if i == len(words):
            pages.append(range(first, i))
            break
        sentence_ended = words[i - 1].endswith(_SENTENCE_ENDS)
        overflows = len(wrap_words(words[first : i + 1], max_chars)) > max_lines
        if sentence_ended or overflows:
            pages.append(range(first, i))
            first = i
    return pages


def _first_frame_at(t: float, fps: float) -> int:
    """The first frame whose instant ``i / fps`` is at or after ``t``."""
    return max(0, math.ceil(t * fps - _FRAME_EPS))


def _complain(message: str, *, strict: bool) -> None:
    if strict:
        raise CaptionError(message + " (captions are strict)")
    warnings.warn(message, CaptionTimingWarning, stacklevel=4)


def _split_token(text: str, start: float, end: float) -> list[tuple[str, float]]:
    """A timed token the typesetter will set as several words ("New York")
    becomes one entry per word, sharing the token's span evenly — so the
    highlight's targets and the drawn word units stay one to one."""
    parts = text.split()
    step = max(0.0, end - start) / len(parts)
    return [(part, start + k * step) for k, part in enumerate(parts)]


def _timed_words(line: Any, *, where: str, strict: bool) -> list[tuple[str, float]]:
    """``(word, line-relative start)`` per word the caption shows, in time order."""
    script = line.text.split()
    timings = [w for w in (line.word_timings or []) if w.text.strip()]
    if timings:
        ordered = sorted(timings, key=lambda w: w.start)
        if ordered != timings:
            _complain(
                f"{where}: the provider's word timings are not in time order; "
                "captioning them sorted, with the timed words' own text",
                strict=strict,
            )
        elif len(timings) == len(script):
            return [(word, float(t.start)) for word, t in zip(script, timings)]
        else:
            _complain(
                f"{where}: the script has {len(script)} words but the provider "
                f"timed {len(timings)}; captioning the TIMED words, which is what "
                "was said",
                strict=strict,
            )
        return [
            pair
            for t in ordered
            for pair in _split_token(t.text, float(t.start), float(t.end))
        ]
    if not script:
        return []
    _complain(
        f"{where}: no word timings (the offline and Rhubarb lip-sync providers "
        "keep none), so its caption spreads the words evenly over the line — "
        "use a provider with word timings (whisper, or WordTimingsLipSync) for "
        "captions that follow the voice",
        strict=strict,
    )
    step = float(line.duration) / len(script)
    return [(word, k * step) for k, word in enumerate(script)]


def _line_pages(
    line: Any,
    *,
    shot_index: int,
    shot_frames: int,
    fps: float,
    captions: Captions,
    where: str,
    speaker: str | None,
) -> list[CaptionPage]:
    if line.start is None or line.duration is None:
        _complain(
            f"{where} has no start/duration yet (the audio pipeline places a line "
            "when it voices it), so it cannot be captioned",
            strict=captions.strict,
        )
        return []
    words = _timed_words(line, where=where, strict=captions.strict)
    if not words:
        return []
    texts = [w for w, _ in words]
    at = float(line.start)
    frame_of = [_first_frame_at(at + t, fps) for _, t in words]
    line_end = _first_frame_at(at + max(float(line.duration), words[-1][1]), fps)
    # A page whose successor starts on the same frame would never be seen
    # ("Mr." then "Smith is here" 15 ms later): it joins its successor.
    ranges: list[range] = []
    for r in paginate(texts, max_chars=captions.max_chars, max_lines=captions.max_lines):
        if ranges and frame_of[r.start] <= frame_of[ranges[-1].start]:
            ranges[-1] = range(ranges[-1].start, r.stop)
        else:
            ranges.append(r)
    pages: list[CaptionPage] = []
    for n, r in enumerate(ranges):
        start = frame_of[r.start]
        if start >= shot_frames:
            warnings.warn(
                f"{where}: {' '.join(texts[r.start:])!r} is spoken after the shot "
                f"ends (frame {start} of {shot_frames}), so it is not captioned",
                CaptionWarning,
                stacklevel=3,
            )
            break
        end = frame_of[ranges[n + 1].start] if n + 1 < len(ranges) else line_end
        end = min(max(end, start + 1), shot_frames)  # seen for at least one frame
        frames = tuple(min(max(frame_of[j], start), end - 1) for j in r)
        lines = wrap_words(texts[r.start : r.stop], captions.max_chars)
        pages.append(
            CaptionPage(
                shot=shot_index,
                start=start,
                end=end,
                lines=tuple(tuple(line_words) for line_words in lines),
                word_frames=frames,
                speaker=speaker,
            )
        )
    return pages


def caption_pages(
    scene: SceneIR, *, fps: float, captions: Captions | None = None
) -> list[CaptionPage]:
    """Every caption page of ``scene``, shot by shot, in the order shown.

    ``captions`` defaults to ``scene.meta.captions`` (and to the defaults when
    that is unset). Dialogue and narration are both captioned (though the
    audio pipeline does not voice narration yet, so a narration line has no
    ``start`` in a rendered scene and is skipped with a warning). Within a
    shot a page is cut off when the next one starts, so two pages are never
    drawn over each other at one anchor; ACROSS a transition they can be — a
    dissolve blends the tail of one shot, captions included, with the head of
    the next, and a fade takes the burned caption through the colour with the
    rest of the picture, while the sidecar's cue is simply on.
    """
    from an.frame_clock import frame_count

    captions = captions or scene.meta.captions or Captions()
    out: list[CaptionPage] = []
    for i, shot in enumerate(scene.timeline):
        n_frames = frame_count(shot.duration, fps)
        pages: list[CaptionPage] = []
        lines = [
            (f"dialogue {k} ({ln.speaker})", ln, ln.speaker)
            for k, ln in enumerate(shot.dialogue)
        ]
        lines += [(f"narration {k}", ln, None) for k, ln in enumerate(shot.narration)]
        for label, line, speaker in lines:
            pages += _line_pages(
                line,
                shot_index=i,
                shot_frames=n_frames,
                fps=fps,
                captions=captions,
                where=f"shot {shot.id!r} {label}",
                speaker=speaker,
            )
        pages.sort(key=lambda p: p.start)
        for k, page in enumerate(pages):
            if k + 1 < len(pages) and pages[k + 1].start < page.end:
                end = pages[k + 1].start
                if end <= page.start:
                    # Two lines spoken at once, starting on one frame: one slot
                    # can show one of them. Said, not silently dropped.
                    warnings.warn(
                        f"shot {shot.id!r}: captions {page.text!r} and "
                        f"{pages[k + 1].text!r} start on the same frame "
                        f"({page.start}); only the second is shown",
                        CaptionWarning,
                        stacklevel=2,
                    )
                    continue
                page = CaptionPage(
                    shot=page.shot,
                    start=page.start,
                    end=end,
                    lines=page.lines,
                    word_frames=tuple(min(f, end - 1) for f in page.word_frames),
                    speaker=page.speaker,
                )
            out.append(page)
    return out


def caption_cues(pages: Sequence[CaptionPage], timeline: Any) -> list[Cue]:
    """``pages`` in FILM time on ``timeline`` (an :class:`an.assemble.FilmTimeline`).

    A cue starts on the film frame that first shows its page and ends on the
    first that does not — the same frames the picture shows it on.
    """
    fps = timeline.fps
    return [
        Cue(
            index=k,
            start=(timeline.starts[p.shot] + p.start) / fps,
            end=(timeline.starts[p.shot] + p.end) / fps,
            text=p.text,
        )
        for k, p in enumerate(pages, 1)
    ]


def srt_for_scene(
    scene: SceneIR, *, fps: float, pages: Sequence[CaptionPage] | None = None
) -> str:
    """The SubRip sidecar of ``scene`` rendered at ``fps``.

    >>> from an.ir.schema import Dialogue, SceneIR, Shot, Transition, WordTimingIR
    >>> def shot(sid, **kw):
    ...     line = Dialogue(speaker="a", text="Hi.", start=0.2, duration=0.5,
    ...                     word_timings=[WordTimingIR(text="Hi.", start=0.0, end=0.4)])
    ...     return Shot(id=sid, duration=2.0, dialogue=[line], **kw)
    >>> scene = SceneIR(timeline=[shot("a"), shot("b", transition=Transition(kind="dissolve"))])
    >>> print(srt_for_scene(scene, fps=10))   # b starts at 1.5 s: the dissolve's 0.5 s overlap
    1
    00:00:00,200 --> 00:00:00,700
    Hi.
    <BLANKLINE>
    2
    00:00:01,700 --> 00:00:02,200
    Hi.
    <BLANKLINE>
    """
    from an.assemble import film_timeline

    if pages is None:
        pages = caption_pages(scene, fps=fps)
    return dump_srt(caption_cues(pages, film_timeline(scene.timeline, fps=fps)))


# -----------------------------------------------------------------------------
# The picture — pages as overlay text blocks plus ordinary actions
# -----------------------------------------------------------------------------


class _PropsWithCaptions(Mapping):
    """The project's props store with the caption style laid over it.

    Everything else — including ``_root``, which is what an author's own text
    block resolves a relative font against — is the underlying store's.
    """

    def __init__(self, base: Mapping, docs: Mapping[str, Any]) -> None:
        self._base = base
        self._docs = dict(docs)

    def __getitem__(self, key: str) -> Any:
        if key in self._docs:
            return self._docs[key]
        return self._base[key]

    def __contains__(self, key: object) -> bool:
        return key in self._docs or key in self._base

    def __iter__(self) -> Iterator[str]:
        yield from self._base
        yield from (k for k in self._docs if k not in self._base)

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __getattr__(self, name: str) -> Any:
        if name in ("_base", "_docs"):
            raise AttributeError(name)
        return getattr(self._base, name)


def _caption_font(captions: Captions, base_dir: Path | str | None) -> str | None:
    if captions.font is None:
        return None
    path = Path(captions.font).expanduser()
    if not path.is_absolute():
        if base_dir is None:
            raise CaptionError(
                f"captions font {captions.font!r} is relative and there is no "
                "project directory to resolve it against; give an absolute path"
            )
        path = Path(base_dir) / path
    return str(path)


def _set_time(frame: int, fps: float) -> float:
    return (frame - _SET_OFFSET_FRAMES) / fps


def _page_actions(
    page: CaptionPage, entity_id: str, *, fps: float, n_frames: int, captions: Captions
) -> list:
    from an.ir import compose as c

    actions = []
    if page.start > 0:
        actions.append(c.set_(entity_id, "alpha", 0.0, at=0.0))
        actions.append(c.set_(entity_id, "alpha", 1.0, at=_set_time(page.start, fps)))
    if page.end < n_frames:
        actions.append(c.set_(entity_id, "alpha", 0.0, at=_set_time(page.end, fps)))
    if captions.highlight is None:
        return actions
    # Karaoke: the glyphs are WHITE and `tint` (a multiply) paints them — the
    # base colour everywhere, the highlight on the word being spoken, from its
    # first frame until the next word's.
    frames = page.word_frames
    for j, first in enumerate(frames):
        target = f"{entity_id}/word_{j}"
        until = next((f for f in frames[j + 1 :] if f > first), page.end)
        lit = not (j + 1 < len(frames) and frames[j + 1] == first)
        # Lit from frame 0 is the set AT 0 itself: a set at -half a frame
        # would be overridden by the base-colour set at 0 (review finding).
        from_start = lit and first == 0
        actions.append(
            c.set_(target, "tint", captions.highlight if from_start else captions.color, at=0.0)
        )
        if not lit:
            continue  # the next word starts on the same frame: this one is never lit
        if not from_start:
            actions.append(
                c.set_(target, "tint", captions.highlight, at=_set_time(first, fps))
            )
        if until < page.end:
            actions.append(c.set_(target, "tint", captions.color, at=_set_time(until, fps)))
    return actions


def captioned_shot(
    shot: Shot,
    pages: Sequence[CaptionPage],
    captions: Captions,
    *,
    fps: float,
    mall: Mapping[str, Any],
    shot_index: int | None = None,
    base_dir: Path | str | None = None,
    resolution: tuple[int, int] | None = None,
) -> tuple[Shot, dict[str, Any]]:
    """``shot`` with its caption pages burned in, and the mall to compile it with.

    Each page becomes an overlay text block ``caption_<k>`` and the ``set``
    actions that show it for exactly its frames. With ``shot_index``, only the
    pages of that shot are used, so a caller can pass the scene's whole list;
    without it every page must belong to one shot. The returned mall is
    ``mall`` with the caption style laid over its props store — nothing is
    written to the project. ``base_dir`` resolves a relative caption ``font``.

    With ``resolution``, every page is typeset now, so a caption the face
    cannot draw (an em dash in the embedded face) raises a :class:`CaptionError`
    naming the shot and the words — before a browser launches, rather than
    from inside a shot's compile after others have rendered.
    """
    from an.frame_clock import frame_count

    if shot_index is None:
        shots = {p.shot for p in pages}
        if len(shots) > 1:
            raise CaptionError(
                f"pages of several shots were passed ({sorted(shots)}); give "
                "`shot_index` to say which are this shot's"
            )
        mine = list(pages)
    else:
        mine = [p for p in pages if p.shot == shot_index]
    if not mine:
        return shot, dict(mall)
    taken = {e.id for e in shot.entities}
    n_frames = frame_count(shot.duration, fps)
    font = _caption_font(captions, base_dir)
    entities = list(shot.entities)
    actions = list(shot.actions)
    for k, page in enumerate(mine):
        eid = f"{CAPTION_ID_PREFIX}{k}"
        if eid in taken:
            raise CaptionError(
                f"shot {shot.id!r} already has an entity {eid!r}, the id caption "
                f"page {k} is drawn as; rename that entity"
            )
        overrides: dict[str, Any] = {
            "text": page.text,
            "layer": "overlay",
            "anchor": captions.anchor,
            "size": captions.size,
            "color": "#ffffff" if captions.highlight else captions.color,
            "unit": "word" if captions.highlight else "line",
        }
        if font is not None:
            overrides["font"] = font
        if resolution is not None:
            _check_typesettable(shot, page, overrides, resolution)
        entities.append(
            AssetRef(
                kind="prop", id=eid, store="props", ref=CAPTION_PROP_REF, overrides=overrides
            )
        )
        actions += _page_actions(page, eid, fps=fps, n_frames=n_frames, captions=captions)
    style = {"kind": "TextDescriptor", "name": "caption"}
    new_mall = dict(mall)
    # `is None`, not `or`: an EMPTY on-disk props store is falsy, and swapping
    # it for `{}` would drop the `_root` an author's relative font needs.
    props = mall.get("props")
    new_mall["props"] = _PropsWithCaptions(
        {} if props is None else props, {CAPTION_PROP_REF: style}
    )
    return shot.model_copy(update={"entities": entities, "actions": actions}), new_mall


def _check_typesettable(
    shot: Shot, page: CaptionPage, overrides: Mapping[str, Any], resolution: tuple[int, int]
) -> None:
    """Typeset one page now: it must be drawable, fit the title-safe width,
    and (for a highlight) build exactly one unit per word."""
    from tituli import safe_area

    from an.text import layout_text, resolve_text

    width, height = resolution
    try:
        lay = layout_text(
            resolve_text({"kind": "TextDescriptor", "name": "caption"}, overrides),
            width=width,
            height=height,
        )
    except ValueError as err:  # TextFontError, TextLayoutError, ValidationError
        raise CaptionError(
            f"shot {shot.id!r}: the caption {page.text!r} cannot be set: {err}. "
            "A caption is set in `captions.font` (the embedded face when unset)."
        ) from err
    area = safe_area(width, height)
    x0 = min(u.box[0] for u in lay.units)
    x1 = max(u.box[2] for u in lay.units)
    if x0 < area.x0 - 1 or x1 > area.x1 + 1:
        raise CaptionError(
            f"shot {shot.id!r}: the caption line {page.text!r} is {x1 - x0} px "
            f"wide, wider than the title-safe area ({round(area.x1 - area.x0)} px "
            f"of a {width} px frame); lower `captions.max_chars` or `captions.size`"
        )
    y0 = min(u.box[1] for u in lay.units)
    y1 = max(u.box[3] for u in lay.units)
    if y0 < area.y0 - 1 or y1 > area.y1 + 1:
        raise CaptionError(
            f"shot {shot.id!r}: the caption {page.text!r} is {len(page.lines)} "
            f"lines, {y1 - y0} px tall, taller than the title-safe area allows "
            "at its anchor; lower `captions.size` or `captions.max_lines`"
        )
    if overrides.get("unit") == "word" and len(lay.units) != len(page.words):
        raise CaptionError(  # pragma: no cover — the tokenisers agree today
            f"shot {shot.id!r}: the caption {page.text!r} set as "
            f"{len(lay.units)} word units but has {len(page.words)} words, so "
            "the highlight would light the wrong word"
        )
