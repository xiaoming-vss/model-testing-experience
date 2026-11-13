# Derived coverage account (compatibility)

The single [case-local audit](evidence-workbench.md) is authoritative for generation and repair. Its target clauses reference actual executable fields; the exporter derives target-to-step coverage automatically and runs check_design_coverage.py on that derived account. Do not write or maintain the same mapping twice.

Legacy callers may still supply --account to the exporter for an additional check. The legacy checker remains available; passing a manually supplied account never bypasses audit freshness or unresolved-target rejection. No account fields enter YAML or become user prerequisites.

Read-only advisory review enumerates included targets directly from the unchanged design and candidate. It does not create, bind or obtain a passing account/audit, and reports only concrete supported findings. Existing generation evidence may be consulted as a hint, not treated as authority.
