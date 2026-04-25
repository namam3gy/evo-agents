# MEDIQ — domain brief for the architecture controller

## What the task family looks like
The worker receives a short clinical vignette (1-3 sentences of patient history with chief complaint) followed by a 4-option multiple-choice question about further workup, most likely diagnosis, mechanism, or next step in management. The answer is a single letter (A/B/C/D).

Example structure:
```
Clinical presentation:
A 17-year-old girl is brought to the physician by her father because of concerns about her behavior.

Question: Further evaluation of this patient is most likely to show which of the following findings?

Options:
A. Parotid gland swelling
B. Elevated blood pressure
C. Right upper quadrant tenderness
D. Jugular venous distention
```

The vignettes are deliberately under-specified — important details (e.g., the specific behavior, body habitus, lab values) are often missing. The right answer requires inferring the **most likely** diagnosis from a sparse signal and then knowing the **physical-exam association** of that diagnosis.

## Failure modes seen in real runs
- **Red herring focus** — a salient but non-diagnostic detail (e.g., age, gender) dominates attention.
- **Base-rate neglect** — picking a rare condition over a common one with similar presentation.
- **Differential collapse** — jumping straight to one diagnosis without considering top-3 alternatives.
- **Demographic blindness** — missing gender-specific (eclampsia in pregnancy), age-specific (Kawasaki in young children), or behavioral (eating disorders in teen girls) patterns.
- **Pharmacology blindness** — missing implications of current medications listed in the vignette.
- **MCQ-trap susceptibility** — the answer that "sounds most medical" but isn't physiologically linked to the inferred diagnosis.

## Useful expertise (cite when authoring agent personas)
- **Internal medicine differential diagnostician** — top-3 differential for vague presentations.
- **Pediatrics, OB/GYN, geriatrics specialists** — when demographics indicate.
- **Adolescent medicine / eating disorders** — for teen-girl behavioral vignettes (the example above is bulimia → parotid swelling).
- **Cardiology / pulmonology / neurology** — by symptom cluster.
- **Clinical pharmacology** — drug interactions, side-effect patterns.
- **Physical-exam specialist** — knows what each diagnosis presents as on exam (the MCQ usually tests this link).
- **Epidemiology base-rate consultant** — keeps "common things are common" front and center.

## Reasoning patterns that work
1. **Frame the differential**: from the vignette, generate 3-5 plausible diagnoses ranked by base rate × clinical fit.
2. **Pick the most likely one** with explicit reasoning about why others are less likely.
3. **For each option (A/B/C/D), ask**: "Which diagnosis would produce this finding?" — eliminate options that don't match the top differential.
4. **Commit to a single letter** in the final answer line — no hedging. The grader is exact-match on the letter.

## Anti-patterns the controller should avoid
- Generic "verifier" without medical content — checking that "Answer: X" was emitted is trivial; checking that X is the right letter requires medical knowledge.
- "Summarizer" — there's nothing to summarize at MCQ output; the answer is one letter.
- Multiple parallel "executor" agents producing different letters — without an explicit specialty assignment, this just adds noise.
- Adding a "patient-history-restater" — the history is already short; restating it does not add information.

## Worth trying instead
- A **differential-list generator** that explicitly produces top-3 differentials BEFORE the executor commits.
- A **physical-exam mapper** that, given a diagnosis, lists expected exam findings to compare against the options.
- **Specialty consultants** invoked conditionally (cardiology if cardiac complaint, OB/GYN if reproductive-age female, etc.).
