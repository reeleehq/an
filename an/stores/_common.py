"""Shared store helpers — tiny base classes around dol's filesystem stores.

We don't want every concrete store re-implementing the same JSON / sidecar
machinery. Two patterns dominate:

- **Pure-JSON store**: each value is a JSON document (no binary side files).
  Used for voices, styles, decisions metadata.
- **JSON + sidecar store**: each key maps to a directory containing a
  ``meta.json`` plus arbitrary binary sidecars (sprites, audio, etc.). Used
  for characters, environments, audio artifacts.

Both patterns wrap dol's ``Files`` family.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Any, Iterator

#: File and folder names an operating system or file manager drops into any
#: folder: never an asset. Hidden names (a leading ``.``: ``.DS_Store``,
#: ``._head.svg`` AppleDouble files, ``.Spotlight-V100``) are junk too.
OS_JUNK_NAMES: frozenset[str] = frozenset(
    {"Thumbs.db", "ehthumbs.db", "desktop.ini", "Desktop.ini", "Icon\r", "__MACOSX"}
)


def is_os_junk(relpath: str) -> bool:
    """Whether a path inside an asset folder is operating-system clutter, not the asset.

    One rule for every reader of an asset folder — a library publish, a
    check-out's drift test, the credits walk's digests — so a ``.DS_Store``
    Finder drops into a character folder never makes a copy look edited.

    >>> [is_os_junk(p) for p in ("parts/head.svg", ".DS_Store", "parts/Thumbs.db", "__MACOSX/x")]
    [False, True, True, True]
    """
    return any(
        part.startswith(".") or part in OS_JUNK_NAMES for part in relpath.split("/")
    )


#: What an asset document's path (a plane's ``art.src``, a part's ``path``)
#: may NOT be (an#483): a URL or a drive (any ``:``), an absolute path, a
#: backslash, a control character, an empty, ``.`` or ``..`` segment — the
#: same cleanliness the asset library asks of a published file
#: (:func:`an.library.api.check_relpath`), so the two never disagree about a path.


def asset_ref_problem(rel: str) -> str | None:
    r"""Why ``rel``, a path an asset document names, is NOT a clean relative
    path inside the asset's folder, or ``None`` when it is one (an#483).

    An asset reference resolves inside its own folder, never anywhere else:
    an absolute path, a ``..`` that leaves the folder or a URL is refused by
    name, before any read — a project may be someone else's input (a
    production pack checked on a server), and a reference that reaches outside
    it is a file-existence and XML-parse oracle on the host. The spelling is
    held to the library's rule too (no ``.`` or empty segment, no backslash),
    so a reference that validates here publishes there unchanged.

    >>> asset_ref_problem("parts/head.svg") is None
    True
    >>> asset_ref_problem("/etc/hostname")
    'is an absolute path'
    >>> asset_ref_problem("../../other/plate.png")
    'leaves the asset folder (`..`)'
    >>> asset_ref_problem("file:///etc/hostname"), asset_ref_problem("C:/art/x.svg")
    ('is a URL or a drive path (`:`)', 'is a URL or a drive path (`:`)')
    >>> asset_ref_problem("./parts/head.svg"), asset_ref_problem("parts\\head.svg"), asset_ref_problem("")
    ('has an empty or `.` segment', 'uses a backslash (write the path with `/`)', 'is empty')
    """
    text = str(rel or "")
    if not text.strip():
        return "is empty"
    if any(ord(c) < 32 or c == "\x7f" for c in text):
        return "contains a control character"
    if "\\" in text:
        return "uses a backslash (write the path with `/`)"
    if ":" in text:
        return "is a URL or a drive path (`:`)"
    if text.startswith("/"):
        return "is an absolute path"
    segments = text.split("/")
    if ".." in segments:
        return "leaves the asset folder (`..`)"
    if any(seg in ("", ".") for seg in segments):
        return "has an empty or `.` segment"
    return None


ASSET_REF_RULE: str = (
    "an asset reference must be a relative path inside the asset's own folder "
    "(nothing outside it is read)"
)


def inside_folder(folder: str | Path, rel: str) -> Path | None:
    """``folder / rel`` when ``rel`` is a relative path that stays inside
    ``folder`` once symlinks are resolved, else ``None`` (an#483). The path is
    returned as joined, not resolved, so a caller's own stat and digest see
    the same spelling they always did.

    >>> import tempfile, os
    >>> with tempfile.TemporaryDirectory() as d:
    ...     inside_folder(d, "parts/head.svg") == Path(d) / "parts/head.svg"
    ...     inside_folder(d, "../head.svg") is None, inside_folder(d, "/etc/hostname") is None
    True
    (True, True)
    """
    if asset_ref_problem(rel) is not None:
        return None
    base = Path(folder)
    target = base / str(rel)
    try:
        real, root = target.resolve(), base.resolve()
    except (OSError, RuntimeError):  # a symlink loop, an unreadable parent
        return None
    return target if real == root or real.is_relative_to(root) else None


def asset_references(doc: Mapping) -> list[tuple[str, str]]:
    """``(label, path)`` for every file path an asset document names (an#552):
    an environment's image planes (``planes/<name>/art/src``), a rig's
    attachments (``skins/<skin>/slots/<slot>/<attachment>/path``), a
    character's ``source_svg`` and the files its ``colour_roles`` keys name.

    The one list of what an asset document references; the core's
    ``an validate`` and a genre's own validator both walk it, so they cannot
    disagree about which fields hold a path.

    >>> asset_references({"planes": [{"name": "sky", "art": {"kind": "image", "src": "sky.png"}},
    ...                              {"name": "fill", "art": {"kind": "fill"}}]})
    [('plane sky', 'sky.png')]
    >>> asset_references({"skins": {"default": {"slots": {"body": {"body": {"path": "parts/body.svg"}}}}},
    ...                   "source_svg": "source.svg", "colour_roles": {"parts/body.svg": {"#fff": "skin"}}})
    [('part body/body', 'parts/body.svg'), ('source_svg', 'source.svg'), ('colour_roles parts/body.svg', 'parts/body.svg')]

    A malformed document names nothing where it is malformed (its schema
    check reports it), rather than raising:

    >>> asset_references({"planes": [{"art": "sky.png"}], "skins": {"default": {"slots": ["body"]}},
    ...                   "source_svg": 3})
    []
    >>> asset_references({"planes": "sky.png", "skins": ["default"]})
    []
    """
    out: list[tuple[str, str]] = []
    planes = doc.get("planes")
    for plane in planes if isinstance(planes, (list, tuple)) else ():
        if not isinstance(plane, Mapping):
            continue
        art = plane.get("art")
        if not isinstance(art, Mapping):
            continue
        src = art.get("src")
        if art.get("kind", "fill") == "image" and isinstance(src, str) and src:
            out.append((f"plane {plane.get('name', '?')}", src))
    skins = doc.get("skins")
    for skin in skins.values() if isinstance(skins, Mapping) else ():
        slots = skin.get("slots") if isinstance(skin, Mapping) else None
        if not isinstance(slots, Mapping):
            continue
        for slot_name, attachments in slots.items():
            if not isinstance(attachments, Mapping):
                continue
            for att_name, att in attachments.items():
                rel = att.get("path") if isinstance(att, Mapping) else None
                if isinstance(rel, str) and rel:
                    out.append((f"part {slot_name}/{att_name}", rel))
    source_svg = doc.get("source_svg")
    if isinstance(source_svg, str) and source_svg:
        out.append(("source_svg", source_svg))
    roles = doc.get("colour_roles")
    if isinstance(roles, Mapping):
        out += [(f"colour_roles {k}", k) for k in roles if isinstance(k, str) and k]
    return out


#: The message a file that resolves outside its asset's folder gets.
OUTSIDE_FOLDER_PROBLEM: str = "resolves outside the asset's folder (a link)"


def asset_ref_problems(
    doc: Mapping,
    folder: str | Path | None = None,
    *,
    file_problems: Callable[[Path], list[str]] | None = None,
) -> list[tuple[str, str]]:
    """``(label, message)`` for every reference in ``doc``
    (:func:`asset_references`) that breaks the asset-reference rule (an#483,
    an#552); ``[]`` when none does. The one rule the core and a genre share.

    A reference is judged by NAME first (:func:`asset_ref_problem`), and is
    never read when its name is bad; with a ``folder``, also by where it
    resolves (:func:`inside_folder`: a link out of the folder is the same
    error). ``file_problems``, when given, is asked about each file that
    passed (the core passes its SVG self-containment check): it is called
    for every path that passed the name (and folder) check, whether or not
    the file exists, so it must tolerate an absent file. Each message it
    returns is appended to ``"<label> names <path>, which"``, so it must
    begin with a verb (``"is SVG that ..."``, ``"is not in the folder"``).
    ``message`` is a whole sentence, label included, so a caller can report
    it as is.

    >>> asset_ref_problems({"source_svg": "../x.svg", "planes": [
    ...     {"name": "sky", "art": {"kind": "image", "src": "sky.png"}}]})  # doctest: +NORMALIZE_WHITESPACE
    [('source_svg', "source_svg names '../x.svg', which leaves the asset folder (`..`):
      an asset reference must be a relative path inside the asset's own folder
      (nothing outside it is read)")]
    >>> asset_ref_problems({"source_svg": "source.svg"}, ".")
    []
    >>> asset_ref_problems({"source_svg": "ok.svg"}, ".",
    ...                    file_problems=lambda f: [f"is SVG that holds a <script>"])
    [('source_svg', "source_svg names 'ok.svg', which is SVG that holds a <script>")]
    """
    out: list[tuple[str, str]] = []
    for label, rel in asset_references(doc):
        who = f"{label} names {rel!r}, which"
        problem = asset_ref_problem(rel)
        if problem is not None:
            out.append((label, f"{who} {problem}: {ASSET_REF_RULE}"))
            continue
        if folder is None:
            continue
        file = inside_folder(folder, rel)
        if file is None:
            out.append((label, f"{who} {OUTSIDE_FOLDER_PROBLEM}: {ASSET_REF_RULE}"))
            continue
        if file_problems is not None:
            out += [(label, f"{who} {found}") for found in file_problems(file)]
    return out


class JsonDirStore(MutableMapping):
    """`MutableMapping` of name -> JSON document, stored as ``<name>.json`` files.

    Backed by the filesystem under ``root_dir``. Keys are the file stems; values
    are arbitrary JSON-serializable Python objects. ``__contains__``, ``__iter__``,
    and ``__len__`` are derived from directory listing.
    """

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if "/" in key or key.startswith(".") or not key:
            raise KeyError(f"invalid key: {key!r}")
        return self._root / f"{key}.json"

    def __getitem__(self, key: str) -> Any:
        p = self._path(key)
        if not p.exists():
            raise KeyError(key)
        return json.loads(p.read_text(encoding="utf-8"))

    def __setitem__(self, key: str, value: Any) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

    def __delitem__(self, key: str) -> None:
        p = self._path(key)
        if not p.exists():
            raise KeyError(key)
        p.unlink()

    def __iter__(self) -> Iterator[str]:
        for child in sorted(self._root.glob("*.json")):
            yield child.stem

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self._root)!r})"


class JsonSidecarStore(MutableMapping):
    """`MutableMapping` of name -> dict, where each entry is a directory containing
    ``meta.json`` plus optional binary sidecars.

    Reading returns the parsed ``meta.json``. Writing replaces ``meta.json``;
    sidecars must be written separately by the caller (use ``sidecar_path(key, name)``).
    Deleting removes the whole directory.
    """

    META_NAME = "meta.json"

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    def _entry_dir(self, key: str) -> Path:
        if "/" in key or key.startswith(".") or not key:
            raise KeyError(f"invalid key: {key!r}")
        return self._root / key

    def sidecar_path(self, key: str, name: str) -> Path:
        d = self._entry_dir(key)
        d.mkdir(parents=True, exist_ok=True)
        return d / name

    def __getitem__(self, key: str) -> dict[str, Any]:
        meta = self._entry_dir(key) / self.META_NAME
        if not meta.exists():
            raise KeyError(key)
        return json.loads(meta.read_text(encoding="utf-8"))

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        d = self._entry_dir(key)
        d.mkdir(parents=True, exist_ok=True)
        (d / self.META_NAME).write_text(
            json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

    def __delitem__(self, key: str) -> None:
        d = self._entry_dir(key)
        if not d.exists():
            raise KeyError(key)
        # Remove the directory and all sidecars.
        for child in d.rglob("*"):
            if child.is_file():
                child.unlink()
        for child in sorted(d.rglob("*"), reverse=True):
            if child.is_dir():
                child.rmdir()
        d.rmdir()

    def __iter__(self) -> Iterator[str]:
        for child in sorted(self._root.iterdir()):
            if child.is_dir() and (child / self.META_NAME).exists():
                yield child.name

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self._root)!r})"


class AudioSidecarStore(JsonSidecarStore):
    """A :class:`JsonSidecarStore` whose entries carry one WAV sidecar.

    The metadata is the mapping's value; the audio is read and written through
    :meth:`read_audio` / :meth:`write_audio`, so no caller builds a path by hand
    (pillar 7). Sounds (``an.stores.sounds``) and recorded takes
    (``an.stores.recordings``) are the two.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     store = AudioSidecarStore(d)
    ...     store['x'] = {'description': 'a take'}
    ...     store.write_audio('x', b'RIFF....')
    ...     store.read_audio('x')
    b'RIFF....'
    """

    #: The sidecar holding the audio bytes. WAV only: a header states the length
    #: without decoding anything.
    AUDIO_NAME = "audio.wav"
    #: What an entry is called in error messages.
    ENTRY_NOUN = "entry"

    def read_audio(self, key: str) -> bytes:
        path = self._entry_dir(key) / self.AUDIO_NAME
        if not path.exists():
            raise KeyError(f"{self.ENTRY_NOUN} {key!r} has no audio sidecar")
        return path.read_bytes()

    def write_audio(self, key: str, data: bytes) -> None:
        self.sidecar_path(key, self.AUDIO_NAME).write_bytes(data)


def art_exists_for(characters_store: Mapping, ref: str) -> Callable[[str], bool] | None:
    """``rel_path -> is the art on disk``, for a character in a filesystem
    store; ``None`` when the store has no root to look under (a dict, a
    fake) — a store that can answer nothing must assume presence, not absence,
    exactly as the rig builder's part probe does.
    """
    root = getattr(characters_store, "_root", None)
    if root is None:
        return None
    base = Path(root) / ref

    def exists(rel_path: str) -> bool:
        path = inside_folder(base, rel_path)  # outside the folder: not art (an#483)
        return path is not None and path.is_file()

    return exists
