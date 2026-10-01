// A genre's runtime script, for tests/test_stage_engine.py (an#247): one
// visual kind, `demo_disc`, a solid red disc of the node's width.
window.anRegisterVisual('demo_disc', function (spec, PIXI) {
    const g = new PIXI.Graphics();
    g.beginFill(0xff0000, 1.0);
    g.drawCircle(0, 0, (spec.width || 20) / 2);
    g.endFill();
    return g;
});
