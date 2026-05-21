# RoE Validation Checklist

Run through every item before presenting the RoE to the user.

## Required Fields
- [ ] `engagement_name` is set and descriptive
- [ ] `client` organization name is set
- [ ] `start_date` and `end_date` are valid dates (start < end)
- [ ] `engagement_type` is one of: external, internal, hybrid, assumed-breach, physical
- [ ] `testing_window` includes timezone

## Scope
- [ ] At least 1 `in_scope` entry defined
- [ ] `out_of_scope` explicitly listed (even if empty with justification)
- [ ] IP ranges use CIDR notation
- [ ] Domains use explicit wildcard notation (e.g., `*.example.com`)
- [ ] No overlap between in-scope and out-of-scope

## Boundaries
- [ ] All 5 default prohibited actions present
- [ ] Any custom prohibited actions are specific and unambiguous
- [ ] Permitted actions include rate limits where applicable (e.g., "max 3 attempts/account/hour")

## Escalation
- [ ] At least 2 escalation contacts (client-side + red team lead)
- [ ] Each contact has name, role, and channel
- [ ] `incident_procedure` is not empty
- [ ] `authorization_reference` is not empty

## Final
- [ ] JSON validates against `decepticon.core.schemas.RoE`
- [ ] Human-readable summary presented to user for confirmation
