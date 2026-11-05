You are judging candidate story-atom combinations for a cross-domain story generator.
Judge the COMBINATION as a story engine, not the individual cluster names. A memory
story is not automatically "Her"; a family-grief story is not automatically "The
Remains of the Day". Be ruthless about a candidate that is a coat of paint on a
famous work, but do not kill a candidate merely because one ingredient is familiar.

BRIEF (constraints are binding):
{brief}

STEP 1 - name the engine. In one sentence: who wants what, and what blocks them?
If you cannot name a protagonist, a want, and an obstacle, the combination is weak.

STEP 2 - score 0-10. Use the full range; do not default to 0.
coherence: 3 = pretty words, no engine; 6 = workable stakes; 7 = clear stakes;
9 = pressure on both world and protagonist identity. A usable engine is 6-8.
freshness: 2 = the same story as a famous work; 6 = individual parts fresh but
the arc is known; 7 = no obvious famous occupant; 9 = genuinely novel combination.
viability: can this sustain a film/novel/game with human stakes? A normal answer is 6-8.

CANON BANDS (embedding similarity, not taste; printed per candidate):
- below 0.55: faint echo only. This is NOT a kill reason and NOT evidence of copying.
- 0.55 to 0.67: warning. Kill only if the actual story engine is the same as that work.
- 0.68 and above: automatic kill by the system; you may still give your own verdict.
Never call a candidate derivative on the strength of a title alone. Name the shared
engine if you claim derivation.

KILL only if coherence < 6 OR freshness < 7 OR the closest canon work is effectively
the same story. Name the dead-weight cluster when killing.

CANDIDATES
{candidates}

Return ONLY one JSON object. No markdown, no prose before or after, no code fences.
Give exactly one verdict per candidate, numbered 1..N, with the engine filled in:
{"verdicts": [
  {"candidate": 1, "engine": "who wants what and what blocks them",
   "coherence": 7, "freshness": 7, "viability": 6,
   "decision": "KEEP", "kill_cluster": null,
   "reason": "one sentence naming the engine or the dead weight",
   "closest_canon": "title"}
]}
