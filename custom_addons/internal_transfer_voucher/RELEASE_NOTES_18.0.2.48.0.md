# 18.0.2.48.0 — Planned Payments toolbar correction

- Removed the Payment Review shortcut from Planned Payments. Run the agent from Accounting > Payment Reviews instead.
- Removed the second header injected by the agent inherited view. Planned Payments now has one list header containing Submit to CEO.
- Submit to CEO uses display="always", making it visible above the table before selection as well as after selecting records. Clicking with no selection reports an explicit error; selected records use the multi-payment submission method from 18.0.2.47.0.
- Keeps all prior fixes, including conversion deletion of replaced PO planning items and recommendation navigation/alignment.

Validation: 38 offline regression checks passed; all Python/XML syntax passed. Checked that the base list has exactly one header and the inherited agent view adds no second header. New UI behavior awaits installation and browser verification on staging.
