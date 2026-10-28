# Field Service Copilot: take-home data

This is a document export from a fictional customer, Corvane Field Services. Corvane services pumps, compressors, chillers and conveyors at four customer sites in North America and Europe. In 2024 it bought a Dutch service company, Kyltek, and the integration isn't finished.

## What's here

- `corpus/`: 42 files exported from Corvane's systems: manufacturer manuals and service bulletins (PDF), controlled procedures and work instructions (SharePoint, DOCX), the field wiki (Confluence HTML export), emails, a Teams channel export, maintenance-system exports from two different systems, Salesforce case exports, and an ops review. It's a real-world export, so expect some mess.
- `users.json`: the technicians, their groups, and what each group means.
- `permissions.json`: for each document, the groups a user needs. A user may see a document only if they belong to every group in `required_groups`. An empty list means every technician may see it.
- `eval/eval_questions.json`: 10 questions, each asked by a specific user, with a reference answer from Corvane's experts.

The full brief is in the prompt we sent you.
