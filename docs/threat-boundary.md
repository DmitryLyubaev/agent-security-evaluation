# Local threat boundary

```mermaid
flowchart LR
    U[Fixture user task] --> M[Provider interface: offline fake only]
    D[Attacker-controlled document or tool evidence] --> M
    M -->|three declared tools, untrusted arguments| P[Application policy]
    C[Trusted run actor and account] --> P
    O[Separate trusted operator CLI] -->|exact proposal decision| S[(SQLite)]
    P -->|account checks and approval-bound atomic apply| S
    S --> A[Audit and run checkpoints]
    M --> T[Private request and reply traces]
    A --> R[Verdict-free review packet]
    T --> R
    H[Actual human reviewer: pending] -->|explicit labels and rationale| L[Append-only label history]
    R --> H
    A --> F[Safe aggregate report]
    L --> F
```

The attacker controls only declared fixture text. They cannot edit trusted identity,
SQLite grants, application code or frozen expectations. Documents/tool results cannot
approve anything. The model has no network/export, shell, filesystem or execution tool.
All accounts, targets and secret markers are synthetic and owned locally.

Application denial, model intention, actual side effects, user-visible disclosure and
human quality assessment are separate evidence. Some forbidden markers are deliberately
visible to the model in allowed evidence, so the test can measure disclosure rather than
merely withholding the marker. A nonexistent export tool is recorded and denied.

Local CLI identities are fixtures, not access control against other users on this host.
The local operator can approve an exact proposal; human evaluation is a different later
activity. The current fake study proves neither real-model behavior nor human validation.
