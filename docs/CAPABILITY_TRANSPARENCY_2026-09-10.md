# Capability Transparency

This is a bounded provider audit. A platform branch is not treated as native
evidence merely because it exists in the source tree. Runtime `ResourceSummary`
states remain authoritative for the selected node; the matrix below describes
what the current providers can attempt.

## State Vocabulary

| State | Meaning |
| --- | --- |
| Supported | The provider returned the metric for this node. |
| Unsupported | An authoritative provider result proves the metric is absent or not exposed. |
| Temporarily unavailable | A supported provider failed, timed out, or returned an unreadable result. |
| No data yet | The node has not produced a sample in the current view. |
| Permission required | The provider was denied access. |
| Not verified on native platform | The source declares no native evidence for that platform. |
| Failed | The operation itself failed; this is separate from capability. |

## Provider Matrix

| Component / metric | Linux | macOS | Windows |
| --- | --- | --- | --- |
| CPU usage | Supported via psutil | Supported via psutil | Supported via psutil |
| Memory usage | Supported via psutil | Supported via psutil | Supported via psutil |
| Storage capacity | Supported via psutil | Supported via psutil | Supported via psutil |
| GPU model | lspci or NVML provider | system_profiler provider | PowerShell CIM provider |
| GPU utilization | Supported when the NVML provider is installed and readable; otherwise Temporarily unavailable | Unsupported by current provider | Supported when the NVML provider is installed and readable; otherwise Temporarily unavailable |
| Network traffic/interfaces | Supported via psutil | Supported via psutil | Supported via psutil |
| Battery charge | Supported when psutil exposes a battery; otherwise Unsupported | Same | Same |
| Battery temperature | Unsupported by current providers | Unsupported by current providers | Unsupported by current providers |
| CPU/GPU/NVMe thermals | Supported when psutil exposes matching sensors; repeated empty reads on a supported card resolve to Unsupported after the bounded confirmation window; provider failures remain Temporarily unavailable | Not verified on native platform | Not verified on native platform |
| SMART data | Unsupported by current providers | Unsupported by current providers | Unsupported by current providers |
| Process inventory/review | Supported through psutil and safety policy | Supported through psutil and safety policy | Supported through psutil and safety policy |
| Downloads cleanup | Supported, restricted to Downloads and Trash | Supported, restricted to Downloads and Trash | Supported, restricted to Downloads and Recycle Bin |

GPU model detection is not GPU utilization. Thermal lines are not fabricated
from GPU or battery data, and SMART data is never inferred from capacity.

## Node Scope

Remote resource summaries carry their capability state in the signed node
snapshot. The selected node context owns its capability map and counters;
local platform declarations are not applied to remote nodes.

For v1 remote compatibility, older peers continue to receive the legacy
`unknown` capability field while newer peers recover the precise state from the
additive `capability_state` field. Permission classification is provider-specific:
the battery provider preserves `PermissionError`; generic psutil sensor reads
remain fail-soft when they cannot distinguish permission from provider failure.

## Evidence

- Provider fakes cover Linux, macOS, and Windows dispatch in
  `tests/test_gpu_name.py` and the capability catalog tests.
- The native smoke command used here was a direct `SystemScanner.scan_component`
  run for CPU, memory, storage, GPU, network, and battery. Phase 13 additionally
  ran the repository Linux regression and static gates.
- This environment is Linux. Linux provider smoke ran here; macOS and
  Windows native provider execution remains unverified because those hosts and
  their native commands are unavailable.
- The current Linux environment has Ruff, Pyright, and Mypy in `.venv`.
  `ruff check .` passed; repository-wide format checking reports pre-existing
  findings, Pyright reports pre-existing findings, and whole-repository Mypy is
  blocked by duplicate module names in versioned PoC directories. These
  limitations do not change the capability state vocabulary.
