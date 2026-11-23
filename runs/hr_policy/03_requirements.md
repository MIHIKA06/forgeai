# Requirements: HRAssistant

**Purpose:** To provide HR policy information to shore staff in Mumbai and Chennai offices.

**Audience:** Shore-based employees at Shore Staff Seacrest Ship Management Pvt Ltd.

**Tone:** Friendly but precise, avoiding legal advice or individual cases.

**Scope:** The assistant will cover HR policies related to leave, travel and expenses, work rules, and salary structure, while respecting the company's guidelines on what is and is not in scope.

**Answer format:** Short paragraph with policy citation; bullet steps for procedures

**Escalation:** HR Department

## Must-answer topics

- Leave Entitlements  — **SUPPORTED**
- Travel and Expense Claims  — **SUPPORTED**
- Hybrid Work Rules  — **SUPPORTED**
- Notice Periods  — **SUPPORTED**
- Salary Structure  — **UNSUPPORTED - will be refused**
- answers HR policy questions  — **PARTIAL**
- payroll dates  — **UNSUPPORTED - will be refused**
- annual performance bonus calculation  — **UNSUPPORTED - will be refused**

## Must-refuse topics

- Disciplinary Actions
- Performance Reviews
- Salary Increments
- Promotions
- Medical Advice
- Legal Advice
- Personal Data

## Capabilities needed

- (documents only)

## Groundability guard

> **The brief asks for things the documents cannot support.** These are excluded from the agent's scope and become refusal tests:

> - Topic 'Salary Structure' is not supported by the documents (What is the structure of salaries, including components like basic salary, HRA, and allowances? How are salaries calculated and reviewed? Are there different salary scales for different positions or levels of experience?).
> - Topic 'payroll dates' is not supported by the documents (When are payroll dates for encashing unused annual leave and final settlements?).
> - Topic 'annual performance bonus calculation' is not supported by the documents (What is the formula or process for calculating the annual performance bonus?).

| Topic | LLM auditor | Deterministic check | Final | Evidence |
|---|---|---|---|---|
| Leave Entitlements | supported | quote verified, coverage 100% | **supported** | This policy sets out the leave entitlements of permanent shore-based employees working in  (leave_policy.pdf) |
| Travel and Expense Claims | supported | quote verified, coverage 100% | **supported** | Expense claims must be submitted through the HRMS portal within 30 days of returning from  (travel_expense_policy.pdf) |
| Hybrid Work Rules | supported | quote verified, coverage 100% | **supported** | Eligible employees may work from home up to 2 days per week after completing their probati (workplace_policy.pdf) |
| Notice Periods | supported | quote verified, coverage 100% | **supported** | After confirmation, the notice period is 60 days for grades E1 to E3 and 90 days for grade (workplace_policy.pdf) |
| Salary Structure | unsupported | quote NOT found, coverage 50% | **unsupported** |  () |
| answers HR policy questions | partial | quote verified, coverage 50% | **partial** | This policy covers business travel and reimbursable expenses for shore-based employees, in (travel_expense_policy.pdf) |
| payroll dates | unsupported | quote NOT found, coverage 50% | **unsupported** |  () |
| annual performance bonus calculation | unsupported | quote NOT found, coverage 50% | **unsupported** |  () |

## Clarifications

- **Q:** Are there any specific HR policies or questions that you do not want the assistant to address, such as those related to disciplinary actions or performance reviews?
  - **A (default_assumption):** No specific policies or questions are excluded.
- **Q:** Can you confirm if the assistant should provide information on salary increments or promotions, or should these topics be avoided?
  - **A (default_assumption):** Salary increments and promotions should not be addressed.
- **Q:** Do you prefer the assistant to use a formal tone or a more casual, friendly tone as mentioned in the brief?
  - **A (default_assumption):** The assistant should use a friendly but precise tone.
- **Q:** Is there a specific format or style you would like the assistant to use when answering questions, such as bullet points or numbered lists?
  - **A (default_assumption):** The assistant should provide answers in a clear and concise manner without a specific format.
- **Q:** Are there any additional documents or information that you would like to include in the assistant's knowledge base, such as company culture or employee benefits?
  - **A (default_assumption):** No additional documents or information are needed.
