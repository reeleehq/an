/**
 * an cutout runtime — Phase 2B
 *
 * Consumes the CutoutSceneJSON contract produced by an.adapters.cutout.compile
 * and renders into a PixiJS canvas. Exposes a small global API so a headless
 * driver (Playwright in Phase 2C) can inject a scene and step through frames.
 *
 * Globals (the only public surface):
 *   window.anLoadScene(sceneJsonObject) → builds the scene tree, registers
 *       animations + timeline. Returns true on success.
 *   window.anSetTime(t) → seeks to time t (seconds) and re-evaluates poses.
 *       A pure function of t: the picture never depends on earlier seeks (an#185).
 *   window.anCanvasReady() → resolves when the canvas is sized and PixiJS
 *       is initialized (so Playwright knows it's safe to screenshot).
 *   window.anCaptureFrames(requests) → seeks each requested instant in order
 *       and returns the canvas as PNG data URLs (the `capture="canvas"` path).
 *   window.anRuntimeVersion → '0.1.0'
 *
 * The runtime is deliberately self-contained: no module loader, no build step.
 * The HTML loads PixiJS first, then this file; PixiJS is available as window.PIXI.
 */
(function () {
    'use strict';

    const RUNTIME_VERSION = '0.1.0';
    const NS = window;

    NS.anRuntimeVersion = RUNTIME_VERSION;

    let app = null;        // PixiJS Application
    let scene = null;      // current CutoutSceneJSON
    let nodeIndex = {};    // path → PIXI.DisplayObject
    let visualIndex = {};  // path → { container, visual: PIXI.DisplayObject }
    let restIndex = {};    // 'target::prop' → restore-to-built function (an#185)
    let restOrder = [];    // restIndex's keys, in pose application order
    let pixiReady = false;

    // ------------------------------------------------------------------------
    // Easing — mirror an/adapters/cutout/easing.py for consistency
    // ------------------------------------------------------------------------

    const EASINGS = {
        linear: t => t,
        ease: t => (t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) ** 2),
        ease_in: t => t * t,
        ease_out: t => 1 - (1 - t) ** 2,
        ease_in_out: t => (t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) ** 2),
        step: t => (t < 1 ? 0 : 1),
    };

    function cubicBezier(cx1, cy1, cx2, cy2, t) {
        if (t <= 0) return 0;
        if (t >= 1) return 1;
        const bx = u =>
            3 * (1 - u) ** 2 * u * cx1 + 3 * (1 - u) * u * u * cx2 + u ** 3;
        const dbx = u =>
            3 * (1 - u) ** 2 * cx1 -
            6 * (1 - u) * u * cx1 +
            6 * (1 - u) * u * cx2 -
            3 * u * u * cx2 +
            3 * u * u;
        const by = u =>
            3 * (1 - u) ** 2 * u * cy1 + 3 * (1 - u) * u * u * cy2 + u ** 3;
        let u = t;
        for (let i = 0; i < 8; i++) {
            const f = bx(u) - t;
            const fp = dbx(u);
            if (Math.abs(fp) < 1e-12) break;
            u = Math.max(0, Math.min(1, u - f / fp));
        }
        return by(u);
    }

    function applyEasing(spec, t) {
        if (spec == null) return t;
        if (typeof spec === 'string') {
            const fn = EASINGS[spec];
            if (!fn) throw new Error('unknown easing: ' + spec);
            return fn(t);
        }
        if (Array.isArray(spec) && spec.length === 4) {
            return cubicBezier(spec[0], spec[1], spec[2], spec[3], t);
        }
        throw new Error('unsupported easing spec');
    }

    // ------------------------------------------------------------------------
    // Channel evaluation
    // ------------------------------------------------------------------------

    function evaluateChannel(channel, t) {
        const kfs = channel.keyframes;
        if (!kfs || kfs.length === 0) return null;
        if (kfs.length === 1) return kfs[0].value;
        const last = kfs[kfs.length - 1];
        if (t >= last.time) return last.value;
        if (t < kfs[0].time) return kfs[0].value;
        // Linear scan; fine for v0.1 (channels are short).
        let i = 0;
        for (; i < kfs.length - 1; i++) {
            if (kfs[i].time <= t && t < kfs[i + 1].time) break;
        }
        const a = kfs[i];
        const b = kfs[i + 1];
        const span = b.time - a.time;
        if (span <= 0) return b.value;
        const u = (t - a.time) / span;
        // Validated for every segment (a typo'd easing name must raise on a
        // swap channel too), but APPLIED only to numeric values.
        const eased = applyEasing(a.easing, u);
        if (typeof a.value === 'number' && typeof b.value === 'number') {
            return a.value + (b.value - a.value) * eased;
        }
        // Non-numeric (viseme codes, swap keys): snap on TIME, never on the
        // eased or raw parameter. The value is `a` for exactly
        // [a.time, b.time): easing cannot move the boundary (the old
        // eased-snap rule let an overshooting cubic bezier show the SECOND
        // key early, or flap A->B->A within one segment), and time has no
        // intermediate arithmetic (a raw-u snap is one float division away
        // from wrong: (t - a.time) / span can round up to 1.0 while
        // t < b.time). Mirror of an/adapters/cutout/channel.py::evaluate —
        // that function is the spec, and tests/test_cutout_channel_parity.py
        // pins the identity.
        return t >= b.time ? b.value : a.value;
    }

    // ------------------------------------------------------------------------
    // Scene → PIXI tree
    // ------------------------------------------------------------------------

    function buildSceneTree(node, parent, pathPrefix) {
        const path = pathPrefix ? pathPrefix + '/' + node.name : node.name;
        const container = new PIXI.Container();
        container.name = path;
        applyTransform(container, node.transform);
        nodeIndex[path] = container;

        if (node.visual) {
            const visual = makeVisual(node.visual);
            // an#163: the outline and the paper-gap shadow are COPIES of this
            // visual, added to the SAME container first so they draw behind
            // it — which is why a tween, a play or the camera moves them with
            // no channel of their own. Built once, from the document; nothing
            // here is a filter and nothing is random.
            for (const copy of makeUnderlays(node.visual, visual)) {
                container.addChild(copy);
            }
            if (node.visual.blend) {
                visual.blendMode = blendModeOf(node.visual.blend);
            }
            container.addChild(visual);
            visualIndex[path] = { container, visual };
        }

        for (const child of node.children || []) {
            buildSceneTree(child, container, path);
        }

        parent.addChild(container);
        return container;
    }

    function makeVisual(visualSpec) {
        if (visualSpec.kind === 'ellipse') {
            return makeEllipse(visualSpec);
        }
        if (visualSpec.kind === 'mouth') {
            // Procedural drawn mouth, initialized to the rest viseme. Its
            // swap vocabulary is DECLARED on the object (an#87): _anDrawSets
            // maps a set name to the redraw function, so the generic swap
            // path applies `viseme` here the same way it swaps textures on a
            // sprite — the set name is convention, not control flow.
            const g = new PIXI.Graphics();
            drawMouthShape(g, MOUTH_REST);
            g._anDrawSets = {
                viseme: {
                    keys: Object.keys(VISEME_SHAPES).sort(),
                    apply: drawMouthShape,
                    // What it was built showing: the pose a seek to before
                    // the first viseme key restores (an#185).
                    rest: MOUTH_REST,
                },
            };
            return g;
        }
        if (visualSpec.kind === 'eye') {
            return makeEye(visualSpec);
        }
        if (visualSpec.kind === 'svg_sprite') {
            return makeSvgSprite(visualSpec);
        }
        if (visualSpec.kind === 'path') {
            return makePath(visualSpec);
        }
        // sprite without textures + everything else falls back to a rect.
        return makeRect(visualSpec);
    }

    // ------------------------------------------------------------------------
    // Surface treatments (an#163). The compiler decides every copy, colour and
    // offset (an/adapters/cutout/surface.py); this only draws what the
    // document says. Blend modes are the engine's native ones — PixiJS 7 does
    // ADD and MULTIPLY in the blend equation, with no filter and no render
    // texture — so the determinism probe below still sees zero filters.
    // ------------------------------------------------------------------------

    const BLENDS = { add: 'ADD', multiply: 'MULTIPLY' };

    function blendModeOf(name) {
        const key = BLENDS[name];
        if (!key) {
            throw new Error(
                'unknown blend ' + JSON.stringify(name) + '. Known: ' +
                JSON.stringify(Object.keys(BLENDS).sort())
            );
        }
        return PIXI.BLEND_MODES[key];
    }

    function mulTint(a, b) {
        // Per-channel product of two packed RGB colours, rounded like the
        // tint channel's quantiser.
        const ch = (x, s) => (x >> s) & 0xff;
        const m = s => Math.round(ch(a, s) * ch(b, s) / 255);
        return (m(16) << 16) | (m(8) << 8) | m(0);
    }

    function fitUnderlay(main, copy) {
        // A sprite copy shares the main sprite's texture, anchor and scale,
        // then grows about the ART'S CENTRE (not the anchor) so its box gains
        // `grow` on every side. Re-run after every swap: the box follows the
        // texture.
        const g = copy._anGrow;
        const off = copy._anOffset;
        const w = main.width, h = main.height;  // displayed, absolute
        const sx = w > 0 ? (w + 2 * g) / w : 1;
        const sy = h > 0 ? (h + 2 * g) / h : 1;
        copy.texture = main.texture;
        copy.anchor.copyFrom(main.anchor);
        copy.scale.set(main.scale.x * sx, main.scale.y * sy);
        // `main.x`/`main.y` are 0 unless a swap key carries its own offset
        // (an#211), and a copy follows its part wherever the key put it.
        copy.x = main.x + off[0] + (0.5 - main.anchor.x) * w * (1 - sx);
        copy.y = main.y + off[1] + (0.5 - main.anchor.y) * h * (1 - sy);
    }

    function makeUnderlays(visualSpec, main) {
        const out = [];
        const specs = visualSpec.underlays || [];
        if (!specs.length) return out;
        const kind = visualSpec.kind;
        if (kind !== 'rect' && kind !== 'ellipse' && kind !== 'svg_sprite') {
            throw new Error(
                'underlays on a visual of kind ' + JSON.stringify(kind) +
                ': only rect, ellipse and svg_sprite take them.'
            );
        }
        main._anUnderlays = [];
        for (const u of specs) {
            const color = parseColor(u.color || '#000000');
            const grow = u.grow || 0;
            for (const off of (u.offsets || [[0, 0]])) {
                let copy;
                if (kind === 'svg_sprite') {
                    copy = new PIXI.Sprite(main.texture);
                    copy._anGrow = grow;
                    copy._anOffset = off;
                    // A tint is a MULTIPLY: exactly `color` over white art,
                    // darker elsewhere, exactly black for black. Remembered as
                    // the copy's base so an entity tint composes with it
                    // instead of replacing it (applyTintDeep).
                    copy.tint = color;
                    copy._anBaseTint = color;
                    fitUnderlay(main, copy);
                    main._anUnderlays.push(copy);
                } else {
                    // A procedural shape is REDRAWN grown: a rect with round
                    // corners of radius `grow` is exactly the rect dilated by
                    // a disk; an ellipse gets both radii grown.
                    copy = new PIXI.Graphics();
                    const w = visualSpec.width || 50;
                    const h = visualSpec.height || 50;
                    copy.beginFill(color, 1.0);
                    if (kind === 'ellipse') {
                        copy.drawEllipse(0, 0, w / 2 + grow, h / 2 + grow);
                    } else {
                        const ax = visualSpec.anchor_x != null ? visualSpec.anchor_x : 0.5;
                        const ay = visualSpec.anchor_y != null ? visualSpec.anchor_y : 0.5;
                        if (grow > 0) {
                            copy.drawRoundedRect(
                                -w * ax - grow, -h * ay - grow, w + 2 * grow, h + 2 * grow, grow
                            );
                        } else {
                            copy.drawRect(-w * ax, -h * ay, w, h);
                        }
                    }
                    copy.endFill();
                    copy.x = off[0];
                    copy.y = off[1];
                }
                copy.alpha = u.alpha != null ? u.alpha : 1;
                out.push(copy);
            }
        }
        return out;
    }

    // Phase 11b: build a Sprite from a pre-loaded SVG texture. The texture
    // is registered under `visualSpec.asset_id` by the asset preloader.
    function refitToBox(sprite) {
        // No-op unless the sprite was built with fit='contain' (only those
        // carry _anFitBox), so the stretch path is untouched.
        const box = sprite._anFitBox;
        const tex = sprite.texture;
        if (!box || !tex || !tex.orig || !(tex.orig.width > 0) || !(tex.orig.height > 0)) {
            return;
        }
        const k = Math.min(box[0] / tex.orig.width, box[1] / tex.orig.height);
        sprite.scale.set(k, k);
    }

    function makeSvgSprite(visualSpec) {
        const tex = (PIXI.Assets && PIXI.Assets.get)
            ? PIXI.Assets.get(visualSpec.asset_id)
            : null;
        const sprite = tex ? new PIXI.Sprite(tex) : new PIXI.Sprite(PIXI.Texture.WHITE);
        // Fit policy (an#74). 'contain' scales BOTH axes by one factor, so the
        // art keeps the shape it was drawn with; the box may be left with slack
        // on one axis and that slack is the correct rendering. The default
        // stays 'stretch' so a stored scene without the field is unchanged.
        //
        // Sizing by sprite.width/height is what made this a stretch: PixiJS
        // turns each into an INDEPENDENT axis scale, so the box's aspect ratio
        // always won and the art's was never consulted. Measured on this repo's
        // own rig, that distorted arm_l by 3.929x.
        const boxW = visualSpec.width || 64;
        const boxH = visualSpec.height || 64;
        if (visualSpec.fit === 'contain' && tex && tex.orig
                && tex.orig.width > 0 && tex.orig.height > 0) {
            const k = Math.min(boxW / tex.orig.width, boxH / tex.orig.height);
            sprite.scale.set(k, k);
            // Remembered so a texture swap re-fits rather than inheriting the
            // previous texture's scale — the box is the invariant, not the scale.
            sprite._anFitBox = [boxW, boxH];
        } else {
            sprite.width = boxW;
            sprite.height = boxH;
        }
        const ax = visualSpec.anchor_x != null ? visualSpec.anchor_x : 0.5;
        const ay = visualSpec.anchor_y != null ? visualSpec.anchor_y : 0.5;
        sprite.anchor.set(ax, ay);
        // Stash the node's swap-set projection ({set: {KEY: asset_id}}) on
        // the sprite so a swap channel can find its textures without
        // re-walking the scene graph. `viseme` is just one such set (an#87).
        if (visualSpec.asset_sets) {
            sprite._anAssetSets = visualSpec.asset_sets;
        }
        // an#211: a swap key drawn on a different canvas (or anchor, or
        // offset) carries its own geometry, applied with its texture — and the
        // geometry the sprite was BUILT with is kept so any other key, and the
        // restore-to-rest path, put it back. Absent on every rig whose keys
        // share one canvas, which leaves this sprite exactly as before.
        if (visualSpec.asset_geometry) {
            sprite._anAssetGeometry = visualSpec.asset_geometry;
            sprite._anBuiltGeometry = {
                width: boxW, height: boxH, anchor_x: ax, anchor_y: ay, x: 0, y: 0,
                fit: visualSpec.fit,
            };
        }
        sprite._anAssetId = visualSpec.asset_id;
        return sprite;
    }

    function applyKeyGeometry(sprite, assetId) {
        // Re-box, re-anchor and re-place a sprite for the texture it now shows
        // (an#211). Returns false when the sprite carries no per-key geometry,
        // so the caller keeps its plain re-fit.
        const table = sprite._anAssetGeometry;
        if (!table) return false;
        const built = sprite._anBuiltGeometry;
        const g = table[assetId] || built;
        sprite.anchor.set(g.anchor_x, g.anchor_y);
        sprite.x = g.x || 0;
        sprite.y = g.y || 0;
        const tex = sprite.texture;
        if (built.fit === 'contain' && tex && tex.orig
                && tex.orig.width > 0 && tex.orig.height > 0) {
            sprite._anFitBox = [g.width, g.height];
            refitToBox(sprite);
        } else {
            sprite.width = g.width;
            sprite.height = g.height;
        }
        return true;
    }

    function makeRect(visualSpec) {
        const g = new PIXI.Graphics();
        const color = parseColor(visualSpec.color || '#888888');
        g.beginFill(color, 1.0);
        const w = visualSpec.width || 50;
        const h = visualSpec.height || 50;
        const ax = visualSpec.anchor_x != null ? visualSpec.anchor_x : 0.5;
        const ay = visualSpec.anchor_y != null ? visualSpec.anchor_y : 0.5;
        g.drawRect(-w * ax, -h * ay, w, h);
        g.endFill();
        return g;
    }

    function makeEllipse(visualSpec) {
        const g = new PIXI.Graphics();
        const color = parseColor(visualSpec.color || '#888888');
        const rx = (visualSpec.width || 50) / 2;
        const ry = (visualSpec.height || 50) / 2;
        g.beginFill(color, 1.0);
        g.drawEllipse(0, 0, rx, ry);
        g.endFill();
        return g;
    }

    function makeEye(visualSpec) {
        // White eye-ball + dark pupil, both ellipses. The compiler stamps
        // visualSpec with width/height for the eye-ball; pupil sizes derive.
        const g = new PIXI.Graphics();
        const w = visualSpec.width || 10;
        const h = visualSpec.height || 8;
        // Eye white
        g.beginFill(0xffffff, 1.0);
        g.lineStyle(0.6, 0x222222, 0.6);
        g.drawEllipse(0, 0, w / 2, h / 2);
        g.endFill();
        // Pupil
        g.lineStyle(0);
        g.beginFill(parseColor(visualSpec.color || '#1a1a1a'), 1.0);
        g.drawEllipse(0, 0, w / 4, h / 3);
        g.endFill();
        return g;
    }

    // ------------------------------------------------------------------------
    // Stroked paths (an#160). The geometry functions below are MIRRORED by
    // an/adapters/cutout/path.py — that module is the spec, and
    // tests/test_path.py runs these exact functions under node against it.
    // Same operation order on both sides and no trigonometry (a direction is
    // a unit vector), so the parity is exact rather than within a tolerance.
    // ------------------------------------------------------------------------

    function pathLengths(pts) {
        const cum = [0];
        for (let i = 1; i < pts.length; i++) {
            const dx = pts[i][0] - pts[i - 1][0];
            const dy = pts[i][1] - pts[i - 1][1];
            cum.push(cum[i - 1] + Math.sqrt(dx * dx + dy * dy));
        }
        return cum;
    }

    // The first non-degenerate segment whose END reaches s, so a tip exactly
    // on a vertex belongs to the leg arriving there.
    function pathSegmentAt(cum, s) {
        let last = 0;
        for (let i = 0; i < cum.length - 1; i++) {
            if (cum[i + 1] > cum[i]) {
                last = i;
                if (s <= cum[i + 1]) return i;
            }
        }
        return last;
    }

    function pathPointAt(pts, cum, s) {
        const i = pathSegmentAt(cum, s);
        const span = cum[i + 1] - cum[i];
        if (!(span > 0)) return [pts[i][0], pts[i][1]];
        const u = (s - cum[i]) / span;
        const ax = pts[i][0], ay = pts[i][1];
        const bx = pts[i + 1][0], by = pts[i + 1][1];
        return [ax + (bx - ax) * u, ay + (by - ay) * u];
    }

    function pathTrim(pts, cum, a, b) {
        const out = [pathPointAt(pts, cum, a)];
        for (let i = 1; i < pts.length - 1; i++) {
            if (a < cum[i] && cum[i] < b) out.push([pts[i][0], pts[i][1]]);
        }
        out.push(pathPointAt(pts, cum, b));
        return out;
    }

    const PATH_HEAD_STROKE_INSET = 0.5;

    // Dash k covers [offset + k*period, offset + k*period + dash], laid along
    // the WHOLE path and clipped to [a, b] afterwards — so the trim moving
    // never moves a dash (an#161). Mirror of path.py::dash_spans.
    function pathDashSpans(a, b, dash, gap, offset) {
        const period = dash + gap;
        let k = Math.floor((a - offset - dash) / period);
        const out = [];
        for (;;) {
            const start = offset + k * period;
            if (!(start < b)) break;
            const lo = a > start ? a : start;
            const end = start + dash;
            const hi = b < end ? b : end;
            if (hi > lo) out.push([lo, hi]);
            k += 1;
        }
        return out;
    }

    function clamp01(v) {
        return v < 0 ? 0 : (v > 1 ? 1 : v);
    }

    function pathGeometry(pts, trimStart, trimEnd, headLength, headWidth,
                          dash, gap, dashOffset) {
        const cum = pathLengths(pts);
        const total = cum[cum.length - 1];
        const lo = clamp01(Math.min(trimStart, trimEnd));
        const hi = clamp01(Math.max(trimStart, trimEnd));
        const a = lo * total;
        const b = hi * total;
        if (!(b > a)) return { stroke: [], head: null };
        let head = null;
        let strokeEnd = b;
        if (headLength > 0) {
            const visible = b - a;
            const k = visible < headLength ? visible / headLength : 1.0;
            const hl = headLength * k;
            const hw = headWidth * k;
            const i = pathSegmentAt(cum, b);
            const dx = pts[i + 1][0] - pts[i][0];
            const dy = pts[i + 1][1] - pts[i][1];
            const seg = Math.sqrt(dx * dx + dy * dy);
            const ux = dx / seg;
            const uy = dy / seg;
            const tip = pathPointAt(pts, cum, b);
            const tx = tip[0], ty = tip[1];
            const bx = tx - ux * hl;
            const by = ty - uy * hl;
            const nx = -uy * (hw / 2);
            const ny = ux * (hw / 2);
            head = [[tx, ty], [bx + nx, by + ny], [bx - nx, by - ny]];
            strokeEnd = b - hl * PATH_HEAD_STROKE_INSET;
        }
        if (dash > 0) {
            const spans = strokeEnd > a
                ? pathDashSpans(a, strokeEnd, dash, gap, dashOffset || 0) : [];
            const dashes = spans.map(sp => pathTrim(pts, cum, sp[0], sp[1]));
            return { stroke: [], head: head, dashes: dashes };
        }
        const stroke = strokeEnd > a ? pathTrim(pts, cum, a, strokeEnd) : [];
        return { stroke: stroke, head: head };
    }

    function drawPath(g) {
        const st = g._anPath;
        const spec = st.spec;
        const geo = pathGeometry(
            spec.points, st.trim_start, st.trim_end,
            spec.head_length || 0, spec.head_width || 0,
            spec.dash || 0, spec.gap || 0, st.dash_offset
        );
        const color = parseColor(spec.color);
        g.clear();
        const strokes = geo.dashes || [geo.stroke];
        for (const line of strokes) {
            if (line.length < 2) continue;
            g.lineStyle({
                width: spec.stroke_width,
                color: color,
                alpha: 1.0,
                cap: spec.cap || 'round',
                join: spec.join || 'round',
            });
            g.moveTo(line[0][0], line[0][1]);
            for (let i = 1; i < line.length; i++) {
                g.lineTo(line[i][0], line[i][1]);
            }
        }
        if (geo.head) {
            g.lineStyle(0);
            g.beginFill(color, 1.0);
            g.drawPolygon([
                geo.head[0][0], geo.head[0][1],
                geo.head[1][0], geo.head[1][1],
                geo.head[2][0], geo.head[2][1],
            ]);
            g.endFill();
        }
    }

    function makePath(visualSpec) {
        const spec = visualSpec.path;
        if (!spec || !Array.isArray(spec.points) || spec.points.length < 2) {
            throw new Error('a path visual needs `path.points` with at least two points');
        }
        const g = new PIXI.Graphics();
        g._anPath = {
            spec: spec,
            trim_start: spec.trim_start != null ? spec.trim_start : 0,
            trim_end: spec.trim_end != null ? spec.trim_end : 1,
            dash_offset: spec.dash_offset != null ? spec.dash_offset : 0,
        };
        drawPath(g);
        return g;
    }

    function applyTrim(node, prop, value) {
        const child = (node.children || []).find(c => c._anPath);
        if (!child) {
            throw new Error(
                'property ' + JSON.stringify(prop) + ' on ' + JSON.stringify(node.name) +
                ': only a stroked path has a trim, and this node draws none.'
            );
        }
        if (prop === 'dash_offset' && !(child._anPath.spec.dash > 0)) {
            throw new Error(
                'property "dash_offset" on ' + JSON.stringify(node.name) +
                ': this path has no dash pattern, so an offset would draw nothing.'
            );
        }
        if (child._anPath[prop] === value) return;
        child._anPath[prop] = value;
        drawPath(child);
    }

    function parseColor(s) {
        if (typeof s !== 'string') return 0x888888;
        const hex = s.startsWith('#') ? s.slice(1) : s;
        return parseInt(hex.padEnd(6, '0').slice(0, 6), 16);
    }

    function applyTransform(displayObject, t) {
        if (!t) return;
        displayObject.x = t.x || 0;
        displayObject.y = t.y || 0;
        displayObject.rotation = t.rotation || 0;
        displayObject.scale.x = t.scale_x != null ? t.scale_x : 1;
        displayObject.scale.y = t.scale_y != null ? t.scale_y : 1;
        displayObject.skew.x = t.skew_x || 0;
        displayObject.skew.y = t.skew_y || 0;
        displayObject.pivot.x = t.pivot_x || 0;
        displayObject.pivot.y = t.pivot_y || 0;
        // Containers DO have alpha, and it cascades to children — which is the
        // semantics wanted: fading a character fades its parts. (Per-part
        // compositing, so overlapping parts show a seam mid-fade; a flattened
        // group fade would need a render-to-texture pass per node per frame.)
        displayObject.alpha = t.alpha != null ? t.alpha : 1;
    }

    // ------------------------------------------------------------------------
    // Pose application
    // ------------------------------------------------------------------------

    // Shallowest target first, then lexicographic. Object key order is
    // insertion order, i.e. a function of channel emission order, which is not
    // a contract — and the golden-frame work downstream needs a frame's pose
    // application to be deterministic. Depth-first ordering also makes the more
    // specific target win for any property that ever cascades.
    function poseKeysInApplicationOrder(pose) {
        return Object.keys(pose).sort(function (a, b) {
            const da = (a.split('::')[0].match(/\//g) || []).length;
            const db = (b.split('::')[0].match(/\//g) || []).length;
            return da !== db ? da - db : (a < b ? -1 : a > b ? 1 : 0);
        });
    }

    function applyPose(pose) {
        for (const key of poseKeysInApplicationOrder(pose)) {
            const [target, prop] = key.split('::');
            const node = nodeIndex[target];
            if (!node) {
                // The sibling silence of the one above: a mistyped target path
                // used to animate nothing, quietly. Listing the known paths is
                // what makes the typo obvious — they are usually one character
                // apart.
                throw new Error(
                    'animation targets unknown node ' + JSON.stringify(target) +
                    '. Known: ' + JSON.stringify(Object.keys(nodeIndex).sort())
                );
            }
            applyProperty(node, prop, pose[key]);
        }
    }

    // Mouth-shape table for viseme rendering. Each entry describes a mouth
    // drawn with two bezier arcs (top & bottom lip). w/h define the bounding
    // box, lipColor outlines, fillColor fills the mouth interior.
    // Mirrors the lookup in an/adapters/cutout/compile.py docstrings.
    const VISEME_SHAPES = {
        // closed: thin line, slight smile
        X: { w: 22, h: 3,  open: 0.0, smile: 0.05 },
        A: { w: 22, h: 4,  open: 0.05, smile: 0.10 },
        // mid open
        B: { w: 22, h: 9,  open: 0.4, smile: 0.0 },
        C: { w: 24, h: 14, open: 0.7, smile: 0.0 },
        D: { w: 26, h: 20, open: 1.0, smile: 0.0 },  // wide open
        // rounded
        E: { w: 20, h: 17, open: 0.85, smile: -0.05 },
        F: { w: 14, h: 14, open: 0.9, smile: -0.10 },  // tight rounded "ooh"
        G: { w: 22, h: 7,  open: 0.2, smile: 0.0, teeth: true },
        H: { w: 18, h: 6,  open: 0.15, smile: 0.0, tongue: true },
    };
    const MOUTH_REST = 'X';
    const _LIP_COLOR  = 0x6b2b2b;
    const _MOUTH_FILL = 0x2a1010;
    const _TEETH_COLOR = 0xfafafa;
    const _TONGUE_COLOR = 0xb04848;

    function drawMouthShape(g, visemeCode) {
        // Loud on an unknown code, like every other bad swap key (an#87).
        // The old `|| VISEME_SHAPES.X` fallback silently drew the closed
        // mouth for typos AND for lowercase codes (the sprite path used to
        // upper-case, this one never did) — the compiler now normalises case
        // at emission and validates codes, so anything unknown arriving here
        // is a hand-written scene's mistake and deserves a diagnosis.
        const s = VISEME_SHAPES[visemeCode];
        if (!s) {
            throw new Error(
                'unknown mouth shape ' + JSON.stringify(visemeCode) +
                '. Known: ' + JSON.stringify(Object.keys(VISEME_SHAPES).sort())
            );
        }
        const w = s.w, h = s.h;
        const halfW = w / 2;
        const halfH = h / 2;
        const smile = (s.smile || 0) * h * 1.5; // pixels of upturn at corners
        g.clear();

        // Build the mouth as a quad-arc lens shape:
        //   top lip:    (-halfW, +smile) → quad → (+halfW, +smile)  with control above
        //   bottom lip: (+halfW, +smile) → quad → (-halfW, +smile)  with control below
        // Mouth-fill inside, outlined in lip color.
        g.lineStyle(1.0, _LIP_COLOR, 1.0);
        g.beginFill(_MOUTH_FILL, 1.0);
        g.moveTo(-halfW, smile);
        // top arc — control point pulled UP by some fraction of openness
        g.quadraticCurveTo(0, -halfH * 0.6 - smile * 0.2, +halfW, smile);
        // bottom arc — control point pushed DOWN by openness amount
        g.quadraticCurveTo(0, +halfH * (0.5 + 0.5 * s.open), -halfW, smile);
        g.endFill();

        if (s.teeth) {
            g.lineStyle(0);
            g.beginFill(_TEETH_COLOR, 1.0);
            g.drawRect(-halfW * 0.7, -1.5, w * 0.7, 2.5);
            g.endFill();
        }
        if (s.tongue) {
            g.lineStyle(0);
            g.beginFill(_TONGUE_COLOR, 1.0);
            g.drawEllipse(0, halfH * 0.2, w * 0.18, h * 0.18);
            g.endFill();
        }
    }

    // The ONE swap implementation (an#87). A property outside applyProperty's
    // static switch names a swap SET; the node's visual child declares which
    // sets it can apply — `_anAssetSets` ({set: {KEY: asset_id}}, texture
    // swap) or `_anDrawSets` ({set: redrawFn}, procedural redraw). `viseme`
    // is just a conventional set name carried by mouths.
    //
    // The value domain is as loud as the target and property domains: an
    // unknown key THROWS naming node, set, and the known keys — the old
    // viseme path silently kept the previous texture, which is the defect
    // class an#87 closes. Compiled scenes never reach the throw (the
    // compiler validates and drops with a warning); a hand-written scene
    // gets a diagnosis instead of a frozen mouth.
    function unknownSwapKey(node, prop, key, known) {
        return new Error(
            'unknown key ' + JSON.stringify(key) + ' for swap set ' +
            JSON.stringify(prop) + ' on ' + JSON.stringify(node.name) +
            '. Known keys: ' + JSON.stringify(known)
        );
    }

    function applySwap(child, node, prop, value) {
        const key = String(value);
        if (child._anDrawSets && child._anDrawSets[prop]) {
            // A drawn set declares {keys, apply}: the same loud unknown-key
            // error as a texture set, naming node, set and known keys, before
            // the redraw function's own backstop can fire.
            const drawn = child._anDrawSets[prop];
            if (drawn.keys.indexOf(key) < 0) {
                throw unknownSwapKey(node, prop, key, drawn.keys);
            }
            drawn.apply(child, key);
            return;
        }
        const map = child._anAssetSets[prop];
        const assetId = map[key];
        if (assetId === undefined) {
            throw unknownSwapKey(node, prop, key, Object.keys(map).sort());
        }
        const tex = PIXI.Assets.get(assetId);
        if (!tex) {
            throw new Error(
                'swap set ' + JSON.stringify(prop) + ' on ' +
                JSON.stringify(node.name) + ' resolves key ' +
                JSON.stringify(key) + ' to texture ' + JSON.stringify(assetId) +
                ', which is not loaded.'
            );
        }
        child.texture = tex;
        // Re-fit: under 'contain' the scale belongs to the texture, not to
        // the sprite, so a swap must recompute it. Without this every key
        // after the first inherits the previous texture's scale — silently,
        // and only visible as art that is subtly the wrong size on some
        // frames. A key with its own box/anchor/offset takes those too.
        if (!(child._anAssetGeometry && applyKeyGeometry(child, assetId))) {
            refitToBox(child);
        }
        // an#163: the part's outline/shadow copies swap WITH it — a mouth's
        // outline that kept the rest shape would be the wrong mouth drawn
        // behind the right one.
        for (const copy of (child._anUnderlays || [])) {
            fitUnderlay(child, copy);
        }
    }

    function applyTintDeep(node, packed) {
        // `tint` DOES NOT CASCADE the way `alpha` does, and that difference is
        // the whole reason this function exists. A PixiJS `Container` has an
        // `alpha` the renderer multiplies down the tree, but no `tint` — only
        // the leaves that actually draw (`Graphics`, `Sprite`, `Mesh`, `Text`)
        // have one. An entity channel targets the entity ROOT, which is a
        // Container, so setting `node.tint` there is a silent no-op: measured,
        // a tween to `#ff0000` moved the drawn pixels by 0.0002 (an#62).
        //
        // Authors reasonably expect it to behave like `alpha` — the docs call
        // that "the fade primitive that cascades to a character's parts" — so
        // the cascade is done here instead of being left as a footgun.
        // An underlay copy's own tint IS its colour (an#163), so an entity
        // tint multiplies into it rather than replacing it.
        node.tint = node._anBaseTint != null ? mulTint(node._anBaseTint, packed) : packed;
        for (const child of (node.children || [])) {
            applyTintDeep(child, packed);
        }
    }

    function applyProperty(node, prop, value) {
        switch (prop) {
            case 'x': node.x = value; break;
            case 'y': node.y = value; break;
            case 'rotation':
            case 'rotation_rad': node.rotation = value; break;
            case 'scale_x': node.scale.x = value; break;
            case 'scale_y': node.scale.y = value; break;
            case 'skew_x': node.skew.x = value; break;
            case 'skew_y': node.skew.y = value; break;
            case 'pivot_x': node.pivot.x = value; break;
            case 'pivot_y': node.pivot.y = value; break;
            case 'alpha': node.alpha = value; break;
            // an#160: a stroked path's visible span. Applied to the node's
            // path visual and redrawn; loud on a node without one.
            case 'trim_start':
            case 'trim_end':
            case 'dash_offset': applyTrim(node, prop, value); break;
            // an#62. Three numeric channels, not one colour: `evaluate` lerps
            // numbers and SNAPS everything else, and it has a Python twin kept
            // in step by a parity test — so a colour type here would be a third
            // interpolation mode in two implementations that have drifted
            // before. The compiler expands one authored `tint: "#rrggbb"` into
            // these, so per-channel sRGB interpolation is the ordinary numeric
            // path and neither evaluator learns what a colour is.
            case 'tint_r':
            case 'tint_g':
            case 'tint_b': {
                // Rest is WHITE. `tint` is a multiply, so a missing component
                // must be 1.0 — defaulting to 0 renders the node black the
                // instant any one of the three is animated.
                const parts = node._anTint ||
                    (node._anTint = { tint_r: 1, tint_g: 1, tint_b: 1 });
                parts[prop] = value;
                const q = v => Math.max(0, Math.min(255, Math.round(v * 255)));
                applyTintDeep(
                    node,
                    (q(parts.tint_r) << 16) | (q(parts.tint_g) << 8) | q(parts.tint_b)
                );
                break;
            }
            default: {
                // Not a transform: the property names a swap set (an#87).
                // Apply it if this node's visual declares the set; otherwise
                // throw. Loud, not silent — "forward compat" was the stated
                // reason for ignoring unknown properties once, but silence
                // meant a channel rendered as nothing with no diagnostic.
                const child = (node.children || []).find(
                    c => c._anAssetSets || c._anDrawSets
                );
                const sets = child
                    ? Object.assign({}, child._anDrawSets, child._anAssetSets)
                    : {};
                if (sets[prop]) {
                    applySwap(child, node, prop, value);
                    break;
                }
                throw new Error(
                    'unknown animated property ' + JSON.stringify(prop) +
                    ' on ' + JSON.stringify(node.name) + '. The runtime applies: ' +
                    'x, y, rotation, rotation_rad, scale_x, scale_y, skew_x, ' +
                    'skew_y, pivot_x, pivot_y, alpha, tint_r, tint_g, tint_b, ' +
                    'trim_start, trim_end, dash_offset (paths only) ' +
                    '(author `tint` as a #rrggbb string; the compiler expands ' +
                    'it into the three) — plus this node\'s swap ' +
                    'sets: ' + JSON.stringify(Object.keys(sets).sort()) + '.'
                );
            }
        }
    }

    // ------------------------------------------------------------------------
    // Timeline evaluation
    // ------------------------------------------------------------------------

    // Port of `an/adapters/cutout/clip.py::_wrap_time` — that function is the spec,
    // and this must stay bit-identical to it. Three modes:
    //   once      clamp; past `duration` the last frame holds
    //   loop      t % duration  (at exactly t == duration this is 0, so the FIRST
    //             keyframe renders at the period boundary, not the last)
    //   ping_pong bounce over period 2*duration; t == duration is the apex, inclusive
    function wrapTime(t, duration, mode) {
        if (t < 0) return 0;
        if (mode === 'loop') return duration > 0 ? t % duration : 0;
        if (mode === 'ping_pong') {
            if (duration <= 0) return 0;
            const period = 2 * duration;
            const phase = t % period;
            return phase <= duration ? phase : period - phase;
        }
        return Math.min(t, duration);  // 'once', and the default for anything unknown
    }

    // The properties `applyProperty` handles itself; anything else names a
    // swap set on the node's visual. Mirror of `an.base.TRANSFORM_PROPERTIES`
    // (tests/test_pure_pose.py pins the two, and this list against the switch).
    const RUNTIME_PROPERTIES = new Set([
        'x', 'y', 'rotation', 'rotation_rad', 'scale_x', 'scale_y', 'skew_x',
        'skew_y', 'pivot_x', 'pivot_y', 'alpha', 'tint_r', 'tint_g', 'tint_b',
        'trim_start', 'trim_end', 'dash_offset',
    ]);
    const SWAP_WRITE_GROUP = '<swap>';
    const SHARED_WRITES = { rotation_rad: 'rotation' };

    // Port of `timeline.py::write_group`: what a property WRITES on its node.
    // Every swap set on a node swaps its one visual; `rotation_rad` is
    // `rotation`; everything else writes only itself.
    function writeGroup(prop) {
        if (RUNTIME_PROPERTIES.has(prop)) return SHARED_WRITES[prop] || prop;
        return SWAP_WRITE_GROUP;
    }

    // Port of `an/adapters/cutout/timeline.py::evaluate_timeline` — that
    // function is the spec, and tests/test_pure_pose.py runs this one against
    // it. The pose is a PURE function of t (an#185): a key a playing clip
    // writes takes its value (later wins); a key whose clips have all ENDED
    // holds the value the latest-ending one reached at its end (a tie goes to
    // the later clip); a key nothing has started writing is ABSENT, and
    // `anSetTime` restores it to what `anLoadScene` built. Of the keys that
    // write the same thing on one node (`writeGroup`), only the most recently
    // written survives. Before an#185 an ended clip simply stopped writing,
    // so the node kept whatever the previous SEEK applied — identical when
    // seeks run forward, and a different picture after any seek backwards.
    function evaluateTimeline(t) {
        const written = {};  // key → { when, value }
        const held = {};     // key → { when, value }
        for (const track of scene.timeline.tracks || []) {
            for (const placed of track.clips || []) {
                const anim = scene.animations[placed.animation_id];
                if (!anim) continue;
                // The window a placement occupies may be WIDENED by `placed.duration`,
                // but the clip still loops against its OWN natural duration — that
                // asymmetry is exactly what makes looping observable, and Python does
                // the same (`_evaluate_clip` wraps against `clip.duration`, never the
                // placement override). Getting it backwards silently breaks every loop.
                const clipDur = anim.duration || 0;
                const windowDur = placed.duration != null ? placed.duration : clipDur;
                const speed = placed.speed != null ? placed.speed : 1;
                const effDur = windowDur / speed;
                const end = placed.start_time + effDur;
                if (placed.start_time <= t && t <= end) {
                    const localT = wrapTime(
                        (t - placed.start_time) * speed, clipDur, anim.loop_mode
                    );
                    for (const ch of anim.channels) {
                        const v = evaluateChannel(ch, localT);
                        if (v != null) {
                            written[ch.target + '::' + ch.property] = { when: t, value: v };
                        }
                    }
                } else if (t > end) {
                    const localEnd = wrapTime(
                        (end - placed.start_time) * speed, clipDur, anim.loop_mode
                    );
                    for (const ch of anim.channels) {
                        const v = evaluateChannel(ch, localEnd);
                        if (v == null) continue;
                        const key = ch.target + '::' + ch.property;
                        if (!(key in held) || end >= held[key].when) {
                            held[key] = { when: end, value: v };
                        }
                    }
                }
            }
        }
        // Sorted: the pose's keys are re-sorted before they are applied, so
        // this order cannot reach a pixel — sorted anyway, per the runtime's
        // Object.keys rule (tests/test_determinism_perimeter.py).
        for (const key of Object.keys(held).sort()) {
            if (!(key in written)) written[key] = held[key];
        }
        const groupOf = key => {
            const [target, prop] = key.split('::');
            return target + '::' + writeGroup(prop);
        };
        const latest = {};
        const keys = Object.keys(written).sort();
        for (const key of keys) {
            const g = groupOf(key);
            if (!(g in latest) || written[key].when > latest[g]) latest[g] = written[key].when;
        }
        const pose = {};
        for (const key of keys) {
            if (written[key].when >= latest[groupOf(key)]) pose[key] = written[key].value;
        }
        return pose;
    }

    // What `anSetTime` puts back for a key the pose leaves ABSENT (nothing
    // writing it has started): a function restoring the node to what
    // `anLoadScene` built, captured right after the build and before any
    // seek. `null` when there is nothing to capture — an unknown target or
    // property — so the loud error stays where it was: `applyPose`, the
    // first time a clip actually writes the key.
    function captureRest(node, prop) {
        switch (prop) {
            case 'x': { const v = node.x; return () => { node.x = v; }; }
            case 'y': { const v = node.y; return () => { node.y = v; }; }
            case 'rotation':
            case 'rotation_rad': { const v = node.rotation; return () => { node.rotation = v; }; }
            case 'scale_x': { const v = node.scale.x; return () => { node.scale.x = v; }; }
            case 'scale_y': { const v = node.scale.y; return () => { node.scale.y = v; }; }
            case 'skew_x': { const v = node.skew.x; return () => { node.skew.x = v; }; }
            case 'skew_y': { const v = node.skew.y; return () => { node.skew.y = v; }; }
            case 'pivot_x': { const v = node.pivot.x; return () => { node.pivot.x = v; }; }
            case 'pivot_y': { const v = node.pivot.y; return () => { node.pivot.y = v; }; }
            case 'alpha': { const v = node.alpha; return () => { node.alpha = v; }; }
            case 'trim_start':
            case 'trim_end':
            case 'dash_offset': {
                const child = (node.children || []).find(c => c._anPath);
                if (!child) return null;
                const v = child._anPath[prop];
                return () => {
                    if (child._anPath[prop] === v) return;
                    child._anPath[prop] = v;
                    drawPath(child);
                };
            }
            // Rest is white (see applyProperty): restoring one component
            // re-applies the cascade with it at 1.
            case 'tint_r':
            case 'tint_g':
            case 'tint_b':
                return () => applyProperty(node, prop, 1);
            default: {
                const child = (node.children || []).find(
                    c => c._anAssetSets || c._anDrawSets
                );
                if (!child) return null;
                const drawn = child._anDrawSets && child._anDrawSets[prop];
                if (drawn) {
                    return () => drawn.apply(child, drawn.rest);
                }
                if (!(child._anAssetSets && child._anAssetSets[prop])) return null;
                // The texture it was BUILT with, which need not be any key of
                // the set. Re-fit and re-fit the underlays exactly as a swap
                // does, so the restored box is the built one.
                const tex = child.texture;
                return () => {
                    if (child.texture === tex) return;
                    child.texture = tex;
                    if (!(child._anAssetGeometry
                            && applyKeyGeometry(child, child._anAssetId))) {
                        refitToBox(child);
                    }
                    for (const copy of (child._anUnderlays || [])) {
                        fitUnderlay(child, copy);
                    }
                };
            }
        }
    }

    function indexRestPoses() {
        restIndex = {};
        for (const anim of Object.values(scene.animations || {})) {
            for (const ch of anim.channels || []) {
                const key = ch.target + '::' + ch.property;
                if (key in restIndex) continue;
                const node = nodeIndex[ch.target];
                restIndex[key] = node ? captureRest(node, ch.property) : null;
            }
        }
        restOrder = poseKeysInApplicationOrder(restIndex);
    }

    // ------------------------------------------------------------------------
    // Public API
    // ------------------------------------------------------------------------

    // Phase 11b: preload SVG textures declared in scene.assets.textures.
    // Returns a Promise that resolves once all assets are GPU-ready.
    async function preloadAssets(sceneJson) {
        if (!PIXI.Assets) return;
        const textures = (sceneJson.assets && sceneJson.assets.textures) || {};
        // .sort() is a determinism CONTRACT, not tidiness. Object key order here
        // is JSON-document order, i.e. a function of the compiler's emission
        // order, which is not a contract — and this array is the argument to
        // PIXI.Assets.load, whose scheduling it decides. Never observed to move
        // a pixel; an unwritten invariant is one refactor from being false.
        const aliases = Object.keys(textures).sort();
        if (!aliases.length) return;
        for (const alias of aliases) {
            const src = textures[alias].src || textures[alias];
            try {
                PIXI.Assets.add(alias, src);
            } catch (e) {
                // already-registered alias — ignore on hot reload.
            }
        }
        await PIXI.Assets.load(aliases);
    }

    NS.anLoadScene = async function (sceneJson) {
        if (!window.PIXI) {
            throw new Error('PixiJS not loaded');
        }
        await preloadAssets(sceneJson);
        scene = sceneJson;
        nodeIndex = {};
        visualIndex = {};

        const meta = scene.meta || {};
        const width = meta.width || 1920;
        const height = meta.height || 1080;
        const bg = parseColor(meta.background || '#ffffff');

        // Reloading a scene (which `an preview` does on every file change) needs a
        // FRESH canvas element, and this is fiddlier than it looks — an#6:
        //
        //  - `destroy(true, …)` removes <canvas id="stage"> from the document. The
        //    lookup below then returned null and PixiJS, given `view: null`, quietly
        //    made its own detached canvas. Nothing threw; the preview just went
        //    blank on the first edit and never came back.
        //  - Simply keeping the old element (`destroy(false, …)`) does not work
        //    either: its WebGL context is gone with the renderer and cannot be
        //    re-acquired, so the next `new PIXI.Application({view: sameCanvas})`
        //    dies with "Invalid value of `0` passed to checkMaxIfStatementsInShader".
        //
        // So: destroy, then put a brand-new canvas where the old one was, keeping
        // its id and position so the page's CSS and any external lookups still work.
        let canvas = document.getElementById('stage');
        if (!canvas) {
            // Fail loudly. The original bug was invisible precisely because PixiJS
            // treats a missing view as "make me one".
            throw new Error(
                'anLoadScene: no <canvas id="stage"> in the document — the runtime ' +
                'renders into it and will not silently create a detached one.'
            );
        }
        if (app) {
            const parent = canvas.parentNode;
            const next = canvas.nextSibling;
            app.destroy(true, { children: true, texture: true, baseTexture: true });
            app = null;
            const fresh = document.createElement('canvas');
            fresh.id = 'stage';
            fresh.className = canvas.className;
            parent.insertBefore(fresh, next);
            canvas = fresh;
        }
        // Supersample factor, injected by the render path before anLoadScene.
        // The `autoDensity` key below is LOAD-BEARING and is the whole
        // plumbing finding. Set it true and Pixi sets the canvas CSS size to
        // the LOGICAL size, so Chromium composites the k-times backbuffer down
        // before the screenshot -- a blind downscale with no filter choice and
        // no record that it happened. The literal is spelled ONCE in this file
        // on purpose: `an/bench/mutations.py` pins it, exactly as it pins the
        // multisampling flag below, so a reformat fails loudly at the lever
        // rather than producing a "mutation" that changes nothing.
        // Both keys are new; the engine default is RESOLUTION: 1, applied
        // silently, so neither could be relied on before.
        const resolution = Math.max(1, (NS.anSupersample | 0) || 1);
        app = new PIXI.Application({
            view: canvas,
            width: width,
            height: height,
            backgroundColor: bg,
            antialias: true,
            resolution: resolution,
            autoDensity: false,
            autoStart: false,
            preserveDrawingBuffer: true,
        });

        const root = new PIXI.Container();
        // Center the scene so transforms in [-w/2..w/2] are visible by default.
        root.x = width / 2;
        root.y = height / 2;
        app.stage.addChild(root);
        // Index the centered root under the path "root" so camera channels
        // (compiled by Python) can target it for scale animations etc.
        root.name = 'root';
        nodeIndex['root'] = root;

        if (scene.scene) {
            // The Python compiler's top-level node is a synthetic "root"
            // container that just holds the entities. Skip indexing it (so
            // path keys start at the entity name like 'charlie/head/mouth',
            // matching the channel.target strings the compiler emits). Do
            // NOT apply its transform — it's a logical container, and the
            // outer `root` already centers the scene to canvas center.
            for (const child of (scene.scene.children || [])) {
                buildSceneTree(child, root, '');
            }
        }

        // The overlay (an#155): a SECOND top-level container, centred like
        // `root` but deliberately NOT indexed — no channel can name it, so the
        // camera (which is `root.pivot` + `root.scale`) cannot reach it, and a
        // title card holds still through a push-in. Its children ARE indexed,
        // under their own paths ('title/word_0'), so they animate like
        // anything else. Added after `root`, so it draws over the scene.
        if (scene.overlay) {
            const overlay = new PIXI.Container();
            overlay.x = width / 2;
            overlay.y = height / 2;
            overlay.name = 'overlay';
            app.stage.addChild(overlay);
            for (const child of (scene.overlay.children || [])) {
                // One index for both layers: an overlay entity that shares a
                // path with the scene (or is called 'root', the camera's node)
                // would overwrite it. The compiler refuses both; this is the
                // loud backstop for a hand-written document.
                if (nodeIndex[child.name]) {
                    throw new Error(
                        'anLoadScene: overlay entity ' + JSON.stringify(child.name) +
                        ' collides with an indexed scene path'
                    );
                }
                buildSceneTree(child, overlay, '');
            }
        }

        indexRestPoses();
        app.render();
        pixiReady = true;
        return true;
    };

    NS.anSetTime = function (t) {
        if (!app || !scene) return false;
        const pose = evaluateTimeline(t);
        // Every animated key the pose leaves absent goes back to rest FIRST,
        // then the pose is applied over it — so a key that shares what it
        // writes with another (two swap sets on one sprite, `rotation` and
        // `rotation_rad`, a tint cascade) still ends on the value the pose
        // names. When seeks run forward this restores nothing that was not
        // already at rest, which is why no golden frame moved (an#185).
        for (const key of restOrder) {
            if (!(key in pose) && restIndex[key]) restIndex[key]();
        }
        applyPose(pose);
        app.render();
        return true;
    };

    // ------------------------------------------------------------------------
    // In-page frame capture — the `capture="canvas"` path
    // (an/adapters/cutout/canvas_capture.py is the Python half; read its
    // docstring before changing anything here).
    //
    // requests: [{frame: i, times: [t, ...]}, ...], in the order the frames
    // must be captured. Returns {frames: [{frame, width, height, pngs}]} with
    // the frame numbers ECHOED, so the Python side can prove nothing was
    // dropped or reordered, or {error, frame, t} for the first instant the
    // runtime could not evaluate — the same located failure the screenshot
    // path raises.
    //
    // Every instant is seeked through `NS.anSetTime`, in the order given,
    // exactly as the screenshot path seeks it. Since an#185 the pose is a pure
    // function of t, so the order is no longer load-bearing for the picture;
    // it is kept because the frame numbers are echoed in it.
    //
    // `app.view.toDataURL`, not `app.renderer.extract` (which re-renders into
    // a non-multisampled texture — a different picture) and not raw
    // `gl.readPixels` bytes (bottom-up rows, premultiplied, and ~20x slower to
    // move across the DevTools protocol than a PNG). It reads the drawing
    // buffer `anSetTime` just rendered, which `preserveDrawingBuffer: true`
    // keeps readable.
    // ------------------------------------------------------------------------
    NS.anCaptureFrames = function (requests) {
        if (!app || !scene) {
            throw new Error('anCaptureFrames: no scene is loaded');
        }
        const view = app.view;
        const frames = [];
        for (const req of requests) {
            const pngs = [];
            for (const t of req.times) {
                try {
                    NS.anSetTime(t);
                } catch (e) {
                    return {
                        error: (e && e.name ? e.name + ': ' : '') + (e && e.message ? e.message : String(e)),
                        frame: req.frame,
                        t: t,
                    };
                }
                pngs.push(view.toDataURL('image/png'));
            }
            frames.push({ frame: req.frame, width: view.width, height: view.height, pngs: pngs });
        }
        return { frames: frames };
    };

    // Blinks are COMPILED channels since an#88 — see compile.py's
    // `_add_face_clips` / `_blink_placements`. This file used to run a post-pose pass that matched
    // eye nodes by regex and forced scale.y every frame, which is why an
    // authored eye scale_y could never reach the screen. The phase-per-entity
    // fact that pass owned now lives in the compiled scene's meta.blink_phases.

    // ------------------------------------------------------------------------
    // Determinism probe (an#37).
    //
    // Reports; it does not judge. The Python side owns the verdict
    // (`an/determinism.py`) so the rule is testable without a browser, and so a
    // future rule change is a Python diff rather than a runtime re-stage.
    //
    // What it watches and why: the vendored PixiJS carries 4 `Math.random`, 2
    // `Date.now`, 6 `performance.now` and 3 `requestAnimationFrame` calls, and
    // `NoiseFilter`'s default seed is `Math.random()`. All dormant today,
    // because the app is created with `autoStart:false` and driven by explicit
    // `app.render()` calls, and because nothing attaches a filter. Both facts
    // are accidents of the current code with nothing asserting them — adding a
    // grain filter in a later wave would randomise every frame with nothing
    // going red. (an#163 shipped grain the other way: a seeded texture made at
    // compile time and drawn with a native blend mode, not a filter.)
    // ------------------------------------------------------------------------

    function _filteredNodePaths() {
        const out = [];
        for (const path of Object.keys(nodeIndex).sort()) {
            const n = nodeIndex[path];
            if (n && n.filters && n.filters.length) out.push(path);
        }
        return out;
    }

    NS.anDeterminismReport = function () {
        const stage = app ? app.stage : null;
        const shared = (window.PIXI && PIXI.Ticker) ? PIXI.Ticker.shared : null;
        return {
            page: (window.location && window.location.pathname) || null,
            runtime_version: RUNTIME_VERSION,
            pixi_version: (window.PIXI && PIXI.VERSION) || null,
            auto_start: !!(app && app.ticker && app.ticker.started),
            shared_ticker_started: !!(shared && shared.started),
            stage_filter_count: (stage && stage.filters) ? stage.filters.length : 0,
            filtered_node_paths: _filteredNodePaths(),
            node_count: Object.keys(nodeIndex).length,
        };
    };

    NS.anCanvasReady = function () {
        return pixiReady;
    };

    // Signal load completion via a known DOM marker (Playwright can wait on it)
    document.addEventListener('DOMContentLoaded', function () {
        const marker = document.createElement('meta');
        marker.name = 'an-runtime-loaded';
        marker.content = RUNTIME_VERSION;
        document.head.appendChild(marker);
    });
})();
