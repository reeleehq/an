"""Where a package's library lives on disk: one root per package (ADR 0005 §2, plan §1 decisions 7–8).

The root is resolved in this order, first match wins:

1. an explicit ``root=`` (tests, power users, a team share);
2. the environment variable ``<PKG>_HOME`` (``AN_HOME``, ``CUTAN_HOME``) — one
   switch for a whole shell or CI job;
3. the platform data folder: ``$XDG_DATA_HOME/<pkg>`` when ``XDG_DATA_HOME`` is
   set to an absolute path, else ``~/.local/share/<pkg>`` on Linux and macOS;
   ``%LOCALAPPDATA%\\<pkg>`` on Windows. On macOS this is deliberately
   ``~/.local/share``, not ``~/Library/Application Support`` — the maintainer's
   choice, and the one the fleet's storage rules use.

This is the data-folder half of ``config2py.get_app_folder``, **vendored** (plan
§1 decision 8): twenty lines are cheaper than a dependency, and the dependency is
taken only if more than this is ever needed.

Under the root, one sub-folder per kind of data, never files at the top:
``library/`` (records, versions, blobs) and ``projects/`` (agent-made videos).
Resolving a root never creates it and never raises at import; the stores create
their folders on first use.

>>> env = {"AN_HOME": "/srv/an-lib"}
>>> library_root(package="an", environ=env).as_posix()
'/srv/an-lib'
>>> library_root(package="cutan", environ={"XDG_DATA_HOME": "/data"}, platform="linux").as_posix()
'/data/cutan'
"""

from __future__ import annotations

import os
import posixpath
import re
import sys
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath

__all__ = [
    "CORE_PACKAGE",
    "LibraryLocationWarning",
    "LIBRARY_DIRNAME",
    "PROJECTS_DIRNAME",
    "git_worktree_of",
    "home_env_var",
    "library_root",
    "project_dir",
    "projects_root",
]

#: The core package, whose library every genre's search path reads after its own.
CORE_PACKAGE: str = "an"
#: The sub-folder of a root that holds the library stores.
LIBRARY_DIRNAME: str = "library"
#: The sub-folder of a root that holds agent-made projects (design §7.5).
PROJECTS_DIRNAME: str = "projects"
#: Suffix of the per-package override variable (``AN_HOME``).
HOME_ENV_SUFFIX: str = "_HOME"
#: The XDG variable naming the user's data folder.
XDG_DATA_HOME: str = "XDG_DATA_HOME"
#: The Windows variable naming the user's local (non-roaming) data folder.
WINDOWS_DATA_ENV: str = "LOCALAPPDATA"
#: Where the data folder is when no variable says otherwise (POSIX).
POSIX_DATA_DEFAULT: tuple[str, ...] = (".local", "share")
#: …and on Windows.
WINDOWS_DATA_DEFAULT: tuple[str, ...] = ("AppData", "Local")


def home_env_var(package: str) -> str:
    """The override variable for ``package``'s root.

    >>> home_env_var("an"), home_env_var("my-genre")
    ('AN_HOME', 'MY_GENRE_HOME')
    """
    return re.sub(r"[^A-Z0-9]", "_", package.upper()) + HOME_ENV_SUFFIX


def _is_windows(platform: str) -> bool:
    return platform.startswith("win") or platform == "cygwin"


def _platform_data_dir(environ: Mapping[str, str], platform: str) -> Path:
    if _is_windows(platform):
        local = environ.get(WINDOWS_DATA_ENV)
        if local:
            return Path(PureWindowsPath(local))
        return Path.home().joinpath(*WINDOWS_DATA_DEFAULT)
    xdg = environ.get(XDG_DATA_HOME)
    # The XDG spec: a relative value is invalid and must be ignored.
    if xdg and posixpath.isabs(xdg):
        return Path(xdg)
    return Path.home().joinpath(*POSIX_DATA_DEFAULT)


def library_root(
    root: str | os.PathLike | None = None,
    *,
    package: str = CORE_PACKAGE,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
) -> Path:
    """The data root of ``package`` — its library and its projects live under it.

    root: an explicit root; wins over everything
    package: the package whose root this is (``an`` for the core library, a
        genre's own name for its library)
    environ: the environment to read (default ``os.environ``; injectable for tests)
    platform: ``sys.platform`` value to resolve for (default: this one)

    >>> library_root("~/x", package="an").name
    'x'
    """
    if root is not None and str(root) != "":
        return Path(root).expanduser()
    env = os.environ if environ is None else environ
    override = env.get(home_env_var(package))
    if override:
        return Path(override).expanduser()
    return _platform_data_dir(env, platform or sys.platform) / package


def projects_root(
    root: str | os.PathLike | None = None,
    *,
    package: str = CORE_PACKAGE,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Where agent-made projects go by default: ``<root>/projects/``.

    >>> projects_root("/lib", package="cutan").as_posix()
    '/lib/projects'
    """
    return library_root(root, package=package, environ=environ) / PROJECTS_DIRNAME


def project_dir(
    project_id: str,
    root: str | os.PathLike | None = None,
    *,
    package: str = CORE_PACKAGE,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """The default directory of the agent-made project ``project_id`` (design §7.5).

    ``an init <dir>`` with an explicit directory keeps working anywhere; this is
    the default for projects an agent makes, so they never land in a session's
    working folder or a repository.

    >>> project_dir("alice-and-bob", "/lib").as_posix()
    '/lib/projects/alice-and-bob'
    >>> project_dir("../escape", "/lib")  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ValueError: ...
    """
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", project_id or ""):
        raise ValueError(
            f"project id {project_id!r} must be one folder name "
            "(letters, digits, '.', '_' or '-'; no path separators)"
        )
    return projects_root(root, package=package, environ=environ) / project_id


class LibraryLocationWarning(UserWarning):
    """Library data, or private material checked out of it, sits inside a git work tree.

    ADR 0005 decision 2: a library root is never inside a repository. The default
    guarantees it; an explicit ``root``, ``<PKG>_HOME`` or a project in a repo
    can break it, and the library may hold private-study material.
    """


def git_worktree_of(path: str | os.PathLike) -> Path | None:
    """The git work tree containing ``path`` (or its nearest existing ancestor), if any.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     git_worktree_of(d) is None
    True
    """
    here = Path(path).expanduser().absolute()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return None
