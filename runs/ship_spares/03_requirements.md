# Requirements: SparePartAssistant

**Purpose:** To assist chief engineers and technical superintendents in managing ship spare-parts procurement.

**Audience:** Chief engineers and technical superintendents, often on board with slow internet.

**Tone:** Practical and concise, providing quick answers.

**Scope:** The assistant will handle inquiries related to spare parts procurement, including price, lead time, supplier terms, and order tracking. It will not provide detailed policy explanations or handle sensitive or legal matters.

**Answer format:** Short paragraph with policy citation; bullet steps for procedures

**Escalation:** the responsible team

## Must-answer topics

- Part Lookup  — **SUPPORTED**
- Supplier Comparison  — **PARTIAL**
- Order Estimation  — **PARTIAL**
- Stock Levels  — **SUPPORTED**
- Order Tracking  — **PARTIAL**
- look up parts in the spares catalogue  — **PARTIAL**
- estimate the total cost of an order  — **SUPPORTED**
- compare supplier terms  — **SUPPORTED**
- check approval level and procurement rules  — **PARTIAL**
- track the status of orders  — **UNSUPPORTED - will be refused**

## Must-refuse topics

- Legal Advice
- Personal Data
- Sensitive Information
- Detailed Policy Explanations
- Escalation Procedures
- Supplier Prioritization
- Multiple Supplier Tracking

## Capabilities needed

- Arithmetic on Prices
- Today's Date for Deadlines
- Exact Lookup in Catalogue Table
- Live Stock Levels

## Groundability guard

> **The brief asks for things the documents cannot support.** These are excluded from the agent's scope and become refusal tests:

> - Topic 'track the status of orders' is not supported by the documents (How to track the status of orders once they are placed?).
> - Capability 'Live Stock Levels' cannot be provided by documents or tools (No tool or document supports live stock level information.).

| Topic | LLM auditor | Deterministic check | Final | Evidence |
|---|---|---|---|---|
| Part Lookup | supported | quote verified, coverage 50% | **supported** | part_no: OE-ME-7002; description: Main engine exhaust valve spindle; equipment: Main engin (spares_catalogue.csv) |
| Supplier Comparison | partial | quote verified, coverage 50% | **partial** | Supplier performance is reviewed every 6 months on price, on-time delivery and quality. (procurement_policy.pdf) |
| Order Estimation | partial | quote verified, coverage 50% | **partial** | Purchase orders are approved according to the total order value in US dollars. (procurement_policy.pdf) |
| Stock Levels | supported | quote verified, coverage 50% | **supported** | Each vessel must hold the minimum onboard stock defined in its critical spares list. (procurement_policy.pdf) |
| Order Tracking | partial | quote NOT found, coverage 50% | **partial** |  () |
| look up parts in the spares catalogue | supported | quote verified, coverage 40% | **partial** | Oceanic Engine Parts is an authorised distributor of OEM spares for two-stroke and four-st (supplier_oceanic_terms.pdf) |
| estimate the total cost of an order | supported | quote verified, coverage 75% | **supported** | Prices are as per the catalogue in US dollars, ex-warehouse Singapore. Volume discounts ar (supplier_marinetech_terms.pdf) |
| compare supplier terms | supported | quote verified, coverage 67% | **supported** | Payment is due 45 days from the invoice date. Invoices paid within 10 days receive an addi (supplier_marinetech_terms.pdf) |
| check approval level and procurement rules | supported | quote verified, coverage 40% | **partial** | Purchase orders are approved according to the total order value in US dollars: (procurement_policy.pdf) |
| track the status of orders | unsupported | no quote, coverage 33% | **unsupported** |  () |

- Capability **'Live Stock Levels'** cannot be provided: No tool or document supports live stock level information.

## Clarifications

- **Q:** Are there specific approval levels and procurement rules for emergency purchases that need to be integrated into the assistant's responses?
  - **A (default_assumption):** Emergency purchases follow standard approval and procurement rules.
- **Q:** Do you need the assistant to escalate certain types of requests or provide guidance on how to handle them?
  - **A (default_assumption):** The assistant will not escalate requests but will provide practical answers.
- **Q:** Do you require the assistant to provide detailed explanations of the procurement policy or just summaries?
  - **A (default_assumption):** The assistant will provide summaries of the procurement policy.
- **Q:** Are there any specific suppliers that must be prioritized or avoided by the assistant?
  - **A (default_assumption):** The assistant will consider all suppliers equally.
- **Q:** Do you need the assistant to track orders from multiple suppliers simultaneously?
  - **A (default_assumption):** The assistant will track orders from a single supplier at a time.
