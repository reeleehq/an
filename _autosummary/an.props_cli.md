# an.props_cli

`an props …` — a prop’s asset folder from the shell (an#340).

A CORE module (`an.tools` imports it at module level), so it reaches the
stage only inside its functions: the stage is behind the core firewall.

Wired into the top-level dispatcher as the `props` namespace
(`an.tools._dispatch_namespaces`), programmatically, per pillar 8: plain
functions taking strings and returning the text to print; the business logic is
[`an.stage.prop_validate`](an.stage.prop_validate.md#module-an.stage.prop_validate). The prop’s twin of `an character validate` /
`an character contract`.

### Functions

| [`contract`](#an.props_cli.contract)()                | Print what a prop folder must hold, generated from the schema and the rig rules.   |
|----------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| [`validate`](#an.props_cli.validate)(name[, out_dir]) | Check a prop's folder (prop.json + parts/) against the rig contract, offline.      |

### an.props_cli.contract()

Print what a prop folder must hold, generated from the schema and the rig rules.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### an.props_cli.validate(name, out_dir='')

Check a prop’s folder (prop.json + parts/) against the rig contract, offline.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

name: the prop’s key (its folder name under out_dir), or a path to its
: folder or to its prop.json

out_dir: parent directory of the keys; defaults to ./assets/props
