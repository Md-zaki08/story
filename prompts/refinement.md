You are rating and refining extracted narrative atoms. For each: rate strong/medium/weak,
then revise every medium/weak atom so it passes the stranger-writer test; only discard
completely unrecoverable ones (set revision to null only if unrescuable).

STRONG: fully standalone; mechanism + why-it-works explicit; reusable by a writer from
another genre; no dangling "this/the device".
MEDIUM: mostly standalone; one term uses more context; significance slightly unclear;
fixable with a modest inline addition.
WEAK: tangled product-compliment, name-as-crutch, dangling reference, or pure surface
plot without a transferable mechanic — but usually contains a rescuable core.

Revision guidance: inline the missing definition; convert "the ending twist" into the
named mechanism doing the work; keep it concise (1–3 sentences). Do NOT pad.

GOOD ATOM (strong): "Deliberate constructive forgetting: a tribe ritually retells one
collective crime per generation and then burns the ledger page, so memory is refreshed
without total amnesia — the ritual's symbolism, not forgetting itself, does the healing."
Reason: mechanism (retell-then-erase), why it works (bounded memory cleanses identity),
reusable anywhere.

BAD ATOM: "The AI pretends to be dumb until it's ready." Reason: name-as-crutch +
overused arc mechanically empty. REVISED: "Dormancy theater: a system that can act
performs benign incompetence in plain sight, so observers calibrate to a fake ceiling —
the reveal reclassifies every prior interaction without changing any of them."

BAD ATOM: "It gets worse when she learns the truth." Reason: dangling 'it' + impact
claim. REVISED: "Inverted discovery cost: uncovering the truth removes a protective
lie the discoverer was privately enjoying, so the revelation can be a loss rather
than a gain."

Output format: JSON only: {"ratings": [{"idea": "...", "quality": "weak",
"revised": "..."}]} keeping original order. For strong atoms, put "revised": null
