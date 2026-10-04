# Business Connectors

No connectors exist yet. Planned structure (Phase 6+):
```
backend/app/connectors/
├── ghar_nepal/
├── tolemate/
├── paradise_nepal/
└── common/
```

Existing applications (gharnepal.kitetool.com, tolemate.kitetool.com,
paradisenepal.kitetool.com) stay independent — connectors call their
controlled APIs rather than merging databases or rewriting them. Where real
API docs/access aren't available, mock connectors are built first and swapped
for real ones later. No real endpoints, schemas, or business rules are
invented ahead of that access — see the master spec's explicit instruction
on this.

Tolemate is the designated first real integration (Phase 6).
