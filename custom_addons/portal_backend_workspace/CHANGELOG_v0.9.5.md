# 18.0.0.9.5 - Sales ownership, own-approver confirmation and data hooks

- All Company Documents retains visibility and editable-draft scope. It no longer
  grants submission or conversion-request rights over another creator's quotation.
- create_uid is the authority for ownership. Neither reassigned salesperson nor
  historical editor-enrollment metadata grants authorship. The existing save API
  preserves the original creator instead of enrolling the editor.
- Sales Approvers may confirm their own saved draft/sent quotation directly,
  including when the implied Prepare role is also present. Other creators'
  quotations retain independent review. Core/native validations remain in the
  confirmation path. Direct confirmation is recorded separately, not as a fake
  independent approval. Repeated requests are rejected.
- The original forms gain Confirm Sales Order only where authorized. Unsaved
  header/line changes disable this action until saved. No CSS/layout is replaced.
- One explicit customer-eligibility provider is used by initial dropdowns, Search
  More and validation. Standalone contacts use Workspace Customer / Client.
- Project display, selection, save and search use one provider hook. Optional
  integrations can supply an existing project field without duplicating values.
- Own quotations are excluded from an approver's review queue and pending count.
- The independent Sales Data Bridge reads the original Sales customer checkbox
  and construction project, only when their exact known field contracts exist.
- The EPS bridge, routing, bell components and Purchase/Accounting/HR source are
  unchanged. The standalone base dependency list is unchanged.
