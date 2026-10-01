# an.characters.record

Record a character’s preview HTML to an mp4.

Uses Playwright’s video recording (saved as webm) and converts to mp4
via ffmpeg. The result is a real video file showing the new SVG
character art animating: cycling visemes + breath/head-tilt.

This is a stop-gap until Phase 11b wires the SVG-texture path into
`runtime.js` and proper scene rendering uses the new character art
directly.

```pycon
>>> # Smoke-tested in tests/test_characters_record.py
```

### Functions

| [`record_character`](#an.characters.record.record_character)(char_dir, \*[, name, ...])      | Render preview.html for the character at `char_dir` and record it.   |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`record_preview_to_mp4`](#an.characters.record.record_preview_to_mp4)(preview_html, out_mp4, \*) | Record `preview_html` to `out_mp4` for `duration_s` seconds.         |

### Exceptions

| [`PreviewRecordError`](#an.characters.record.PreviewRecordError)   | Raised when preview recording fails.   |
|-----------------------------------------------------------------------|----------------------------------------|

### *exception* an.characters.record.PreviewRecordError

Bases: `RuntimeError`

Raised when preview recording fails.

### an.characters.record.record_character(char_dir, , name=None, out_mp4=None, duration_s=8.0, size=(640, 480))

Render preview.html for the character at `char_dir` and record it.

The preview HTML is generated/refreshed via the same writer used by
`an character preview`, so this command is self-contained.

* **Return type:**
  `Path`

### an.characters.record.record_preview_to_mp4(preview_html, out_mp4, , duration_s=8.0, size=(640, 480), fps=30, crf=23)

Record `preview_html` to `out_mp4` for `duration_s` seconds.

Returns the output mp4 path.

Pipeline:

> 1. Playwright launches headless Chromium with video recording on.
> 2. Navigates to `preview_html` ([file://](file://) URL).
> 3. Waits `duration_s` real-time so the browser captures frames.
> 4. Closes the context to flush the webm.
> 5. ffmpeg re-encodes the webm to H.264 mp4 (better compatibility,
>    smaller files, plays in `quicktime` / GitHub previews).

Both Playwright (project dep) and ffmpeg (system dep, already
required by the renderer) must be installed.

* **Return type:**
  `Path`
