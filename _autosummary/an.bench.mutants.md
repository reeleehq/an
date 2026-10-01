# an.bench.mutants

The guard mutants: “I mutation-tested it” as a runnable artifact, not a claim.

Wave 1 shipped three guards that stayed green when the bug they guarded was
reintroduced — one flagged the sentence *explaining* a deprecation, one
exonerated everything via neighbouring prose, and one keyed on a string the fix
itself removed. Wave 2’s own an#36 sweep lost five mutants, two of them to
guards that asserted a table’s *contents* rather than the check that reads it.

Every commit in this wave has said “N mutants, all caught”. That sentence is
unfalsifiable after the fact: the mutations lived in a scratch script and were
thrown away. This module is the correction — each one is **declared data**, so
a future reader can re-run the proof instead of trusting the commit message.

Three properties the declaration is shaped to have:

**Each mutant names the guard it must break.** A mutation nobody expected to be
caught is a fact about the code; a mutation with a named catcher is a claim
about a *test*, and that is what is worth pinning.

\*\*The whole file runs, never a `-k` filter.\*\* A filter that happens to exclude
the catching test reports “not caught” and sends the reader to write a test
that already exists.

\*\*The `old` text is pinned exactly.\*\* A mutant whose source text has moved is
a mutant that silently stops proving anything, so
`tests/test_bench_mutation.py` asserts every site still exists — cheaply, in
the default CI leg, with no pytest subprocesses at all. The full sweep is
`an bench-mutants`: it is a deliberate act, and it takes about half a minute.

**A killed sweep must not leave the tree mutated** (an#67), and that is two
mechanisms rather than one, because they cover different kills. SIGTERM is
turned into an exception for the duration ([`restore_on_termination()`](#an.bench.mutants.restore_on_termination)) so
the restoring `finally` runs; SIGKILL cannot be caught by anything, so
[`check_sites()`](#an.bench.mutants.check_sites) — which every sweep runs first, and which the default CI leg
runs too — recognises a file whose mutated text is present and whose original is
gone, and reports it as an interrupted run with the exact repair. The recovery
path is the load-bearing half: what makes a leftover dangerous is that every
mutation here is chosen to be *plausible*, so the tree compiles, renders and
stays green apart from one test, and a developer can commit it without noticing.
That recovery reads “the mutation is present and the original is gone”, which is
an assumption about the DECLARATION — so `check_sites` also refuses a mutant
whose substitution leaves its own `old` text behind, because such a mutant is
invisible to the recovery and a later sweep would restore *to* the leftover.

### Module Attributes

| [`PYTEST_ARGS`](#an.bench.mutants.PYTEST_ARGS)           | see the module docstring.                                                                                                                                                                                                                                                                                                                                     |
|------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`RESTORE_ON_SIGNALS`](#an.bench.mutants.RESTORE_ON_SIGNALS)    | Terminating signals turned into an exception for the duration of a sweep, so the restoring `finally` runs.                                                                                                                                                                                                                                                    |
| [`INTERRUPTED_EXIT_CODE`](#an.bench.mutants.INTERRUPTED_EXIT_CODE) | the shell convention of 128 + SIGINT.                                                                                                                                                                                                                                                                                                                         |
| [`SWEEP_COPY_IGNORE`](#an.bench.mutants.SWEEP_COPY_IGNORE)     | Left out of a sweep's throwaway tree.                                                                                                                                                                                                                                                                                                                         |
| [`MUTANTS`](#an.bench.mutants.MUTANTS)               | A representative sweep rather than an exhaustive one, chosen so each entry pins a *different* class of failure: a silently widened comparison, a guard that reads the same table twice, a refusal that stops refusing, an unknown-is-not-zero substitution, a decoder that only works on its own output, and an instrument that goes blind without saying so. |
| [`RESTORE_TMP_SUFFIX`](#an.bench.mutants.RESTORE_TMP_SUFFIX)    | Suffix for the sibling file the restore is staged through.                                                                                                                                                                                                                                                                                                    |

### Functions

| [`check_sites`](#an.bench.mutants.check_sites)([root])               | Problems with the declarations themselves, as a list of sentences.           |
|------------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`format_results`](#an.bench.mutants.format_results)(results)           | The digest, with the survivors and errors last because they are the finding. |
| [`restore_on_termination`](#an.bench.mutants.restore_on_termination)([signals]) | Turn a terminating signal into an exception for the duration.                |
| [`run_mutants`](#an.bench.mutants.run_mutants)([names, root])        | Apply each mutant, run its whole guard file, restore, and report.            |
| [`sweep_tree`](#an.bench.mutants.sweep_tree)(source)                | A throwaway copy of `source` for a sweep to do its damage in.                |
| [`verdict_of`](#an.bench.mutants.verdict_of)(result)                | `CAUGHT` / `SURVIVED` / `ERRORED`, as three separate answers.                |

### Classes

| [`Mutant`](#an.bench.mutants.Mutant)(name, file, old, new, caught_by, why)   | One deliberate defect, and the guard that must notice it.   |
|-------------------------------------------------------------------------------------------------|-------------------------------------------------------------|

### Exceptions

| [`MutantError`](#an.bench.mutants.MutantError)          | A declared mutant no longer applies, or the tree was left dirty.       |
|-----------------------------------------------------------------------|------------------------------------------------------------------------|
| [`MutantRunInterrupted`](#an.bench.mutants.MutantRunInterrupted) | A terminating signal arrived mid-sweep, raised so the restore can run. |

### an.bench.mutants.INTERRUPTED_EXIT_CODE *: int* *= 130*

the shell convention of
128 + SIGINT. Nonzero, and distinguishable from the 1 a surviving mutant
gives — “you stopped it” and “a guard is decoration” are different answers.

* **Type:**
  What the CLI exits with after an interrupted sweep

### an.bench.mutants.MUTANTS *: tuple[[Mutant](#an.bench.mutants.Mutant), ...]* *= (Mutant(name='png_paeth_tiebreak', file='an/bench/png.py', old='if (pa <= pb and pa <= pc) else (b if pb <= pc else c)', new='if (pa <= pb and pa <= pc) else (b if pb < pc else c)', caught_by='tests/test_bench_png.py', why="the Paeth predictor's tie-break. Wrong, it still decodes this module's own filter-0 output perfectly and corrupts every real Chromium frame — the exact asymmetry that makes an encoder validating its own decoder worthless."), Mutant(name='png_first_idat_only', file='an/bench/png.py', old='            idat.append(payload)', new='            idat = [payload]', caught_by='tests/test_bench_png.py', why='Chromium splits the stream: a real frame has 2-9 IDAT chunks and our own output has one, so a first-chunk-only reader passes its own tests and fails on everything else.'), Mutant(name='png_no_write_verification', file='an/bench/png.py', old='    if not np.array_equal(decode_png(out.read_bytes()), np.asarray(rgb)):', new='    if False:', caught_by='tests/test_bench_png.py', why="the only thing between a bug in this module's own encoder and a committed golden that silently disagrees with the frame it was blessed from."), Mutant(name='golden_criterion_becomes_file_bytes', file='an/bench/golden.py', old='    digest.update(f"{arr.dtype.str}:{arr.shape}|".encode("ascii"))', new='    pass', caught_by='tests/test_bench_golden.py', why='\`ndarray.tobytes()\` carries no shape, so a transposed frame hashes identically and satisfies the criterion an#38 literally states.'), Mutant(name='golden_blesses_a_blank_reason', file='an/bench/golden.py', old='    if not reason.strip():', new='    if reason is None:', caught_by='tests/test_bench_golden.py', why='a re-bless with no recorded reason is the same failure as a silently widened threshold — the named failure mode this wave exists to end.'), Mutant(name='golden_blesses_an_identical_pair', file='an/bench/golden.py', old='            if np.array_equal(decoded[i], decoded[j]):', new='            if False:', caught_by='tests/test_bench_golden.py', why='measured on \`promote_demo\`: frame 0 and the duration/2 frame differ by ZERO pixels, so the obvious second time blesses one picture twice and the second golden tests nothing forever after.'), Mutant(name='compare_gains_a_tolerance_band', file='an/bench/compare.py', old='    if before == after:\\n        return "no_change"', new='    if abs(float(before) - float(after)) < 1e-9:\\n        return "no_change"', caught_by='tests/test_bench_compare.py', why='two consecutive runs on one machine are bit-identical, so a band can only ever hide a true movement.'), Mutant(name='compare_refuses_on_an_absent_key', file='an/bench/compare.py', old='        elif b is \_ABSENT or a is \_ABSENT:', new='        elif False:', caught_by='tests/test_bench_compare.py', why='the ledger grows additively, so treating absence as difference makes every future field retroactively destroy comparability with every row already written.'), Mutant(name='compare_counts_metrics_not_families', file='an/bench/compare.py', old='        block["family_count"] = len(families)', new='        block["family_count"] = sum(len(v) for v in families.values())', caught_by='tests/test_bench_compare.py', why="counting bare metrics is satisfiable by shipping one signal under three names, which is exactly what family A's three edge metrics would do."), Mutant(name='compare_exempts_the_whole_environment', file='an/bench/compare.py', old='        touched = {t.label for t in MUTATION_TOUCHES.get(mutation, ())}', new='        touched = {i["key"] for i in common + render + encode}', caught_by='tests/test_bench_compare.py', why='the knob the lever pulls is the independent variable; the ISA is not. A blanket exemption lets a row from another machine in through the same door.'), Mutant(name='compare_exempts_by_path_not_by_value', file='an/bench/registry.py', old='        if self.differs_only_in is None:\\n            return True', new='        if True:\\n            return True', caught_by='tests/test_bench_compare.py', why="\`x264_argv\` is the WHOLE encode command, so exempting the path exempts every flag in it. A \`-preset medium\` -> \`-preset veryslow\` change moves every encode-side number and rode in as 'the lever moved it — expected'. The exemption must match the change the lever actually makes."), Mutant(name='compare_trusts_an_edited_prediction', file='an/bench/compare.py', old='    if not isinstance(inline, dict) or not isinstance(declared, dict):\\n        return []', new='    if True:\\n        return []', caught_by='tests/test_bench_compare.py', why="the prediction IS the criterion, and it is read from the after row's inline block alone. Flipping one \`expect\` turns \`contrary\` into \`as_declared\` with nothing else in the report moving — the cheapest possible way to fake a caught mutation."), Mutant(name='compare_lets_a_row_forge_its_own_scope', file='an/bench/compare.py', old='    "comparison_scope",\\n    "reference",', new='    "reference",', caught_by='tests/test_bench_compare.py', why="\`comparison_scope\` decides whether a metric may be compared ACROSS MACHINES, and \`compare\` reads the row's INLINE copy. Editing that one word compared an encode-side metric across a different ISA with no refusal — the single invariant this module exists to hold, defeated from inside the row."), Mutant(name='ledger_substitutes_zero_for_unknown', file='an/bench/ledger.py', old='        if self.state == "measured":\\n            if self.value is None:', new='        if self.state == "measured":\\n            if False:', caught_by='tests/test_bench_ledger_schema.py', why='a substituted number — 0.0 especially — is read downstream as a measurement, which is the unknown-is-not-zero failure the whole schema exists to prevent.'), Mutant(name='ledger_lets_a_tripwire_vanish', file='an/bench/ledger.py', old='    absent_tw = sorted(set(TRIPWIRES) - set(tripwires))', new='    absent_tw = []', caught_by='tests/test_bench_ledger_schema.py', why='a change detector that quietly stopped being computed reads exactly like one that fired and found nothing.'), Mutant(name='registry_counts_a_tautology', file='an/bench/registry.py', old='        if self.expect in ("no_change", "not_applicable") and self.counts:', new='        if False:', caught_by='tests/test_bench_ledger_schema.py', why="'no change by construction' is a tautology; counting it lets any pre-encode statistic pad the witness count for free."), Mutant(name='golden_fabricates_a_zero_pixel_count', file='an/bench/golden.py', old='"changed_px": max((int(f["changed_px"]) for f in compared), default=None),', new='"changed_px": max((int(f["changed_px"] or 0) for f in frames), default=0),', caught_by='tests/test_bench_golden.py', why="a shape mismatch has no per-pixel comparison to count, and turning that into 0 printed 'GOLDEN MISMATCH: 0 px changed' — a fabricated number in the one schema whose whole premise is that unknown is not zero."), Mutant(name='compare_scope_absence_fails_open', file='an/bench/compare.py', old='        if scope not in env_refusals:', new='        if False:', caught_by='tests/test_bench_compare.py', why="an absent \`comparison_scope\` read as 'no refusals apply', so an encode-side metric from another ISA and another x264 build compared cleanly and reported a regression."), Mutant(name='strict_passes_a_comparison_that_compared_nothing', file='an/tools.py', old='            not report.get("answered")', new='            False', caught_by='tests/test_bench_compare.py', why="the documented CI gate exited 0 on a run in which every scene was refused, while printing '0 regression(s)' — a zero the compare module's own docstring calls worse than no number at all."), Mutant(name='cli_returns_nothing_to_the_terminal', file='an/_\_main_\_.py', old='        if result is not None:\\n            typer.echo(result)', new='        pass', caught_by='tests/test_cli_dispatch.py', why='typer discards return values and every \`an.tools\` function returns its report as a string, so the CLI would run correctly and print NOTHING — the worst possible failure for a diagnostic tool.'), Mutant(name='cli_loses_the_signature_that_is_the_command_line', file='an/_\_main_\_.py', old='    @functools.wraps(func)\\n    def run(', new='    def run(', caught_by='tests/test_cli_dispatch.py', why='\`inspect.signature\` follows \`_\_wrapped_\_\`, and that signature IS the command line. Without it typer sees \`(\*args, \*\*kwargs)\` and every flag on all 17 commands disappears at once, while \`--help\` still renders.'), Mutant(name='corpus_reads_shot_order_from_the_directory', file='an/bench/corpus.py', old='    for shot_id in order:\\n        shot_dir = root / f"shot_{shot_id}"', new='    for shot_dir in sorted(root.glob(SHOT_DIR_GLOB)):\\n        shot_id = shot_dir.name[len("shot_") :]', caught_by='tests/test_bench_corpus.py', why="\`an/render.py\` concatenates in timeline order; a directory sort agrees only by luck, and when it does not every encode-side metric pairs one shot's source frames against another's decode."), Mutant(name='reshape_checks_divisibility_not_shape', file='an/bench/imageio.py', old='    if frames is not None and len(buf) != per_frame \* frames:', new='    if False:', caught_by='tests/test_bench_shape_guard.py', why='a k-times supersample makes the decoded buffer exactly k\*\*2 larger, so a divisibility check ALWAYS passes and family A is computed over k\*\*2 as many scrambled frames — plausibly, because at k=2 most horizontal runs survive the wrong reshape.'), Mutant(name='bench_measures_a_supersampled_render', file='an/bench/run.py', old='        if sizes != {capture.resolution}:', new='        if False:', caught_by='tests/test_bench_shape_guard.py', why="\`capture.resolution\` comes from the staged scene's meta and never from a file, so without an independent read of the PNGs' own IHDRs nothing in the pipeline ever compares the declared size to the size on disk."), Mutant(name='png_dimensions_trusts_a_non_ihdr_first_chunk', file='an/bench/png.py', old='    if data[_IHDR_TAG] != b"IHDR":', new='    if False:', caught_by='tests/test_bench_png.py', why='without the tag check the four bytes that happen to sit at offset 16 are returned as a resolution — a plausible number fed straight into the shape guard, which is the failure class an#54 closes.'), Mutant(name='read_png_dimensions_reads_the_whole_file', file='an/bench/png.py', old='        return png_dimensions(handle.read(PNG_HEADER_BYTES))', new='        return png_dimensions(handle.read())', caught_by='tests/test_bench_png.py', why='the answer stays right and the cost stops being free: the bench reads one of these per frame of every shot, and a 1080p frame is megabytes against a 24-byte header.'), Mutant(name='strict_exits_zero_on_a_row_it_cannot_read', file='an/tools.py', old='        if strict:\\n            print(refusal)', new='        if False:\\n            print(refusal)', caught_by='tests/test_bench_compare.py', why='the documented CI gate exited 0 on an unreadable schema_version or an undeclared --mutation — precisely the state a \`--strict --mutation supersample\` run is in before the lever is registered. Same class an#51 closed for the refusal path.'), Mutant(name='latest_rows_orders_by_filename', file='an/bench/compare.py', old='    return sorted(rows, key=key)[-count:]', new='    return sorted(rows, key=lambda p: p.name)[-count:]', caught_by='tests/test_bench_compare.py', why="filenames are <date>-<sha7>.json, so within one date the order is sha HEX order. A re-baseline and its after-run on the same day swap silently when the after-commit's sha sorts lower, and every improvement is then reported as a regression."), Mutant(name='compare_hides_that_a_row_was_blessed', file='an/bench/compare.py', old='            "blessed_scenes": sorted(after["provenance"].get("blessed") or ()),', new='            "blessed_scenes": [],', caught_by='tests/test_bench_compare.py', why="a bless run gates family B \`blessed_this_run\`, and \`format_comparison\` skips \`unchanged\` entries — so family B vanishes from the table entirely. 'Family B agreed' and 'family B was never asked' are the same blank space."), Mutant(name='capture_inherits_the_previous_renders_shots', file='an/bench/capture.py', old='IGNORED_RELPATHS_ON_COPY: tuple[str, ...] = ("artifacts/shots",)', new='IGNORED_RELPATHS_ON_COPY: tuple[str, ...] = ()', caught_by='tests/test_bench_corpus.py', why="\`mall['shots']\` is \`<project>/artifacts/shots\`, and it is gitignored — so a previous render's per-shot mp4s cross into every bench run on a developer machine and on no clean checkout, in the module whose docstring is 'do not inherit a stale render'."), Mutant(name='capture_excludes_shots_by_basename_at_any_depth', file='an/bench/capture.py', old='            n for n in names if prefix + n in IGNORED_RELPATHS_ON_COPY', new='            n\\n            for n in names\\n            if n in {p.rsplit("/", 1)[-1] for p in IGNORED_RELPATHS_ON_COPY}', caught_by='tests/test_bench_corpus.py', why="the obvious \`shutil.ignore_patterns('shots')\` spelling, restated. It fnmatches BASENAMES against the names in every directory, so it also deletes a character rig's \`assets/.../shots\` — and the other obvious spelling, \`'artifacts/shots'\` as a pattern, matches NOTHING, because no name contains a separator. Both fail silently."), Mutant(name='bless_names_its_row_after_the_tree_it_did_not_leave', file='an/bench/run.py', old='    return git_state(root) if blessed else git', new='    return git', caught_by='tests/test_bench_bless_protocol.py', why='\`git_state\` is read before the corpus loop and a \`--bless\` run writes inside it, so a bless on a clean tree filed itself as \`<date>-<sha>.json\` — a filename naming a commit whose tree that very run then modified, which is what the \`-dirty\` suffix exists to prevent.'), Mutant(name='golden_trusts_a_frame_its_own_record_disowns', file='an/bench/golden.py', old='        if expected is not None and expected != record["golden_sha256"]:', new='        if False:', caught_by='tests/test_bench_golden.py', why='the bless record and the committed PNG carry the same digest of the same file, written by two different calls. A disagreement means the golden is not the picture a human blessed — an edited file, a half-finished re-bless — and every one of those read as a clean PASS.'), Mutant(name='bench_asks_a_mutated_run_the_unmutated_question', file='an/tools.py', old='            compare_rows(load_row(compare), ledger, mutation=mutation or None)', new='            compare_rows(load_row(compare), ledger)', caught_by='tests/test_bench_mutation_cli.py', why="without the mutation, \`compare\` answers 'is the second row worse' of a run degraded on purpose — so the declared per-mutation predictions are never scored and the an#41 criterion cannot appear in the mandated \`--compare\` artifact at all."), Mutant(name='bench_blesses_a_deliberately_degraded_picture', file='an/tools.py', old='        if bless:\\n            return (\\n                "refusing --bless with --mutation: a lever renders a"', new='        if False:\\n            return (\\n                "refusing --bless with --mutation: a lever renders a"', caught_by='tests/test_bench_mutation_cli.py', why='blessing under a lever commits the degraded picture as the reference every future run is measured against — a permanent, silent re-baseline, and the one bless refusal that cannot be recovered by reading the recorded reason.'), Mutant(name='pix_fmt_knob_cannot_reach_the_encode', file='an/adapters/cutout/render.py', old='    resolved = pix_fmt or DEFAULT_PIX_FMT', new='    resolved = pix_fmt or "yuv420p"', caught_by='tests/test_encode_pins.py', why='reading the literal instead of the module global severs the seam any outside caller pulls — the same shape hoisting \`DETERMINISTIC_X264_ARGS\` into a default argument would sever for \`high_crf\`. That is why the seam is kept even though an#59 ships no lever — see the note there. (Until an#72 the row would ALSO have said 4:4:4 while the file stayed 4:2:0, because \`environment_record\` re-derived the format from the same global; it is measured off the delivered files now, so the row no longer lies about its own file — only the knob is broken.)'), Mutant(name='mux_argv_is_checked_by_subset_not_equality', file='an/adapters/cutout/render.py', old='        "-c:v",\\n        "libx264",\\n        "-pix_fmt",', new='        "-c:v",\\n        "libx264",\\n        "-tune",\\n        "animation",\\n        "-pix_fmt",', caught_by='tests/test_encode_pins.py', why='\`-tune animation\` is a measured-and-rejected flag (0.8%) and this is what adding it looks like. A SUBSET check passes — every pin is still present — and the encode moves and every encode-side metric is silently refused against every committed row. Only argv equality notices.'), Mutant(name='canvas_capture_flips_rows', file='an/adapters/cutout/canvas_capture.py', old='rgb = image.convert("RGB")', new='rgb = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).convert("RGB")', caught_by='tests/test_canvas_capture.py', why='the \`readPixels\` trap in reverse: WebGL readback is bottom-up and a PNG is top-down, so a capture path is one flip away from writing every frame upside down at exactly the declared size — past every shape check. The offline catcher is named here because a sweep runs the whole file per mutant; the browser equivalence gate (tests/test_canvas_capture_equivalence.py) catches the same flip in its own test.'), Mutant(name='capture_page_stops_compositing_the_canvas', file='an/data/cutout_runtime/index.html', old='#stage { display: block; }', new='#stage { display: none; }', caught_by='tests/test_cutout_runtime_files.py', why="an#57's proposal. The element screenshot (the \`--capture screenshot\` path, which shares this page with the canvas default) is a PAGE capture clipped to the element, so hiding the canvas does not make it cheaper — it makes \`Locator.screenshot\` time out after 30 s per frame. The two spellings Playwright does accept return an all-white frame."), Mutant(name='supersample_autodensity_true', file='an/data/cutout_runtime/runtime.js', old='            autoDensity: false,', new='            autoDensity: true,', caught_by='tests/test_bench_supersample_lever.py', why="\`autoDensity: true\` makes Chromium composite the k-times backbuffer down before the screenshot — a blind downscale with no filter choice and no record. The PNGs come out the DECLARED size, so every shape check passes and the whole knob silently measures nothing. It is the option whose name most suggests it is the right one. Lives on the PRODUCT's file since an#58, because the product owns the key."), Mutant(name='supersample_skips_the_frame_stage', file='an/bench/mutations.py', old='        render._capture_frames = \_capture_then_resolve', new='        render._capture_frames = original', caught_by='tests/test_bench_supersample_lever.py', why='drops the resolve, leaving k-times PNGs on disk. Before an#54 that was silent — \`_reshape\` checked byte-count divisibility and k\*\*2 always divides — and family A was computed on k\*\*2 scrambled frames that still produced a believable \`edge_transition_width\`. It is a loud refusal now, which is what makes this lever safe to run.'), Mutant(name='supersample_verify_is_merely_not_shipped', file='an/bench/mutations.py', old='    if recorded != expected:', new='    if False:', caught_by='tests/test_bench_supersample_lever.py', why="reduces the supersample fingerprint to \`disabled_aa\`'s inequality, which ANY render lever satisfies — both stage through one seam and both move \`render_side.runtime_sha256\`. A row rendered with \`antialias: false\` then verifies as a supersample row and the whole lever table is written from the wrong lever's numbers."), Mutant(name='edge_masked_colour_count_is_not_masked', file='an/bench/metrics.py', old='    per_frame = [len(np.unique(f[m])) for f, m in zip(packed, edge) if m.any()]', new='    per_frame = [len(np.unique(f)) for f, m in zip(packed, edge) if m.any()]', caught_by='tests/test_bench_metrics.py', why='unmasked it is \`frame_distinct_colours\` under a second name, and the one property the mask does buy — that an interior-only change cannot reach the number — is gone with no other symptom.'), Mutant(name='empty_edge_mask_reads_as_zero_colours', file='an/bench/metrics.py', old='        return float("nan"), 0', new='        return 0.0, 0', caught_by='tests/test_bench_metrics.py', why='a substituted zero is the largest possible DOWNWARD move in the one metric that exists to notice a downward move, on exactly the scenes where the number means nothing at all.'), Mutant(name='lossless_leg_pinned_to_420', file='an/bench/imageio.py', old='        "-pix_fmt",\\n        resolved,\\n        "-qp",', new='        "-pix_fmt",\\n        "yuv420p",\\n        "-qp",', caught_by='tests/test_bench_lossless_leg.py', why='a reference PINNED in the one dimension it has to track. The leg exists to be the plane libx264 received; \`-pix_fmt\` names what libx264 receives, so pinning it does not keep the reference lossless — it makes the reference a different colour pipeline from the delivered file, and every encode-side metric silently acquires the whole 4:2:0 conversion the reference exists to cancel. Distinct from every other entry here because the mutated code stays correct on the default path and is wrong only under a knob: measured on the corpus at 4:4:4, it changes the SIGN of family E on three of ten scenes (an#72).'), Mutant(name='sweep_never_finds_a_reversal', file='an/bench/compare.py', old='    unstable = tally["increase"] > 0 and tally["decrease"] > 0', new='    unstable = tally["increase"] > 0 and tally["decrease"] < 0', caught_by='tests/test_bench_compare.py', why="the robustness gate that stops being able to fire. Every row still carries its sweep and every report still prints a \`sweep\` block reading \`stable\`, so the instrument looks exactly like one that checked and found nothing — while \`graded_field\`'s +84.2% at tol 6, which is -81.6% at tol 8, counts toward family D again (an#140)."), Mutant(name='sweep_counts_a_different_statistic', file='an/bench/metrics.py', old='int((dev > t).sum())', new='int((dev >= t).sum())', caught_by='tests/test_bench_metrics.py', why="a sweep of a statistic the row does not report. Off by one code value, every cell stays a plausible, monotone survival count, and the comparer then certifies the robustness of \`>=\` while the ledger's number is \`>\` (an#140)."), Mutant(name='sweep_deletion_is_excused', file='an/bench/compare.py', old='    spec = declared.get("threshold_sweep")\\n', new='    spec = None\\n', caught_by='tests/test_bench_compare.py', why="a row that declares a threshold sweep and carries none reads as 'written before an#140' — so deleting one field from a row turns an \`unstable\` verdict back into a counted witness, the cheapest possible way to fake a caught mutation."), Mutant(name='strict_passes_an_unstable_movement', file='an/tools.py', old='else bool(report.get("has_regressions") or report.get("unstable"))', new='else bool(report.get("has_regressions"))', caught_by='tests/test_bench_compare.py', why="\`unstable\` is neither a regression nor a pass; with no mutation it means some cell of the metric's own grid got worse. A CI gate that exits 0 on it reads 'cannot tell' as 'fine' (an#140)."))*

A representative sweep rather than an exhaustive one, chosen so each entry
pins a *different* class of failure: a silently widened comparison, a guard
that reads the same table twice, a refusal that stops refusing, an
unknown-is-not-zero substitution, a decoder that only works on its own
output, and an instrument that goes blind without saying so.

### *class* an.bench.mutants.Mutant(name, file, old, new, caught_by, why)

Bases: `object`

One deliberate defect, and the guard that must notice it.

#### caught_by *: str*

The test file that must go red. The whole file runs.

#### file *: str*

Repo-relative path of the file to break.

#### old *: str*

Exact source text to replace. Must occur **exactly once**.

### *exception* an.bench.mutants.MutantError

Bases: `RuntimeError`

A declared mutant no longer applies, or the tree was left dirty.

### *exception* an.bench.mutants.MutantRunInterrupted

Bases: `KeyboardInterrupt`

A terminating signal arrived mid-sweep, raised so the restore can run.

Derived from `KeyboardInterrupt` — a `BaseException` — rather than from
`Exception`, on purpose: an `except Exception` anywhere between here and
the top would swallow it and the sweep would carry on with a mutated file on
disk, which is the outcome the whole mechanism exists to prevent.

### an.bench.mutants.PYTEST_ARGS *: tuple[str, ...]* *= ('-q', '--no-header', '--tb=no', '-p', 'no:cacheprovider')*

see the module docstring. No
`--cache-provider` so a failed mutant cannot leave a `--lf` trail behind.

* **Type:**
  pytest flags for a mutant run. No `-k`

### an.bench.mutants.RESTORE_ON_SIGNALS *: tuple[int, ...]* *= (Signals.SIGTERM, Signals.SIGHUP)*

Terminating signals turned into an exception for the duration of a sweep, so
the restoring `finally` runs. SIGINT is deliberately absent: it already
raises `KeyboardInterrupt`, and re-handling it would only replace a working
mechanism. Built from what the platform actually has — Windows has no SIGHUP,
and asking for one is an `AttributeError` at import time.

### an.bench.mutants.RESTORE_TMP_SUFFIX *: str* *= '.an-restore-tmp'*

Suffix for the sibling file the restore is staged through. Same directory, so
`os.replace` is a rename within one filesystem and therefore atomic.

### an.bench.mutants.SWEEP_COPY_IGNORE *: tuple[str, ...]* *= ('_\_pycache_\_', '.pytest_cache', '.ruff_cache', '.venv', 'node_modules', 'out')*

Left out of a sweep’s throwaway tree. Caches and build output only —
**\`.git\` IS copied**, because six of the thirteen guard files call
`dirty_paths` or `repo_root`, and a tree with no history fails them for the
wrong reason. Measured at 0.26 s for this repository, once per sweep.

### an.bench.mutants.check_sites(root=None)

Problems with the declarations themselves, as a list of sentences.

Separate from running them because it is nearly free and catches the failure
that matters most: a refactor moved the code, so a mutant no longer applies
and has silently stopped proving anything.

* **Return type:**
  `list`[`str`]

### an.bench.mutants.format_results(results)

The digest, with the survivors and errors last because they are the finding.

* **Return type:**
  `str`

### an.bench.mutants.restore_on_termination(signals=(Signals.SIGTERM, Signals.SIGHUP))

Turn a terminating signal into an exception for the duration.

`run_mutants` restores in a `finally`, which covers everything that
*raises* — an exploding pytest, Ctrl-C — and covers nothing about SIGTERM,
which stops the interpreter without raising, so no `finally` runs and the
mutated file stays on disk. A `kill`, a timeout, an agent harness reaping a
background task and a closing terminal are all SIGTERM, and the sweep is
slow enough that interrupting it is the normal thing to do.

The previous handlers are restored on the way out, because this module is
importable and a library that permanently rewires SIGTERM is a worse defect
than the one it fixes. Yields the signals it actually took, which is empty
off the main thread (`signal.signal` refuses there), on a platform that
will not have them, and for any signal arriving already `SIG_IGN` — a
caller that wants to *report* the coverage can, and the restore itself never
depends on it.

An inherited `SIG_IGN` is left alone. `nohup` and most detach wrappers
ignore SIGHUP so a long job survives the terminal closing, and a sweep is
exactly the job someone detaches; taking the signal there would convert a
deliberately-protected run into a partial one exiting 130. There is nothing
to protect against either way — a signal that is ignored is never delivered,
so it cannot leave a mutation on disk.

**SIGKILL cannot be handled at all**, which is why the recovery path in
[`check_sites()`](#an.bench.mutants.check_sites) is the load-bearing half of this fix and this is the
convenience.

* **Return type:**
  `Iterator`[`tuple`[`int`, `...`]]

### an.bench.mutants.run_mutants(names=None, , root=None)

Apply each mutant, run its whole guard file, restore, and report.

\*\*With no `root`, the sweep runs against a COPY of the repository\*\* and the
real working tree is never written (an#124). See [`sweep_tree()`](#an.bench.mutants.sweep_tree) for why
that is not merely tidiness. An explicit `root` is swept IN PLACE, because a
caller who names a tree has already chosen a throwaway.

Restoration is in a `finally` and rewrites the ORIGINAL text rather than
reversing the substitution: a reversal that itself failed would leave the
tree broken, which is a worse outcome than any mutant surviving.

A `finally` covers everything that *raises*, which is why the loop runs
inside [`restore_on_termination()`](#an.bench.mutants.restore_on_termination): SIGTERM does not raise. What no
handler can cover is SIGKILL, so `check_sites` — which runs first, here —
also recognises a file left mutated by a previous kill and says so in those
words rather than as declaration rot.

* **Return type:**
  `list`[`dict`]

### an.bench.mutants.sweep_tree(source)

A throwaway copy of `source` for a sweep to do its damage in.

\*\*A sweep mutates real source files, and every mutation here is chosen to be
plausible\*\* — it compiles, it renders, and the suite stays green apart from
the one test that names it. So a concurrent reader of the working tree does
not get an error, it gets a believable wrong answer. That reader is not
hypothetical: `test_a_representative_mutant_is_really_caught` runs in the
DEFAULT leg, so a plain `pytest -q` mutates `an/bench/compare.py` for a few
seconds, and a second suite, an editor re-indexing, a `git status` from
another shell or a lint job sees it (an#124 — three pytest processes against
one checkout, and which of them owned the file’s contents was unanswerable).

Copying is what makes that structurally impossible rather than merely
coordinated. A lock would order the *writers*; it cannot reach a reader that
never took it.

It also retires an#67’s hazard for this path: a sweep killed by SIGKILL can
now only leave a mutated file inside a temp directory that nothing reads.

* **Return type:**
  `Iterator`[`Path`]

### an.bench.mutants.verdict_of(result)

`CAUGHT` / `SURVIVED` / `ERRORED`, as three separate answers.

`ERRORED` is not a third flavour of caught: a mutant that stops the guard
file from being collected has demonstrated nothing about the guard.

* **Return type:**
  `str`
