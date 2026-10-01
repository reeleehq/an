# an.characters.licenses

DiceBear per-style licences, as data.

The DiceBear *software* licence (MIT) is a separate fact from each *style*
licence — DiceBear itself splits them under literal `# Design` and `# Code`
headings inside every per-style licence file. Reading the repo’s top-level MIT
and concluding the avatars are MIT is the trap this table exists to close.

Verified against the per-style licence files and style pages at the pinned API
major; the sources are recorded in `misc/docs/wave1_verification.md` §2.

Of the styles `an` can request: 11 are CC0 (no attribution duty), 12 are
CC BY 4.0 (a real duty), and the Pablo Stanley set carries bespoke
“free for personal and commercial use” terms that are **not** Creative Commons —
which is why they are their own code here rather than being rounded to one.

### Module Attributes

| [`FREE_PERSONAL_AND_COMMERCIAL`](#an.characters.licenses.FREE_PERSONAL_AND_COMMERCIAL)   | Pablo Stanley's own terms.                                  |
|---------------------------------------------------------------------------------|-------------------------------------------------------------|
| [`DICEBEAR_STYLE_LICENSES`](#an.characters.licenses.DICEBEAR_STYLE_LICENSES)        | style name -> its DESIGN licence.                           |
| [`NO_ATTRIBUTION_REQUIRED`](#an.characters.licenses.NO_ATTRIBUTION_REQUIRED)        | Licences that need no credit from whoever ships the output. |

### Functions

| [`attribution_for`](#an.characters.licenses.attribution_for)(style)           | DiceBear's own attribution template, filled in.                |
|-----------------------------------------------------------------------------------|----------------------------------------------------------------|
| [`dicebear_source`](#an.characters.licenses.dicebear_source)(style, \*, seed) | Build the provenance record for a DiceBear avatar.             |
| [`requires_acknowledgement`](#an.characters.licenses.requires_acknowledgement)(style)  | Whether using `style` puts a duty on whoever ships the output. |

### Classes

| [`StyleLicense`](#an.characters.licenses.StyleLicense)(license, license_url, author, ...)   | One style's design licence and the credit it obliges.   |
|----------------------------------------------------------------------------------------------------|---------------------------------------------------------|

### an.characters.licenses.DICEBEAR_STYLE_LICENSES *: dict[str, [StyleLicense](#an.characters.licenses.StyleLicense)]* *= {'adventurer': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'Lisa Wischofsky', 'https://www.instagram.com/lischi_art/', 'Adventurer', 'https://www.figma.com/community/file/1184595184137881796'), 'adventurer-neutral': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'Lisa Wischofsky', 'https://www.instagram.com/lischi_art/', 'Adventurer Neutral', 'https://www.figma.com/community/file/1184595184137881796'), 'avataaars': ('free-personal-and-commercial', 'https://avataaars.com/', 'Pablo Stanley', 'https://twitter.com/pablostanley', None, 'https://avataaars.com/'), 'avataaars-neutral': ('free-personal-and-commercial', 'https://avataaars.com/', 'Pablo Stanley', 'https://twitter.com/pablostanley', None, 'https://avataaars.com/'), 'big-ears': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'The Visual Team', 'https://thevisual.team/', 'Face Generator', 'https://www.figma.com/community/file/986078800058673824'), 'big-ears-neutral': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'The Visual Team', 'https://thevisual.team/', 'Face Generator', 'https://www.figma.com/community/file/986078800058673824'), 'big-smile': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'Ashley Seo', 'http://www.ashleyseo.com/', 'Custom Avatar', 'https://www.figma.com/community/file/881358461963645496'), 'bottts': ('free-personal-and-commercial', 'https://bottts.com/', 'Pablo Stanley', 'https://twitter.com/pablostanley', None, 'https://bottts.com/'), 'bottts-neutral': ('free-personal-and-commercial', 'https://bottts.com/', 'Pablo Stanley', 'https://twitter.com/pablostanley', None, 'https://bottts.com/'), 'croodles': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'vijay verma', 'https://vjy.me/', 'Croodles - Doodle your face', 'https://www.figma.com/community/file/966199982810283152'), 'croodles-neutral': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'vijay verma', 'https://vjy.me/', 'Croodles - Doodle your face', 'https://www.figma.com/community/file/966199982810283152'), 'dylan': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'Natalia Spivak', 'https://nataspvk.tilda.ws/', 'Dylan! The Avatar Generator', 'https://www.figma.com/community/file/1356575240759683500'), 'fun-emoji': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'Davis Uche', 'https://www.instagram.com/davedirect3/', 'Fun Emoji Set', 'https://www.figma.com/community/file/968125295144990435'), 'glass': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'DiceBear', 'https://www.dicebear.com', 'Glass', 'https://www.dicebear.com'), 'icons': ('mit', 'https://opensource.org/licenses/MIT', 'The Bootstrap Authors', None, None, None), 'identicon': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'DiceBear', None, None, 'https://www.dicebear.com'), 'initials': ('mit', 'https://opensource.org/licenses/MIT', 'Florian Körner', None, None, None), 'lorelei': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'Lisa Wischofsky', 'https://www.instagram.com/lischi_art/', 'Lorelei', 'https://www.figma.com/community/file/1198749693280469639'), 'lorelei-neutral': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'Lisa Wischofsky', 'https://www.instagram.com/lischi_art/', 'Lorelei Neutral', 'https://www.figma.com/community/file/1198749693280469639'), 'micah': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'Micah Lanier', 'https://dribbble.com/micahlanier', 'Avatar Illustration System', 'https://www.figma.com/community/file/829741575478342595'), 'miniavs': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'Webpixels', 'https://webpixels.io/', 'Miniavs - Free Avatar Creator', 'https://www.figma.com/community/file/923211396597067458'), 'notionists': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'Zoish', 'https://bio.link/heyzoish', 'Notionists', 'https://heyzoish.gumroad.com/l/notionists'), 'notionists-neutral': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'Zoish', 'https://bio.link/heyzoish', 'Notionists', 'https://heyzoish.gumroad.com/l/notionists'), 'open-peeps': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'Pablo Stanley', 'https://twitter.com/pablostanley', 'Open Peeps', 'https://www.openpeeps.com/'), 'personas': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'Draftbit', 'https://draftbit.com/', 'Personas by Draftbit', 'https://personas.draftbit.com/'), 'pixel-art': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'DiceBear', None, 'Pixel Art', 'https://www.figma.com/community/file/1198754108850888330'), 'pixel-art-neutral': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'DiceBear', None, 'Pixel Art Neutral', 'https://www.figma.com/community/file/1198754108850888330'), 'rings': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'DiceBear', 'https://www.dicebear.com', 'Rings', 'https://www.dicebear.com'), 'shapes': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'DiceBear', None, None, 'https://www.dicebear.com'), 'thumbs': ('cc0-1.0', 'https://creativecommons.org/publicdomain/zero/1.0/', 'DiceBear', None, None, 'https://www.dicebear.com'), 'toon-head': ('cc-by-4.0', 'https://creativecommons.org/licenses/by/4.0/', 'Johan Melin', 'https://www.johanmelin.com', 'ToonHead', 'https://www.figma.com/community/file/1589627891082866389')}*

style name -> its DESIGN licence. Absent from this table means “unverified”,
which is refused rather than assumed permissive.

### an.characters.licenses.FREE_PERSONAL_AND_COMMERCIAL *= 'free-personal-and-commercial'*

Pablo Stanley’s own terms. Permissive in effect, not a CC licence, and not
something to silently relabel as one.

### an.characters.licenses.NO_ATTRIBUTION_REQUIRED *: frozenset[str]* *= frozenset({'cc0-1.0', 'free-personal-and-commercial', 'mit'})*

Licences that need no credit from whoever ships the output.

### *class* an.characters.licenses.StyleLicense(license, license_url, author, author_url, source_title, source_page_url)

Bases: `NamedTuple`

One style’s design licence and the credit it obliges.

#### author *: str | None*

Alias for field number 2

#### author_url *: str | None*

Alias for field number 3

#### license *: str*

Alias for field number 0

#### license_url *: str | None*

Alias for field number 1

#### source_page_url *: str | None*

Alias for field number 5

#### source_title *: str | None*

Alias for field number 4

### an.characters.licenses.attribution_for(style)

DiceBear’s own attribution template, filled in. `None` when none is owed.

The wording is theirs, verbatim from the per-style package README, including
the “Remix of the original” half — which is what discharges CC BY’s
“indicate if changes were made” clause. `an` wraps the avatar into a rig, so
it genuinely produces a modified work.

* **Return type:**
  `str` | `None`

### an.characters.licenses.dicebear_source(style, , seed)

Build the provenance record for a DiceBear avatar.

Raises on an unlisted style rather than returning an empty record: “we did
not check” and “there is nothing to discharge” must not look the same, and
a `None` licence silently reads as the latter everywhere downstream.

* **Return type:**
  AssetSource

### an.characters.licenses.requires_acknowledgement(style)

Whether using `style` puts a duty on whoever ships the output.

An unlisted style counts as requiring acknowledgement — an unverified
licence is a refusal, not a warning.

* **Return type:**
  `bool`
