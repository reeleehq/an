// The JS facade the Python side calls (an#257 spike). Plain function declarations
// only, so `jy.add_js_funcs` can read their signatures and make Python stubs that
// return call strings. `previz_host.mjs` evaluates this file in its global scope,
// after putting `previz`, `previzDemo`, `encodePng` and `spike` (the session's
// mutable slots) on `globalThis`.

// Compile a previz sequence and open a demo engine at the capture size.
function load(sequence, width, height, supersample) {
  spike.reel = previz.compile(sequence);
  spike.engine = previzDemo.demoEngine({ width: width, height: height, supersample: supersample });
  return info();
}

// What the compiled reel knows: everything a Python lowering needs.
function info() {
  var r = spike.reel;
  return {
    duration: r.duration,
    loop: r.loop,
    times: r.times,
    states: r.states,
    segments: r.segments,
    transitions: r.transitions,
    space: r.space,
    undeclared: r.undeclared,
    warnings: r.warnings
  };
}

// previz's own evaluation: the reel's state at each time.
function statesAt(times) {
  return times.map(function (t) { return spike.reel.at(t); });
}

// Draw states the caller hands over (the STATE-driven path): base64 PNGs.
async function renderStates(states, width, height) {
  var out = [];
  for (var i = 0; i < states.length; i++) {
    out.push(encodePng(await spike.engine.render(states[i], { width: width, height: height })));
  }
  return out;
}

// Evaluate and draw in one round trip (the TIME-driven path): base64 PNGs.
async function renderTimes(times, width, height) {
  return renderStates(statesAt(times), width, height);
}
