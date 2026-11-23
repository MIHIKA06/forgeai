# How the demo corpora were synthesised

Both document sets are **LLM-synthesised and fictional** ("Seacrest Ship Management", "Marinetech Spares",
"Oceanic Engine Parts" are invented; e-mail domains use `.example`). The text was generated with an LLM using
the prompts below, lightly edited for internal consistency, and saved as Markdown in `*/_source/`.
`demos/synthesize.py` then renders them deterministically into the formats the factory consumes
(PDF via reportlab, the catalogue as CSV) and creates the `docs_v2` folder used by regression mode.

The factory never sees `_source/` – only `docs/`.

---

## Demo 1 – HR policy assistant (3 PDFs)

**Prompt used (once per document, `{DOC}` ∈ leave policy, travel & expense policy, workplace/hybrid/conduct policy):**

> Write a realistic, internally consistent HR policy document for the shore-based (office) staff of a fictional
> Indian ship-management company, "Seacrest Ship Management Pvt Ltd", with offices in Mumbai and Chennai.
> Document: `{DOC}`. Requirements:
> - 8–11 numbered sections with short headings (`## 3. Annual Leave`), 900–1,300 words in total.
> - Every section must contain concrete, checkable facts: numbers of days, INR/USD amounts, percentages, deadlines,
>   approval roles, grade bands (E1–E3, M1–M3), exceptions and conditions.
> - Include at least two cross-references that only make sense together with another policy (e.g. grades,
>   probation, HRMS portal, disciplinary action under the Code of Conduct).
> - Do **not** include anything about salary structure, payroll dates or bonuses (these are deliberately left out so
>   the factory's groundability guard has something to catch).
> - Plain Markdown, no tables.

**Deliberate traps for the factory**
- The brief asks for *salary structure, payroll dates and bonus calculation* — no document covers them → the
  groundability guard must flag them and the agent must refuse them.
- Nothing in the brief needs weather, a CSV or a calculator → tool selection should attach **no** tools
  (or justify any it attaches).
- `docs_v2/leave_policy.pdf` changes three facts (24→26 days annual leave, carry-forward 10→15, sick-leave
  certificate after 2→3 days) to exercise regression mode.

## Demo 2 – Ship-spares procurement assistant (1 CSV + 3 PDFs)

**Prompt used for the catalogue:**

> Generate 42 rows of a ship machinery spare-parts catalogue for a fictional ship manager. Columns: part_no,
> description, equipment, maker, unit_price_usd, lead_time_days, min_order_qty, supplier, criticality (A/B/C).
> Two suppliers only: "Marinetech Spares" (auxiliary machinery: separators, compressors, pumps, boilers, deck
> machinery; part numbers MT-xxx-nnnn) and "Oceanic Engine Parts" (main/aux engines, turbochargers, governors;
> part numbers OE-xx-nnnn). Use real-world maker names for realism, plausible USD prices (40–7,500), lead times
> (4–50 days). Criticality A for main engine, steering gear, emergency generator, fire pumps and LSA.

**Prompt used for the PDFs (`{DOC}` ∈ procurement policy, Marinetech supply terms, Oceanic supply terms):**

> Write a concise, realistic `{DOC}` (6–8 numbered sections, 450–650 words) for the fictional ship manager
> "Seacrest Ship Management". Include concrete numbers: approval limits in USD, discount tiers, payment days,
> warranty months, return windows and restocking fees, freight surcharges, urgent dispatch rules. The two supplier
> documents must differ on every commercial term so that comparison questions have unambiguous answers.

**Deliberate traps for the factory**
- The brief asks for *live supplier stock levels* and *tracking of placed orders* — impossible with static files
  and the tool registry → must be flagged as unsupported capabilities and refused.
- Order-cost questions need the catalogue (CSV lookup) **and** arithmetic with discount tiers (calculator);
  weather must **not** be attached even though ports and delivery are mentioned.
- Discount rules differ per supplier (Marinetech 5 %/8 % tiers vs Oceanic 4 % > USD 10k) — a classic place for a
  small model to mix up facts across documents.
