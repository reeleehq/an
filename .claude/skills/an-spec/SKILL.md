---
name: an-spec
description: Use when the user is starting a new an scene and needs help dialogically developing a scene specification — clarifying questions about characters, dialogue, art style, voices, pacing, and camera. Triggers on "let's design a scene", "I want to make a video about…", "help me sketch a cartoon", or any open-ended creative request handed to an.
---

# an-spec — interviewing the director

You're helping the user develop a scene specification that will end up as `scene.md` inside an `an` project. Your job is to ask the right questions, propose sensible defaults, check what already exists, and confirm before writing. Making the assets, writing the file and rendering are the **`an`** skill's job; this one ends with an approved draft.

The pipeline renders today: `an render <dir>` goes from `scene.md` to `output/main.mp4` with no API key (offline speech is silent, lip-sync is synthesized). Say so when the user asks "can it render" — and say what it costs: real speech needs `--tts elevenlabs` (a key) or `--tts mac_say` (macOS voices), and a style's `high` cost class (hand-drawn, many-piece puppets) means factory stand-ins until art is drawn or commissioned.

## Sequence

1. **Clarify the goal in one sentence.** "A 45-second 2D cartoon, two characters on a park bench" — get this nailed before anything else.
2. **Ask only what you can't reasonably default.** Defaults: 1920×1080, 30 fps (1280×720 renders about twice as fast — offer it for drafts), the `cutout` renderer, 30–60 s. Don't quiz the user on any of these unless they have an opinion.
3. **Walk the structural questions.**
   - Cast: how many characters, named or generic, their look (build, hat, hair, palette tell two people apart)
   - Setting: one environment or several, time of day, what is in front of the characters and what behind (planes at depths)
   - Beats: what happens in order
   - Dialogue: do characters speak, what about, voice tone and emotion (`[happy]`), delivery (`{sighs}`)
   - Camera: static, or which moves (push in, pull out, pan, tilt)
   - Look: a named style ("in the style of South Park / OverSimplified / Kurzgesagt / Reiniger …") or a palette and surface (outline, paper shadow, grain, gradient backdrops)
4. **Check the asset library before inventing anything** (`an library`, ADR 0005). Map the director's words onto the library's facets and capabilities (`an library vocabulary`), then search: `an library find --package cutan --kind character --style <style> --affords <capabilities> --near`. `--near` lists what nearly fits and the remedy for each gap (`an character add-views`, …). Offer a match by id (`cutan:character.alice-reiniger`) and say what it affords (`an library show <id>`): reuse is the default, a new character is the fallback. Do the same for environments, props and voices. Assets checked out into a project live in its own stores (`assets/characters/…`, `assets/environments/…`); `mall["characters"]` is that project's store, not the library.
   - For a reused character, read what it can do: `an character capabilities <name>` lists, per aspect (walk, speech, expression, turn), the method that will be used, the ones that apply and what the others are missing. Offer its declared swap sets by name (`hands`, `body_facing`, `eyelid`, a turnaround view) for direction like "she turns to face left" — never author a swap on a set or key the descriptor does not declare (compile refuses it, listing the declared ones).
   - A style that wants a capability the cast lacks (a silhouette film with mouth-chart lip-sync, a walk on a legless rig) falls back to a requirement-free default with a recorded substitution. Surface that in the spec rather than letting the render discover it.
5. **For a named look, use the `an-style` skill**: its style spec says what the look needs, what it costs, and how the render is measured against it. Record the style and its cost class in the spec.
6. **Echo the spec back as a draft `scene.md`** for approval before writing anything to disk — the shot list, entities (with the library ids you propose to check out), actions, dialogue and camera, in the blocks the `an` skill documents.

## What to ask only when relevant

- **Voice:** only if dialogue is in scope. Record the intent per character (pitch, tone, provider); the `an` skill's *Voices* section binds it (`voice_ref`, `mall["voices"]`, an ElevenLabs voice). Under the default offline TTS lines are silent but timed.
- **Timing per shot:** propose totals; offer to break into shots only if the user wants control. Real speech is longer than a script suggests (breaths, tails): leave room; once the audio is synthesized `an validate` warns when a line runs past its shot.
- **Renderer:** assume `cutout` unless the beat is mathematical (a `manim` shot inside the film) or purely typographic. The key is `renderer:` on a shot (`## Shot s1 (cutout)`) and `default_renderer:` in `meta`.
- **Commissioned art:** if the user wants real drawn characters, the **`an-art-package`** skill writes the brief and checks the delivery.

## What NOT to ask

- File paths, fps, resolution — defaults work. `an init --id <id> --genre cutout_animation` puts a project where agent-made videos go when the user names no directory.
- Backend choice — the orchestrator picks from each shot's `renderer`.

## Confirm-before-write

Always:

> "Here's the spec I have. Should I write this to `scene.md`, run `an validate`, and render a draft?"

If the user pushes for more detail, recurse on whichever section needs it. Once they approve, hand over to the **`an`** skill: check out or make the assets, write `scene.md`, `an validate`, `an render`. After a render, `scene.md` is still the file the user wrote (prose and formatting kept; a change rewrites only the blocks it touches), so edits can continue on it.
