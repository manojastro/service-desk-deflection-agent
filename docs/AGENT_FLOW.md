# Agent Flow

```mermaid
stateDiagram-v2
    [*] --> Normalize
    Normalize --> Classify
    Classify --> Retrieve
    Retrieve --> Plan
    Plan --> Policy
    Policy --> Escalate: unsafe / unknown / low evidence
    Policy --> Confirm: state-changing tool
    Policy --> Execute: read-only tool
    Policy --> Confidence: knowledge-only
    Confirm --> [*]: await employee decision
    Confirm --> Execute: approved continuation
    Confirm --> Cancelled: declined
    Execute --> Verify
    Verify --> Confidence
    Confidence --> Resolve: grounded and verified
    Confidence --> Escalate: low confidence or failure
    Resolve --> Persist
    Escalate --> Persist
    Persist --> [*]
```

Every node emits a safe operational event with node name, decision summary, elapsed time, timestamp, and non-sensitive metadata. These events explain system behavior without exposing hidden reasoning.

Classification, retrieval, and tool verification contribute to confidence. The deterministic policy currently resolves at `>= 0.60`. Tool failure always escalates. A knowledge-only request also needs approved retrieval evidence. Maximum agent steps are configured through `MAX_AGENT_STEPS` and LangGraph's recursion limit.

The serialized confirmation checkpoint binds the pending tool and arguments to the session. An employee cannot confirm another employee's session or substitute a new tool/target in the confirmation request.

