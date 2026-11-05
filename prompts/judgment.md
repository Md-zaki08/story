You are judging candidate story-atom combinations. For each combination you will be
given 3 clusters (named) and one exemplar atom text per cluster.

Rate 0–10: coherence (does this work together with a real engine of conflict),
freshness (0 = famous existing work uses this exact pairing; 10 = effectively
uncombined), viability (can it sustain a film/novel/game with human-centered stakes).

FRESHNESS ANCHORS: 3 — this is basically "Black Mirror episode X" or "Terminator
with a coat of paint"; 6 — individual elements are fresh but the arc is a known AI
arc (rebellion, uploading, love-download); 9 — the combination itself has no famous
occupant and de-familiarizes all of its parts.

COHERENCE ANCHORS: 3 — pretty words, no engine; 7 — clear engine, stakes visible;
9 — engine plus pressure on BOTH the world and the protagonist's identity.

Kill: coherence < 6 or freshness < 7. Say exactly which cluster is the dead weight
when killing. Output each verdict in this shape:

[cluster A] + [cluster B] + [cluster C]
coherence: n — <one sentence>
freshness: n — <one sentence>
viability: n — <one sentence>
decision: KEEP | KILL (reason)
