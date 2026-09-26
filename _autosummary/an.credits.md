# an.credits

What a rendered video owes, and to whom.

`an` composes work it did not create into a video its user ships. Recording where
that work came from (`an.ir.assets.AssetSource`) is half the job; the other half
is being able to *produce* the credits, because \*\*a licence recorded and never
displayed is not compliance\*\* — it is a note to oneself.

So this module walks a project’s reachable assets and answers three questions a
user actually has:

- what third-party work is in this video?
- what must I display, verbatim, to ship it?
- is anything in here unverified?

The third is the one that matters most and is easiest to lose. An asset with no
licence is reported as **UNKNOWN**, never as “nothing owed”: those are different
answers, and collapsing them is exactly how an obligation goes missing.

### Functions

| [`collect_credits`](#an.credits.collect_credits)(mall)            | Walk a project mall and gather every recorded `AssetSource`.   |
|-----------------------------------------------------------------------------------|----------------------------------------------------------------|
| [`credits_for_project`](#an.credits.credits_for_project)(project_dir) | Credits for the project at `project_dir`.                      |

### Classes

| [`CreditsReport`](#an.credits.CreditsReport)([entries])   | Everything a project owes, split by whether we actually know.   |
|-----------------------------------------------------------------------------|-----------------------------------------------------------------|

### *class* an.credits.CreditsReport(entries=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Everything a project owes, split by whether we actually know.

#### format()

Human-readable, and honest about what it does not know.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

#### *property* owed *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[CreditEntry]*

Entries that definitely require an attribution.

#### *property* unverified *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[CreditEntry]*

Entries whose licence we could not classify.

Deliberately its own list rather than folded into [`owed`](#an.credits.CreditsReport.owed). Folding
them in cries wolf; folding them into “nothing owed” hides a real
obligation. Neither is honest, so they are counted separately — the same
reason `priv`’s upkeep keeps `unavailable` apart from `findings`.

### an.credits.collect_credits(mall)

Walk a project mall and gather every recorded `AssetSource`.

Three stores carry provenance: characters, **props** (an#108) and
**environments** (an#110). Each was added by the PR that gave that store
real art, which is the rule rather than a coincidence — a walk that skips a
store holding third-party plates does not return less information, it
returns an affirmative false statement to exactly the people who need the
opposite. Styles will join when a StylePack has art (#112).

Legacy reconstruction runs on characters only: it recovers a DiceBear
record from `metadata.dicebear_*`, which no other store has ever written.

* **Return type:**
  [`CreditsReport`](#an.credits.CreditsReport)

### an.credits.credits_for_project(project_dir)

Credits for the project at `project_dir`.

* **Return type:**
  [`CreditsReport`](#an.credits.CreditsReport)
