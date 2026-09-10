# Phase 15.11 Cleanup Safety Audit

## Boundary Reviewed

`StorageDialog.move_selected` passes selected `FileCandidate.path` values to
the injected `FileManager`. `FileManager.move_to_trash` is the only local
mutation path. It rejects symlinks, resolves and requires a regular file under
the configured Downloads root, rechecks device/inode identity, and calls only
`send2trash`.

Remote storage is read-only. `AuthenticatedNodeProvider.storage_candidates`
requests only `storage_candidates`, and `RemoteService` exposes no cleanup
operation or file-action backend. Arbitrary paths therefore cannot cross the
remote wire as cleanup requests.

## Safe Blocked Outcome

The required remote cleanup prerequisites are not present: opaque
target-created candidate IDs, durable or expiring target registry, target
revalidation, target-side authorization, and explicit cleanup confirmation as
one complete contract. No path-based or generic remote deletion was added.

Remote cleanup affordances remain absent: non-local `StorageDialog` instances
are read-only and keep Move Selected to Trash disabled, even if a future
metadata grant advertises `CLEANUP` before the target contract exists. Local
cleanup remains unchanged and continues to use the existing Downloads,
symlink, regular-file, device/inode, and Trash checks.

## Validation Evidence

- `tests.test_remote_contract` rejects a signed `cleanup` request containing
  `/etc/passwd` as an unknown wire operation.
- `tests.test_storage_conservative` covers Downloads containment, direct and
  ancestor symlinks, missing and directory targets, partial Trash failures,
  duplicate inputs, and device/inode change between validation checks.
- `tests.test_storage_dialog` covers the disabled read-only Trash affordance.

Decision: **remote cleanup blocked; remote storage review remains read-only**.

## Phase 15.13 Compatibility Evidence

The protocol remains version `"1"`. Compatibility tests verify that additive
read payload fields and absent legacy process/thermal fields remain decodable,
while unknown response envelope fields, unsupported protocol versions, and
malformed security identity data fail closed.

Hello capability decoding retains only known `NodeCapability` values. It does
not infer capabilities from unknown values, and the operation validator rejects
unknown operations before dispatch. Legacy trusted-node records remain
loadable when endpoint metadata is absent, but missing or malformed permissions
decode to no permissions; no action authorization is fabricated.

Validation evidence: `tests.test_remote_compatibility`,
`tests.test_remote_contract`, and `tests.test_cluster` pass; Ruff, Pyright, and
Mypy pass for the touched files.

## Phase 15.14 Deployment Evidence

The source dependency declarations are identical: `pyproject.toml` and
`requirements.txt` each contain `psutil>=5.9`, `send2trash>=1.8`,
`nvidia-ml-py>=12.0; platform_system != "Darwin"`, and `zeroconf>=0.131`.
The latest local wheel was `dist/system_analyzer-1.4.2.0-py3-none-any.whl`.

`tests.test_deployment_validation` checks the wheel's package members, remote
modules, typed marker, both console entry points, `Requires-Dist` metadata,
Python floor, and absence of tests/bytecode content. `./install/verify.sh`
also passed against that wheel, including its recorded SHA256 checksum
`60a617bf9278f5816145b6462fe18a6debef470d443102629d5d4a7645a18282`.

The safe local evidence available here is a non-destructive wheel inspection,
build verification, and a temporary virtualenv exercise: the previous local
wheel installed, the new wheel upgraded it, installed imports resolved from
the temporary environment, and `system-analyzer-snapshot --help` exited zero.
The GUI entry point was not launched because this host has no usable display.
No live uninstall was run. The Windows PowerShell and native macOS installer
paths were not executable on this Linux host, so there is no platform evidence
for those paths. No claim is made for those unsupported runs.

The installer scripts preserve user preferences and trusted-node records by
installing the wheel through pip rather than deleting application data. This
was inspected from the script paths; persistence preservation across a real
upgrade remains unverified in this environment. Remote cleanup remains
explicitly read-only unless its target-side candidate and authorization
contract is implemented and separately verified.

Exact local deployment commands were `./install/build.sh`,
`./install/verify.sh`, `python -m unittest tests.test_packaging
tests.test_package_structure tests.test_deployment_validation -v`, and a
temporary-venv install/upgrade using `pip install --no-index --no-deps` for
the `1.4.1.0` then `1.4.2.0` wheels. The host was Python 3.12.3 with
`psutil 7.2.2`, `Send2Trash 2.1.0`, `nvidia-ml-py 13.610.43`, and
`zeroconf 0.151.3`.
