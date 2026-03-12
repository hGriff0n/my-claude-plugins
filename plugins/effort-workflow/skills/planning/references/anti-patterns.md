# Decomposition Anti-Patterns

| Anti-pattern | Problem | Fix |
|---|---|---|
| Decomposing all tiers in one pass | Over-specifies before enough information is available | One tier per session |
| Activity framing ("implement X") | No clear completion condition; scope drifts | Write deliverables with `[done:: ...]` |
| No method chosen | Arbitrary child structure, unclear sequencing | Choose method before generating children |
| Children that overlap | MECE violation; ambiguous ownership | Re-partition before continuing |
| Children that don't exhaust parent | Scope surprises mid-execution | Coverage check before closing session |
| Missing `[done:: ...]` on stubs | Completion criteria discovered late, causing rework | Define done at creation time |
| Atomic tasks > 4h | Probably composite | Split or re-scope |
| Atomic tasks < 30min | Over-granular; overhead exceeds value | Merge with a sibling |
| Skipping tiers for complex efforts | Milestones become unmanageable bags of tasks | Add the intermediate tier |
