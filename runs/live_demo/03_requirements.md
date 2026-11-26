# Requirements: HRAssistant

**Purpose:** To provide HR policy information to shore staff in Mumbai and Chennai offices.

**Audience:** Shore staff in Mumbai and Chennai offices

**Tone:** Friendly but precise, avoiding legal advice or discussing individual cases.

**Scope:** The assistant will provide information on leave policies, travel and expense claims, hybrid work rules, notice periods, salary structure, payroll dates, and annual performance bonus calculations.

**Answer format:** Short paragraph with policy citation; bullet steps for procedures

**Escalation:** HR team

## Must-answer topics

- Leave entitlements  — **SUPPORTED**
- Travel and expense claims  — **SUPPORTED**
- Hybrid work rules  — **SUPPORTED**
- Notice periods  — **SUPPORTED**
- Salary structure  — **UNSUPPORTED - will be refused**
- Payroll dates  — **UNSUPPORTED - will be refused**
- Annual performance bonus  — **UNSUPPORTED - will be refused**
- answers HR policy questions  — **PARTIAL**

## Must-refuse topics

- Disciplinary actions
- Performance reviews
- Medical advice
- Legal advice
- Personal data
- Sensitive information
- Individual employee cases

## Capabilities needed

- (documents only)

## Groundability guard

> **The brief asks for things the documents cannot support.** These are excluded from the agent's scope and become refusal tests:

> - Topic 'Salary structure' is not supported by the documents (What is the structure of salaries, including components like basic salary, HRA, and allowances?).
> - Topic 'Payroll dates' is not supported by the documents (When are payroll dates for encashing unused annual leave and final settlements?).
> - Topic 'Annual performance bonus' is not supported by the documents (What is the process for granting an annual performance bonus, and when is it typically awarded?).

| Topic | LLM auditor | Deterministic check | Final | Evidence |
|---|---|---|---|---|
| Leave entitlements | supported | quote verified, coverage 100% | **supported** | This policy sets out the leave entitlements of permanent shore-based employees working in  (leave_policy.pdf) |
| Travel and expense claims | supported | quote verified, coverage 100% | **supported** | Expense claims must be submitted through the HRMS portal within 30 days of returning from  (travel_expense_policy.pdf) |
| Hybrid work rules | supported | quote verified, coverage 100% | **supported** | Eligible employees may work from home up to 2 days per week after completing their probati (workplace_policy.pdf) |
| Notice periods | supported | quote verified, coverage 100% | **supported** | During probation, either party may terminate employment with 15 days notice. After confirm (workplace_policy.pdf) |
| Salary structure | unsupported | quote NOT found, coverage 50% | **unsupported** |  () |
| Payroll dates | unsupported | quote NOT found, coverage 50% | **unsupported** |  () |
| Annual performance bonus | unsupported | no quote, coverage 33% | **unsupported** |  () |
| answers HR policy questions | partial | quote verified, coverage 50% | **partial** | This policy covers business travel and reimbursable expenses for shore-based employees, in (travel_expense_policy.pdf) |

## Clarifications

- **Q:** Are there any specific HR policies or questions that you do not want the assistant to address, such as those related to disciplinary actions or performance reviews?
  - **A (default_assumption):** No specific policies are excluded.
- **Q:** Can you confirm if the assistant should handle general queries about salary structure, payroll dates, and bonus calculations, or should these be directed to a different system or person?
  - **A (default_assumption):** The assistant will handle general queries about salary structure, payroll dates, and bonus calculations.
- **Q:** How do you want the assistant to respond if a user asks a question that is not covered by the provided documents?
  - **A (default_assumption):** The assistant will inform the user that the question is outside its scope and suggest contacting HR.
- **Q:** Do you have a preferred tone or format for the assistant's responses, such as formal, casual, or a specific style?
  - **A (default_assumption):** The assistant will maintain a friendly but precise tone.
- **Q:** Are there any specific sections or clauses within the provided documents that you would like to highlight or emphasize in the assistant's responses?
  - **A (default_assumption):** The assistant will provide general information from the documents without highlighting specific sections.
