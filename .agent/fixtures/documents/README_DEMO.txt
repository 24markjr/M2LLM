JARVIS PROFESSIONAL DEMO PACK

Recommended live demonstration:
1. Warm the model with: python -m app.cli health
2. Show ambiguity refusal:
   python -m app.cli intent "Look at these files." --docs aurora_project_report.txt
3. Run the full investigation:
   python -m app.cli investigate "Investigate whether Project Aurora's timeline and budget information is consistent. Identify contradictions and explain what evidence supports each finding." --docs aurora_project_report.txt aurora_financial_report.txt aurora_milestone_report.txt aurora_budget.csv
4. Optional PDF demonstration:
   python -m app.cli investigate "Summarise the key financial figures and flag anything inconsistent." --docs aurora_project_report.pdf

Expected evidence:
- Project report: baseline completion 30 April 2026; approved budget INR 380,000.
- Financial report: expenditure INR 450,000; latest completion milestone 14 May 2026.
- Milestone report: M4 closed 14 May 2026 but baseline/change request is not established.
- Budget CSV: line items total INR 490,000.

IMPORTANT:
The documents intentionally contain inconsistencies and an evidence gap. Do not edit them before the demo.
