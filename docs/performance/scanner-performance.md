# Scanner Performance Baseline

| Workload | Scenario | Median | P95 | Evidence |
|---|---|---:|---:|---|
| dashboard | cold | 0.273739s | 0.273739s | native |
| dashboard | warm | 0.006476s | 0.008593s | native |
| component:cpu | cold | 0.240692s | 0.240692s | native |
| component:cpu | warm | 0.002318s | 0.006018s | native |
| component:memory | cold | 0.001279s | 0.001279s | native |
| component:memory | warm | 0.001196s | 0.001803s | native |
| component:storage | cold | 0.031218s | 0.031218s | native |
| component:storage | warm | 0.000205s | 0.000237s | native |
| component:gpu | cold | 0.052332s | 0.052332s | native |
| component:gpu | warm | 0.000430s | 0.000674s | native |
| component:network | cold | 0.001910s | 0.001910s | native |
| component:network | warm | 0.002002s | 0.002423s | native |
| component:battery | cold | 0.021886s | 0.021886s | native |
| component:battery | warm | 0.000070s | 0.000089s | native |
| gpu-telemetry | cold | 0.022385s | 0.022385s | native |
| gpu-telemetry | warm | 0.000279s | 0.000471s | native |
| temperature-telemetry | cold | 0.000195s | 0.000195s | native |
| temperature-telemetry | warm | 0.000074s | 0.000081s | native |
| network-discovery | cold | 0.000036s | 0.000036s | native |
| network-discovery | warm | 0.000008s | 0.000009s | native |
| downloads | cold | 0.275159s | 0.275159s | native |
| downloads | warm | 0.227794s | 0.274282s | native |
| processes | cold | 0.513712s | 0.513712s | native |
| processes | warm | 0.464966s | 0.489108s | native |
| background-delivery | cold | 0.001342s | 0.001342s | native |
| background-delivery | warm | 0.001333s | 0.002195s | native |
| app-coordinator | cold | 0.001313s | 0.001313s | native |
| app-coordinator | warm | 0.001205s | 0.001718s | native |

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
