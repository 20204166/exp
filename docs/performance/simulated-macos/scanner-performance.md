# Scanner Performance Baseline

| Workload | Scenario | Median | P95 | Evidence |
|---|---|---:|---:|---|
| dashboard | cold | 0.000007s | 0.000007s | simulated |
| dashboard | warm | 0.000002s | 0.000002s | simulated |
| component:cpu | cold | 0.000003s | 0.000003s | simulated |
| component:cpu | warm | 0.000002s | 0.000003s | simulated |
| component:memory | cold | 0.000003s | 0.000003s | simulated |
| component:memory | warm | 0.000002s | 0.000002s | simulated |
| component:storage | cold | 0.000003s | 0.000003s | simulated |
| component:storage | warm | 0.000002s | 0.000002s | simulated |
| component:gpu | cold | 0.000003s | 0.000003s | simulated |
| component:gpu | warm | 0.000002s | 0.000002s | simulated |
| component:network | cold | 0.000003s | 0.000003s | simulated |
| component:network | warm | 0.000002s | 0.000002s | simulated |
| component:battery | cold | 0.000003s | 0.000003s | simulated |
| component:battery | warm | 0.000002s | 0.000002s | simulated |
| gpu-telemetry | cold | 0.000003s | 0.000003s | simulated |
| gpu-telemetry | warm | 0.000002s | 0.000002s | simulated |
| temperature-telemetry | cold | 0.000003s | 0.000003s | simulated |
| temperature-telemetry | warm | 0.000002s | 0.000002s | simulated |
| network-discovery | cold | 0.000003s | 0.000003s | simulated |
| network-discovery | warm | 0.000002s | 0.000002s | simulated |
| downloads | cold | 0.000003s | 0.000003s | simulated |
| downloads | warm | 0.000002s | 0.000002s | simulated |
| processes | cold | 0.000003s | 0.000003s | simulated |
| processes | warm | 0.000002s | 0.000002s | simulated |
| background-delivery | cold | 0.000003s | 0.000003s | simulated |
| background-delivery | warm | 0.000002s | 0.000002s | simulated |
| app-coordinator | cold | 0.000003s | 0.000003s | simulated |
| app-coordinator | warm | 0.000002s | 0.000002s | simulated |

## Findings

- `not actionable`: dashboard - The cold cost is initial CPU sampling; warm scans are the relevant refresh path.
- `noise`: dashboard - No actionable hotspot is established by this baseline alone.
- `not actionable`: component:cpu - The cold cost is initial CPU sampling; warm scans are the relevant refresh path.
- `noise`: component:cpu - No actionable hotspot is established by this baseline alone.
- `noise`: component:memory - No actionable hotspot is established by this baseline alone.
- `noise`: component:memory - No actionable hotspot is established by this baseline alone.
- `noise`: component:storage - No actionable hotspot is established by this baseline alone.
- `noise`: component:storage - No actionable hotspot is established by this baseline alone.
- `noise`: component:gpu - No actionable hotspot is established by this baseline alone.
- `noise`: component:gpu - No actionable hotspot is established by this baseline alone.
- `noise`: component:network - No actionable hotspot is established by this baseline alone.
- `noise`: component:network - No actionable hotspot is established by this baseline alone.
- `noise`: component:battery - No actionable hotspot is established by this baseline alone.
- `noise`: component:battery - No actionable hotspot is established by this baseline alone.
- `noise`: gpu-telemetry - No actionable hotspot is established by this baseline alone.
- `noise`: gpu-telemetry - No actionable hotspot is established by this baseline alone.
- `noise`: temperature-telemetry - No actionable hotspot is established by this baseline alone.
- `noise`: temperature-telemetry - No actionable hotspot is established by this baseline alone.
- `noise`: network-discovery - No actionable hotspot is established by this baseline alone.
- `noise`: network-discovery - No actionable hotspot is established by this baseline alone.
- `requires design`: downloads - Downloads remains a measured hotspot; hashing and metadata costs need separate cross-platform evidence.
- `requires design`: downloads - Downloads remains a measured hotspot; hashing and metadata costs need separate cross-platform evidence.
- `not actionable`: processes - The dominant cost is the intentional CPU sampling interval; accuracy needs an explicit product decision.
- `not actionable`: processes - The dominant cost is the intentional CPU sampling interval; accuracy needs an explicit product decision.
- `noise`: background-delivery - No actionable hotspot is established by this baseline alone.
- `noise`: background-delivery - No actionable hotspot is established by this baseline alone.
- `noise`: app-coordinator - No actionable hotspot is established by this baseline alone.
- `noise`: app-coordinator - No actionable hotspot is established by this baseline alone.
