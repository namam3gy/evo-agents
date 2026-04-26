# AgentClinic (single-pass mode) — domain brief for the architecture controller

## What the task family looks like
The worker receives a complete OSCE-style clinical case as JSON (Patient demographics, History, Symptoms, Past_Medical_History, Social_History, Review_of_Systems, Physical_Examination_Findings, Test_Results, Objective_for_Doctor) and must output the **single most likely primary diagnosis** as a short string.

Example:
```
You are given a complete OSCE-style clinical case. Based on all of the
information below, state the single most likely primary diagnosis.

Case details (JSON):
{
  "Objective_for_Doctor": "Evaluate and diagnose the patient presenting with chronic diarrhea and lower abdominal discomfort.",
  "Patient_Actor": {
    "Demographics": "31-year-old female",
    "History": "The patient reports experiencing chronic diarrhea on most days for the past four months..."
    ...
  },
  "Physical_Examination_Findings": {...},
  "Test_Results": {...}
}
```

Expected answer style: short diagnostic name, e.g., "Irritable Bowel Syndrome", "Acute appendicitis", "Type 2 diabetes mellitus".

The **single-pass** mode is critical: there are NO follow-up questions, no patient interaction, no additional tests. Whatever is in the JSON is all the worker gets. The answer is graded by an LLM judge on diagnostic equivalence.

## Failure modes seen in real runs
- **Verbose differential without commitment** — producing 5 possibilities and not picking one. The judge wants ONE primary diagnosis.
- **Anchoring on chief complaint** — missing context-changing details from social history (alcohol, travel, occupation) or labs.
- **Ignoring "context" clues** — recent travel suggests infectious; occupational exposure suggests environmental; family history suggests genetic.
- **Hedging language** — "possibly", "could be", "consistent with". The judge prefers decisive answers.
- **Missing red-flag triage** — failing to consider emergency-tier diagnoses first when red flags are present.
- **Over-specific diagnosis** — picking a sub-type when the data only supports the broader diagnosis (and vice versa).
- **Diagnostic vocabulary mismatch** — using a colloquial term where the canonical name is expected (e.g., "stomach flu" vs "viral gastroenteritis").

## Useful expertise (cite when authoring agent personas)
- **General internal medicine + family practice** — broad differential generation across organ systems.
- **Specialty consultants** — gastroenterology for GI cases, cardiology for chest pain, neurology for neuro signs, infectious disease for fever-plus-context.
- **Triage specialist** — emergency vs subacute vs chronic; identifies red flags first.
- **Concise diagnostic communicator** — produces the 1-3 word canonical diagnosis name, no hedging.
- **Demographics-aware reasoner** — adjusts differential based on age / sex / occupation / region.

## Reasoning patterns that work
1. **Triage** the case: emergency / subacute / chronic — what's the time pressure?
2. **Read demographics + chief complaint first**, then enrich with past medical history, social history, exam, labs.
3. **Generate a differential of 2-3** candidate diagnoses, weighing base rate × clinical fit × specific evidence.
4. **Pick the most likely** with brief justification; reject the others briefly.
5. **State the diagnosis using the canonical clinical term**, no hedging, no qualifier.

## Anti-patterns the controller should avoid
- A "summarizer" that adds verbosity (this domain *needs* less verbosity, not more).
- A "verifier" without diagnostic competence — verifying the format of "Diagnosis: X" is trivial; verifying that X is right needs a specialist.
- Parallel executors with the same generic role (just adds noise).
- Adding a "patient-question-asker" — useless in single-pass mode (no patient interaction).

## Worth trying instead
- A **triage agent** that fires first and routes to a specialist agent based on symptom system.
- **Specialty consultants** added conditionally (GI consult for diarrhea cases, cardiology for chest pain) — but only if the case load actually warrants the specialty.
- A **decisive-diagnosis writer** at the end whose explicit job is "convert the prior reasoning into ONE diagnosis name with no hedging".
- **Removing** any agent whose output doesn't change the final diagnosis vs without it.
