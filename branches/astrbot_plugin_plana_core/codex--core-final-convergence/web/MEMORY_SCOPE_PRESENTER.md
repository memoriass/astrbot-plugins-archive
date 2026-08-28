# Memory Scope Presenter

`memory_scope_payload.py` provides the embedded dashboard with read-only scope labels and counts.

The presenter uses existing storage, feedback, and recall-gap services. It does not write data or change memory governance behavior.

Memory pages must not assume that imported or production-preview data belongs to the `global` scope. They should select an active user scope and allow the user to switch it.
