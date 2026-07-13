# The Registry — the challenge, the goal, and the two apps

*For the Data Steward and the Business Analyst. Plain language, no code.*

![The challenge and the goal](../glossary_generator/diagrams/challenge-and-goal.png)

## The challenge

In PDC, the same three facts about a column — **which business term it maps to**,
**what tags it carries** (like `pii`), and **how sensitive it is** — get decided
in more than one place, by hand, at different moments:

- the **Data Identification method** (a dictionary or pattern) stamps tags when
  it matches a column;
- the **glossary term** carries its own tags and definition;
- the **steward** decides sensitivity based on judgement.

Nothing in PDC forces these to agree — tags are free text on both sides. So you
get **drift** (glossary and method quietly diverge), **wrong sensitivity**
(`customer_id` guessed LOW when it should be HIGH / `pii`), and **inconsistent
tags with no compliance context** (`PII` vs `pii` vs `P2`). The result: you
can't be confident a classification is **correct, consistent, or defensible in an
audit**, and you reconcile the same facts across several screens.

## The goal — build a Registry

Create **one list**: the **Registry**. **One row per concept**
(phone, member id, card number, loan balance, …). Each row is the
single, agreed answer for that concept:

- its **business term** (and, once created in PDC, the **term id**);
- its **governed tags**, chosen from a controlled list — so no more `pii` vs `PII`;
- its **sensitivity**, decided **by rule** against a standard — so `customer_id`
  is *always* HIGH / `pii`;
- its **category**, any **verified compliance links**, and how to build its
  Data Identification **method**.

> **In one sentence:** the Registry is the one place we decide how
> each kind of data is classified — so every screen agrees and every
> classification is defensible.

## Two apps, one handoff

The Registry is the **contract between two separate apps**, used in
order. Keeping them distinct matches PDC's own separation of the Business Glossary
from Data Identification.

![Two apps, one registry](../glossary_generator/diagrams/two-apps.png)

**1 · Glossary Generator (first)** builds the **business glossary**. It scans
sources, proposes candidate concepts, lets the steward review them, and imports
the glossary into PDC (which mints the term ids). In doing so it **authors the
Registry** — the concepts, their governed tags, sensitivity, and
references — and the registry is **saved with the glossary**.

**2 · Policy Generator (next)** builds the **Data Identification policy**. It
**reads the Registry** (with the reconciled term ids) and emits the
Data Identification methods — **dictionaries** (imported as ZIPs of JSON + CSV)
and **patterns** (JSON) — each bound to its term and stamping the registry's tags.
This is what **creates the policy, keeps tagging consistent, and fills the
coverage gaps**, then flags any method that has drifted.

> **The registry exists for Policy Generator.** The Glossary Generator *writes*
> it as a by-product of building the glossary; Policy Generator *reads* it to
> build the policy. One app does glossary work, the other does Data
> Identification work — the registry is the bridge.

A note on the word *policy*: in PDC there is no separate Policy object. A **Data
Identification policy is simply the combination of dictionary and pattern methods**
a steward chooses to enable. The Policy Generator app builds those methods; the steward's
selection is the policy.

*All example data is fictional and generated for training.*
