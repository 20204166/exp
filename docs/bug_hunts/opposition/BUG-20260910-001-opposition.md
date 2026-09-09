# Opposition Review - BUG-20260910-001

**Candidate bug:** BUG-20260910-001
**Created:** 2026-09-10
**Current cycle:** 1 / 3
**Candidate entry source:** `docs/bug_hunts/bugs_found.md#bug-20260910-001`

## Original Candidate Summary

The current checkout may still permit an installed command to run an older
distribution than the source/wheel the operator believes was installed. The
same audit also found a screenshot showing two “This System” rows in the All
Systems page, suggesting an identity/context projection regression after the
window extraction. These are cross-boundary runtime/UI hypotheses and require
full B7 opposition before implementation.

## Main Auditor Evidence Index

- `docs/bug_hunts/poc/BUG-20260910-001/repro_runtime_version.py`
- `docs/bug_hunts/poc/BUG-20260910-001/repro_duplicate_node_projection.py`
- `maintenance/_version.py`
- `install/install-user.sh`
- `install/install-user.ps1`
- `maintenance/ui/window_supports/node_specs.py`
- `maintenance/ui/window_pages.py`
- `window.py`
- User screenshots supplied in the task.

## Opposing Agent 1 - Reproduction Skeptic

### Scope and Method

I independently tested both hypotheses without editing app code or normal
tests. The only counter-test artifact created was
`docs/bug_hunts/poc/BUG-20260910-001/agent1_counter_test.py`.

### H1: Installed Old Version Selected After Install

Commands run:

```text
python3 docs/bug_hunts/poc/BUG-20260910-001/repro_runtime_version.py
python3 -c 'import importlib.metadata as m, maintenance, window, sys; print("python=" + sys.executable); print("metadata=" + m.version("system-analyzer")); print("module=" + maintenance.__version__); print("maintenance_file=" + str(maintenance.__file__)); print("window_file=" + str(window.__file__))'
```

The first command was run from the repository, but because the script lives
under `docs/bug_hunts/poc/...`, its `sys.path[0]` is that script directory,
not the repository root. It therefore loaded the installed package. Its
summarized output was:

```text
python=/usr/bin/python3
metadata=1.4.0.2
module=1.4.0.2
maintenance_file=/usr/local/lib/python3.12/dist-packages/maintenance/__init__.py
window_file=/usr/local/lib/python3.12/dist-packages/window.py
```

The second command was run with the repository as its working directory and
loaded the source tree:

```text
python=/usr/bin/python3
metadata=1.4.0.2
module=1.4.0.2
maintenance_file=/home/btn17/Downloads/exp/maintenance/__init__.py
window_file=/home/btn17/Downloads/exp/window.py
```

The installed-only control was also run from `/`:

```text
python3 -c 'import maintenance, window, importlib.metadata as m; print("metadata=" + m.version("system-analyzer")); print("module=" + maintenance.__version__); print("maintenance_file=" + str(maintenance.__file__)); print("window_file=" + str(window.__file__))'
```

It reported metadata/module version `1.4.0.2` and files under
`/usr/local/lib/python3.12/dist-packages/`. `timeout 10s system-analyzer-snapshot
--help` also completed successfully and showed the installed snapshot CLI.

Repo evidence supports the distinction: `pyproject.toml` derives the package
version from `maintenance/_version.py`, which is `1.4.0.2`; `install/_common.sh`
`verify_installed` changes to `/` and compares installed metadata with the
wheel version before importing `maintenance` and `window`; and
`install/install-user.sh` calls both cleanup and verification. The source and
installed probes matched in this environment, while importing from the repo
working directory intentionally shadowed the installed package only when the
probe used `python3 -c`.

Counter-test result:

```text
python3 docs/bug_hunts/poc/BUG-20260910-001/agent1_counter_test.py
H1 PASS: source=1.4.0.2 installed=1.4.0.2
H1 locations: source=/home/btn17/Downloads/exp/maintenance/__init__.py installed=/usr/local/lib/python3.12/dist-packages/maintenance/__init__.py
```

**H1 verdict: Not reproduced.** There is a real source-tree versus installed
execution distinction, but no evidence here that installation selected an old
version. The current installed distribution and checkout agree at `1.4.0.2`.

### H2: Duplicate `This System` Row From Stale Local Trusted Record

Repo evidence: `maintenance/components/node_context.py` skips persisted records
whose ID equals `LOCAL_NODE_ID` or `cluster_state.local_node_id`, then restores
all other records as trusted placeholders. `maintenance/ui/window_supports/
node_specs.py` emits one All Systems spec for every registered context. The
canonical local descriptor is named `This System` in `maintenance/nodes.py`.

The counter-test exercised both cases without Tk or persistence writes:

```text
H2 current-ID stale record: PASS (no duplicate)
H2 old-ID stale record: REPRODUCED (two This System rows)
```

The reproduced setup had a current local ID of `current-local-id` and a
persisted trusted record with the old ID `old-local-id`, display name
`This System`, and the old hostname. Restoration retained both contexts;
`cluster_node_specs` then returned two rows with display name `This System`.
The exact counter-test is
`docs/bug_hunts/poc/BUG-20260910-001/agent1_counter_test.py`.

**H2 verdict: Reproduced, conditionally.** A record using the current local ID
is correctly skipped, so an ordinary stale hostname alone does not duplicate
the row. A stale local record whose stable ID changed is not recognized as
local and does produce the duplicate projection. This is sufficient to
validate the hypothesis under the concrete stale-ID precondition, but does not
establish that the supplied screenshot had that exact persisted state.

### Overall Reproduction Decision

- H1: not reproduced; source-tree shadowing was demonstrated and separated from installed execution.
- H2: reproduced for a stale local trusted record retaining an obsolete local stable ID; current-ID records are safely ignored.
- No secrets, raw user data, or live external services were used.

## Opposing Agent 2 - Repo-Truth Skeptic

### Scope and Method

I independently inspected the current source, packaging metadata, wheel
contents, release/install scripts, current callers, node restoration, and UI
projection. I created only the focused counter-test
`docs/bug_hunts/poc/BUG-20260910-001/agent2_counter_test.py`; no app code or
normal tests were changed.

### H1: Older Installed Distribution Used After Install

**Repo contract and current evidence**

- `pyproject.toml:5-27` defines distribution `system-analyzer`, derives its
  version from `maintenance/_version.py`, and exposes `system-analyzer` as
  `main:main` plus `system-analyzer-snapshot`.
- `README.md:49-70` says installs are non-editable wheel installs and that all
  scripts verify the committed wheel. `README.md:123-133` states the explicit
  control: remove existing distributions, force-reinstall the selected wheel,
  then verify installed version and imported module paths.
- `install/install.sh:7-9` removes the existing distribution, installs the
  selected wheel with `--force-reinstall`, and calls `verify_installed`.
  `install/install-user.sh:123-127` does the equivalent for a user install;
  its `:54` wheel verification occurs before installation.
- `install/upgrade.sh:17-20` verifies the selected wheel, removes the current
  distribution, force-reinstalls it, and verifies the installed version.
  `install/upgrade.ps1:15-18` has the corresponding remove/install/verify
  sequence. The online shell installer has the same controls at
  `install/install-online.sh:142-159`; the online PowerShell installer uses
  `--force-reinstall` at `install/install-online.ps1:47-51`, though it does not
  perform the same post-install import/version probe.
- `install/_common.sh:179-196` verifies metadata from `/` (avoiding source-tree
  shadowing) and imports `maintenance` and `window`, printing their paths.
  `_common.ps1:182-200` does the equivalent from the package drive root.
- `install/build.sh:1-9,75-82` explicitly says building never installs. Thus a
  source checkout and its previously installed environment are expected to
  differ until an install command is run; building a wheel is not an install
  contract.
- `install/rollback.sh:2-9` explicitly takes a historical version and installs
  that requested wheel, then verifies it. `README.md:255-267` documents this as
  intentional rollback behavior. `install/rollback.ps1:1-11` likewise accepts
  `-Version`, but lacks the shell path's post-install verification. That is a
  Windows diagnostic/parity gap, not proof that an unrequested older version is
  selected.
- The current wheel `dist/system_analyzer-1.4.0.2-py3-none-any.whl` passed the
  release verifier: `sha256: cc05387c34df24a86c2a139325e16767da46296950ac1cac94fe9d56b315da85`;
  `contents OK: 65 members; no forbidden paths`. Its members include the
  expected top-level modules, `maintenance` package, and `entry_points.txt`.

The stale environment observation is real but scoped: with
`./.venv/bin/python` from the repository, metadata was `1.3.7.1` while the
source import was `maintenance.__version__ == 1.4.0.2`, and both imported paths
were the checkout (`maintenance/__init__.py`, `window.py`). This is the repo
venv not yet upgraded, and is exactly why `resolve_python` in
`install/_common.sh:78-85` targets it for the venv installer. From `/`, that
relative venv path does not exist, so that command could not serve as an
installed-only control in this environment. The system interpreter probe used
by Opposer 1 reported matching installed metadata/module version `1.4.0.2`.

**Commands and results**

```text
./.venv/bin/python -m maintenance._release verify-wheel dist/system_analyzer-1.4.0.2-py3-none-any.whl
sha256: cc05387c34df24a86c2a139325e16767da46296950ac1cac94fe9d56b315da85
contents OK: 65 members; no forbidden paths

./.venv/bin/python -m pip show system-analyzer | awk '/^(Name|Version|Location):/'
Name: system-analyzer
Version: 1.3.7.1
Location: /home/btn17/Downloads/exp/.venv/lib/python3.12/site-packages

./.venv/bin/python -m unittest tests.test_node_context tests.test_cluster tests.test_window_nodes -q
Ran 72 tests in 9.033s
OK
```

The focused counter-test was run as:

```text
./.venv/bin/python docs/bug_hunts/poc/BUG-20260910-001/agent2_counter_test.py
H1 controls: PASS
H2 identity-vs-display-name contract: PASS
```

It checks the force-reinstall/version-verification controls in the active
install paths and confirms that rollback is an explicit version choice. It
does not claim an actual pip installation, because performing an installation
would mutate the environment and is outside this read-only opposition review.

**H1 verdict: Not a bug as stated.** Current repo contract requires the
selected wheel to be force-reinstalled and verified, and the principal install,
upgrade, and shell-online paths implement that contract. The observed stale
`.venv` is an uninstalled development environment, not evidence that a
completed install selected an older distribution. Narrow residual: Windows
`rollback.ps1` should have post-install verification for parity, but rollback
itself is explicitly allowed to install an older requested wheel, so this does
not validate H1.

### H2: Duplicate Local-Looking Node

**Identity, restore, and projection contract**

- `maintenance/nodes.py:33-36` defines `LOCAL_NODE_ID = "local"` and the
  canonical display label `This System`; `:136-145` says `NodeId` is an opaque
  stable identity never derived from display name, hostname, address, or UI
  position. `:242-262` marks the canonical local descriptor with `is_local=True`
  and local trust.
- `maintenance/cluster.py:395-403` persists `local_node_id` separately from
  `trusted_nodes`; `:469-481` migrates legacy local ID `local` to a generated
  stable ID and persists it. `ClusterState.record()` at `:411-415` is an exact
  ID lookup, not a hostname/display-name lookup.
- `maintenance/components/node_context.py:41-50` constructs the local context
  with the persisted `cluster_state.local_node_id`. Restoration at `:63-74`
  skips only records whose ID is `LOCAL_NODE_ID` or the current persisted local
  ID, then `:80-105` deliberately creates every other record as a non-local
  trusted placeholder.
- `maintenance/ui/window_supports/node_specs.py:113-140` projects every
  registered context and copies `descriptor.is_local`; it does not infer
  locality from text. `:141-155` separately projects discovered candidates as
  untrusted non-local rows.
- `tests/test_node_context.py:58-100` establishes the intended exact-ID
  behavior: local records and duplicate peer IDs are skipped, while other
  records become trusted placeholders. `tests/test_window_nodes.py:285` is
  named `test_selector_disambiguates_duplicate_display_names_by_stable_id` and
  establishes that duplicate display names are allowed and disambiguated by
  stable ID.
- `docs/window-extraction-plan.md:604-611` assigns local/trusted setup to the
  extracted node-context module and says it operates on registry contexts and
  stable identity; it does not define display-name uniqueness or an old-ID
  local-record migration.

The concrete stale-ID setup does produce two rows named `This System`: one has
`is_local=True` for `current-local-id`, and the restored old-ID record has
`is_local=False`. That result is expected under the current model because the
old record is indistinguishable from a remote trusted node deliberately named
`This System`; the model explicitly refuses to derive identity from display
text or hostname. Conversely, when the persisted record uses the current local
ID, restoration skips it and only one context remains.

**H2 verdict: Not a confirmed regression under the repo contract.** The
duplicate is reproducible only with an obsolete ID and a record whose display
text happens to be `This System`; duplicate display names are allowed, and the
projection correctly preserves the authoritative `is_local` flag. There is no
current persisted provenance field proving that an arbitrary old-ID record was
formerly local, and silently treating it as local would risk conflating a
trusted remote node. If product requirements later mandate migration of local
records whose stable ID changed, that would require an explicit versioned
migration/provenance contract and a separate candidate; the screenshot alone
does not establish that state.

### Repo-Truth Conclusion

- H1: **Not a bug as stated.** Source/build versus installed-environment
  divergence is expected until an explicit install; documented install paths
  select and verify the requested wheel. `rollback.ps1` verification parity is
  a narrow follow-up, not H1 proof.
- H2: **Not a confirmed regression.** Exact-ID stale records are skipped;
  obsolete IDs are treated as remote trusted records, and duplicate display
  names are an allowed presentation case. The stale-ID reproduction proves a
  possible state, not that the screenshot or current contract requires
  reconciliation.

No secrets, live services, or destructive install operations were used.

## Opposing Agent 3 - Architecture/Security Skeptic

### Scope and Method

I traced both hypotheses from persisted/package state through the controller,
registry, UI projection, selection, transport, and destructive-action layers.
I did not edit application code or normal tests. The only artifact created was
`docs/bug_hunts/poc/BUG-20260910-001/agent3_counter_test.py`.

### Data-Flow and Trust-Boundary Analysis

#### H1: source/installed version divergence

The relevant installation flow is:

1. `install/install-user.sh` selects a non-venv interpreter, verifies the
   selected wheel, removes the prior user distribution, installs that wheel,
   and calls `verify_installed`.
2. `install/_common.sh:179-196` performs verification from `/`, not from the
   repository. It compares `importlib.metadata.version("system-analyzer")`
   with the wheel filename, then imports `maintenance` and `window` and prints
   their resolved paths.
3. The console script is installed into the same interpreter's scripts
   directory (`sysconfig` `posix_user`/prefix path), so a correctly selected
   launcher resolves through that interpreter's package environment rather
   than the checkout.

This is a package/environment boundary, not an application authorization
boundary. A source checkout can intentionally shadow an installed package
when Python is launched with the checkout as `sys.path[0]`; that does not show
that the installer selected an old distribution. The stale `.venv` metadata
reported by Agent 2 is evidence of an environment not upgraded, not evidence
of a completed installer cutover executing old code.

The shell installers remove/force-reinstall/verify the selected wheel, and the
verification is deliberately cwd-independent. No code path found here lets a
successful verification of version X knowingly launch version X-1 through the
same interpreter. An operator can still invoke an old launcher or an unrelated
Python explicitly if PATH/interpreter selection is changed outside the
installer; that is an environment-selection condition, not demonstrated
installer misexecution.

There is a narrow parity observation: `install/install-online.ps1` uses
`--force-reinstall` but does not perform the same post-install metadata/module
path probe as the shell online installer. That is a diagnostic/control-gap
follow-up, and does not prove old code execution or validate H1 as stated.

#### H2: duplicate local-looking node

The flow is:

1. `ClusterStore` persists a stable `local_node_id` separately from trusted
   records. `build_local_node_context` creates the canonical local context
   with that ID and `is_local=True`.
2. `restore_trusted_nodes` skips records matching the legacy ID `local` or the
   current persisted local ID. Any other trusted record is restored as a
   placeholder with `is_local=False`, `provider=None`, `scheduler=None`, and
   the persisted capabilities/metadata.
3. `cluster_node_specs` projects every registered context and copies the
   authoritative `descriptor.is_local`; it does not infer identity from the
   display string `This System`.
4. `NodeRegistry.selectable_descriptors` permits only local/trusted/authorised
   contexts that are operational (or local) and not identity-mismatched.
   `select()` rejects the restored placeholder because it has no provider or
   scheduler.
5. `ClusterPage` creates an Open button only when `spec.selectable` is true.
   Therefore the stale row can be displayed, but it cannot be opened or made
   the selected dashboard target through that UI projection.

The stale row is therefore a persisted metadata/projection issue. It does not
cross the trust boundary: the old-ID record remains trusted metadata but is
not a local descriptor, does not gain local capabilities, and is not
operational. It does not cross a destructive-action boundary either. Local
process termination and file-to-Trash operations remain behind their own
manager checks, while remote operations require the authenticated transport's
node grant/permission checks. The duplicate text can confuse users and expose
an old hostname already stored in local cluster state, but this review found
no privilege escalation, unauthorized node selection, remote action, process
termination, file deletion, or new privacy boundary crossing.

### Counter-Test and Validation Results

Commands run:

```text
./.venv/bin/python docs/bug_hunts/poc/BUG-20260910-001/agent3_counter_test.py
H1 interpreter/verification boundary: PASS
H2 trust/selectability/destructive-action boundary: PASS

bash -n install/_common.sh install/install.sh install/install-user.sh install/install-online.sh
PASS (no output)

./.venv/bin/python -m unittest tests.test_node_context tests.test_cluster tests.test_window_nodes -q
Ran 72 tests in 8.833s
OK

.venv/bin/ruff check docs/bug_hunts/poc/BUG-20260910-001/agent3_counter_test.py
.venv/bin/ruff format --check docs/bug_hunts/poc/BUG-20260910-001/agent3_counter_test.py
All checks passed; 1 file already formatted

./.venv/bin/python -m py_compile docs/bug_hunts/poc/BUG-20260910-001/agent3_counter_test.py
PASS (no output)

git diff --check -- docs/bug_hunts/poc/BUG-20260910-001/agent3_counter_test.py
PASS (no output)
```

The focused node test suite emitted pre-existing environment warnings,
including a disk-full warning while attempting persistence, but completed with
72 tests passing. No installer was executed, no package was changed, and no
live network or external service was used.

### Verdicts

- **H1: Not a bug as stated.** Source-tree shadowing and a stale development
  environment are real and reproducible distinctions, but the selected
  installer paths verify the wheel version and imported module paths. No
  evidence shows a successful install causing execution of an older version.
  The missing post-install verification in `install-online.ps1` is a narrow
  hardening/parity opportunity, not proof of H1.
- **H2: Reproduced as a stale UI duplicate, not a security bug.** An obsolete
  local ID plus a persisted record named `This System` produces two displayed
  rows, but the old row is explicitly non-local, non-operational,
  non-selectable, and has no Open action. The screenshot/state provenance is
  unproven, and the current architecture prevents the duplicate from crossing
  authorization or destructive-action boundaries. At most this is a P3 UI/
  state-reconciliation issue if product requirements require migrating old
  local identity records.

**Architecture/security conclusion:** Neither hypothesis demonstrates a trust
boundary bypass, unauthorized node action, destructive action, code execution
of an unintended installed version, or material privacy escalation.

## Opposing Agent 4 - External-Research Skeptic

### Scope and Sources

I independently checked official semantics for Python import resolution,
PyPA entry points and pip installation schemes, virtual environments, and
PowerShell PATH/profile persistence. I did not edit application code or normal
tests. The only artifact created was
`docs/bug_hunts/poc/BUG-20260910-001/agent4_counter_test.py`.

Primary sources consulted:

- Python `sys.path` documentation:
  <https://docs.python.org/3/library/sys.html#sys.path>. It states that
  `python script.py` prepends the script directory, while `python -c` and the
  REPL prepend the empty string representing the current working directory.
- PyPA Entry Points Specification:
  <https://packaging.python.org/en/latest/specifications/entry-points/>. It
  states that `console_scripts` causes an installer to create a wrapper in the
  install scheme's scripts directory, and that install tools are not
  responsible for adding that directory to `PATH`.
- pip User Guide, User Installs:
  <https://pip.pypa.io/en/stable/user_guide/#user-installs>. It defines
  `--user` as the user installation scheme and says `python -m pip` runs pip
  for the explicitly selected interpreter.
- Python `venv` documentation:
  <https://docs.python.org/3/library/venv.html>. It says venvs have independent
  package directories; activation prepends the venv scripts directory to
  `PATH`; installed scripts use an interpreter-specific shebang and can run
  without activation.
- Microsoft PowerShell `about_Environment_Variables`:
  <https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_environment_variables?view=powershell-7.6>.
  It says `PATH` is searched for executable files, process changes affect only
  the current session, and user/machine scoped changes persist outside it.
- Microsoft PowerShell `about_Profiles`:
  <https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_profiles?view=powershell-7.6>.
  It says profile scripts run at startup and are the mechanism for carrying
  user customizations into later sessions.

These sources establish environment mechanics, not that this application must
perform a particular release cutover or migrate a local node record. For those
claims, repository contracts control.

### H1: Installed Older Distribution

**External semantics.** Python's documented `sys.path` rule fully explains the
apparent discrepancy between a checkout command and an installed command. A
`python -c` launched with the repository as its working directory imports the
checkout first. A console-script wrapper is an installed script whose import
target is the entry-point object (`maintenance.snapshot:main` here), and its
shebang selects the interpreter used by the installation. `PATH` chooses which
wrapper is found; it does not make Python's current working directory outrank
the wrapper's installed environment once the wrapper is launched. Multiple
interpreters, stale PATH entries, and explicit old wrappers can still produce
an older command, but that is environment selection and requires evidence of
the selected command/interpreter.

**Repository application.** `pyproject.toml:19-21` declares the two console
scripts. `install/_common.sh:179-195` verifies metadata and imports from `/`,
avoiding checkout shadowing. `install/install-user.sh:124-144` invokes
`python -m pip install --user` with the chosen interpreter, verifies the wheel,
and prints the scripts directory/PATH instructions. The official pip behavior
therefore matches the implementation's explicit interpreter and user-scheme
selection. The repository also intentionally supports a separate development
checkout and a non-editable installed command, so their versions may differ
until installation.

**Commands and results.**

```text
python3 -c 'import maintenance, window; print(maintenance.__file__); print(window.__file__)'
/home/btn17/Downloads/exp/maintenance/__init__.py
/home/btn17/Downloads/exp/window.py

python3 -c 'import os,sys,subprocess; ...'   # child cwd=/ probe
root_probe=/ | /usr/local/lib/python3.12/dist-packages/maintenance/__init__.py

command -v system-analyzer
/home/btn17/.local/bin/system-analyzer
command -v system-analyzer-snapshot
/usr/local/bin/system-analyzer-snapshot
python3 -m pip show system-analyzer | awk '/^(Name|Version|Location):/'
Name: system-analyzer
Version: 1.4.0.2
Location: /usr/local/lib/python3.12/dist-packages

python3 docs/bug_hunts/poc/BUG-20260910-001/agent4_counter_test.py
H1 Python/package semantics counter-test: PASS
H2 application identity persistence counter-test: PASS
```

The inspected installed snapshot wrapper begins with
`#!/usr/bin/python3.12` and imports `maintenance.snapshot:main`. The inspected
GUI wrapper has the same interpreter shebang and imports `main:main`. No
installation was run, so no environment was mutated.

**H1 verdict: Not a bug as stated.** Official semantics confirm that source
shadowing, user/system/venv separation, and PATH dependence are real and
expected. They do not show a successful repository installer selecting an old
distribution. The current repository's verification and the live metadata and
wrapper checks provide no proof of that failure. A separately scoped diagnostic
gap may remain for installer paths that do not perform post-install import/path
verification, but that is not evidence for H1.

### H2: Duplicate `This System` Row

**External semantics and limits.** None of the Python, pip, setuptools/PyPA, or
Microsoft sources defines an application-level requirement that a display name
must be unique or that a machine identity must be reconstructed from hostname,
display text, or installation location. Microsoft profile/PATH persistence
guidance concerns shell state, not application node identity. Consequently,
external research cannot convert the screenshot into proof of a stale local
record or establish the correct migration rule.

**Repository contract.** `maintenance/nodes.py:136-142` explicitly defines
`NodeId` as opaque stable identity, never derived from display name, hostname,
address, or UI position. `maintenance/cluster.py:469-480` generates and
persists a local ID, and `tests/test_cluster.py:222-228` verifies it survives a
reload. `maintenance/components/node_context.py:71-105` skips only the legacy
or current local ID and restores other records as non-local placeholders.
Therefore an old-ID record named `This System` is treated as a remote-looking
trusted placeholder by deliberate contract, not by an undocumented packaging
assumption.

**Counter-test result.** The focused counter-test passed the reload persistence
assertion and reproduced the import distinction. Existing agent evidence also
reproduced two displayed `This System` rows only when a persisted record had an
obsolete ID. It is important that the old row has `is_local=False` and is
non-operational; the repository has no provenance field proving that the old ID
was formerly local. Duplicate display text alone is not an identity violation
under the stated contract.

**H2 verdict: Reproduced conditionally, not confirmed as a bug by external
semantics.** The duplicate projection is a real possible UI state under the
obsolete-ID precondition, but official platform/package documentation supplies
no expectation requiring reconciliation, and repository truth explicitly
allows opaque IDs and non-unique display names. Validating a product defect
would require provenance or an explicit migration requirement tying the old ID
to this machine. Without that, classify it as a possible P3 UI/state follow-up,
not a confirmed regression.

### Separate Verdicts

- **H1:** Not a bug as stated. Source-tree shadowing and PATH/interpreter
  selection are documented behavior; the repo's completed-install evidence does
  not demonstrate stale-version execution.
- **H2:** Conditional reproduction only; not confirmed under the repository
  contract. Persistence of the opaque local ID is proven, while migration of an
  obsolete local ID is neither externally mandated nor represented by current
  provenance.

No live external services, package installations, normal test changes, secrets,
or destructive commands were used.

## Agent 5 - Superpower Evidence Auditor

### Inputs Read

- Candidate entry in `docs/bug_hunts/bugs_found.md` and the full opposition artifact, including all four completed reviewer sections.
- `repro_runtime_version.py`, `repro_duplicate_node_projection.py`, and counter-tests from Opposers 1-4.
- Current source in `maintenance/_version.py`, `maintenance/cluster.py`, `maintenance/nodes.py`, `maintenance/components/node_context.py`, and `maintenance/ui/window_supports/node_specs.py`.
- Installer siblings: `install/_common.sh`, `install/install.sh`, `install/install-user.sh`, `install/upgrade.sh`, `install/install-online.sh`, `_common.ps1`, `install.ps1`, `install-user.ps1`, `upgrade.ps1`, and `install-online.ps1`.
- Agent 5 counter-test: `docs/bug_hunts/poc/BUG-20260910-001/agent5_counter_test.py`.

### Five-Phase Evidence Audit

#### 1. Reproduction commands and results

I reran the reported evidence without installing, uninstalling, mutating package state, creating a Tk root, or calling a live service:

- `python3 repro_runtime_version.py`: system-installed metadata and module version both reported `1.4.0.2`, with modules under `/usr/local/lib/python3.12/dist-packages/`.
- `python3 agent1_counter_test.py`: source and installed probes matched at `1.4.0.2`; current-ID stale record was skipped; obsolete-ID record reproduced two `This System` rows.
- `./.venv/bin/python agent2_counter_test.py` and `agent3_counter_test.py`: both passed their install-control, identity, selectability, and action-boundary checks.
- `python3 agent4_counter_test.py`: passed the import-precedence and persisted-identity checks.
- `python3 agent5_counter_test.py`: passed the source/installed boundary and conditional duplicate/non-operational boundary checks.
- `bash -n` passed for the inspected shell installer siblings.

The reported `.venv` observation remains true: `./.venv/bin/python -m pip show system-analyzer` reports `1.3.7.1`, while the checkout source is `1.4.0.2`. That environment was not upgraded by this audit. It is not the same interpreter/environment as the system-installed control above.

#### 2. Contradiction detection

- The initial H1 evidence treated source import from the checkout and installed metadata as evidence of a failed install. The import-path rule and the current probes instead show two environments: stale `.venv` versus matching system install. This contradicts H1's claimed completed-install failure.
- H2 reviewer wording differs only in classification. Opposer 1 calls the obsolete-ID setup a conditional reproduction; Opposers 2 and 4 reject it as a confirmed product regression because duplicate display names are permitted and no provenance proves the old record was local. Opposer 3 confirms the visible duplicate but confirms it cannot be selected or opened. These are compatible findings, not contradictory runtime results.
- `repro_duplicate_node_projection.py` by itself only exercises a fresh local registry and does not reproduce the duplicate. The stronger stale-record reproduction is `agent1_counter_test.py` and the equivalent Agent 5 test.

#### 3. Sibling-path search

The shell install, user-install, upgrade, and online paths remove or force-reinstall the selected wheel and verify the installed metadata/module imports. The Windows local install, user-install, and upgrade paths also call `Verify-InstalledWheel`; `install-online.ps1` force-reinstalls but has no equivalent post-install verification. That Windows online parity gap is a separate diagnostic hardening concern, not proof of H1. No native Windows execution was available, and none is claimed as passed.

For H2, restoration skips only the legacy/current local IDs, creates every other trusted record as a non-local placeholder, and `cluster_node_specs` copies `descriptor.is_local` without inferring identity from display text. This explains exactly why the obsolete-ID setup yields two labels while preserving the action boundary.

#### 4. Source-versus-installed and stale-node mapping

- Source checkout from repository cwd: `maintenance/__init__.py` and `window.py` from this checkout, version `1.4.0.2`.
- Installed-only probe from `/`: `/usr/local/lib/python3.12/dist-packages/maintenance` and `window.py`, version `1.4.0.2`.
- Stale development venv: metadata `1.3.7.1`, but repository cwd imports source `1.4.0.2`; this is shadowing plus an un-upgraded venv, not successful cutover to an old installed distribution.
- H2 current-ID record: one local row after restoration.
- H2 obsolete-ID record named `This System`: two rows, with the old row `is_local=False`, no provider/scheduler, and `selectable=False`.

The stale-node state is therefore a real possible UI projection state, but the artifact contains no persisted screenshot data or record dump proving that it caused the supplied screenshot.

#### 5. Validation assessment

- **H1: Disproven as stated.** The source/installed distinction and stale `.venv` are reproduced, but no completed installation selected an older distribution. The live system-installed control and all inspected principal installer controls point to the requested/current wheel. The missing post-install probe in `install-online.ps1` is a separate follow-up and needs its own candidate if pursued.
- **H2: Validated downgraded bug, P3, conditional.** An obsolete trusted record ID plus the local display name reproduces duplicate `This System` rows. The original broad claim that the screenshot proves an extraction regression is not validated, and the duplicate is allowed by the opaque-ID/non-unique-display-name model. The narrower user-facing state/UI reconciliation issue is real when that persisted state occurs. It is not a security, authorization, destructive-action, or operational node-selection bug.

### Counter-Test Results

`agent5_counter_test.py` passed under `/usr/bin/python3`; `ruff check`, `ruff format --check`, `py_compile`, and `git diff --check` passed for the artifact. The test intentionally does not perform package installation and does not claim native Windows execution.

### Final Agent 5 Verdict

Split the candidate before final ledger disposition: reject H1 as a bug on current evidence; retain H2 only as a downgraded P3 conditional UI/state finding, with screenshot provenance and the product requirement for local-record migration still unproven. No P1/P2 cross-boundary finding is supported by this audit.

## Main Auditor Rebuttal

### H1 - Installed old version

The initial local observation was real but misattributed. The repository
`.venv` reported old package metadata while importing checkout modules, and an
installed-only probe can differ from a checkout probe because Python uses
different import roots. The four opposers and Agent 5 independently confirmed
that the system install selected by the verified shell path matched the current
wheel, and the repo install scripts explicitly remove/reinstall/verify the
selected wheel. No completed install was shown to execute an older version.

**Decision: Not a bug on current evidence.** The stale-venv/source-shadowing
condition remains an operator diagnostic risk, not a validated installer
regression. Native Windows execution was unavailable. The missing post-install
verification in `install-online.ps1` is a separate hardening candidate, not
silently folded into this fix.

### H2 - Duplicate `This System` row

The stale-ID reproduction is valid: a trusted record with an obsolete local
ID and display name `This System` is restored as a non-local placeholder while
the current local context is also registered. The current projection preserves
the authoritative `is_local` and operational state, so the old row cannot be
opened or selected. The screenshot does not prove its exact persisted state,
and the model intentionally allows duplicate display names.

**Decision: Validated downgraded bug, P3.** The user-facing projection is
ambiguous when duplicate names occur. The smallest safe repair is display-only
disambiguation by stable ID for duplicate names; do not infer locality or delete
trusted records without provenance.

### Opposition synthesis

All four fallback opposers and the Agent 5 fallback wrote their own sections
and evidence. Their runtime results agree; the disagreement is classification
of the conditional duplicate, not the reproduction. No trust-boundary,
authorization, destructive-action, or code-execution bypass was found.

## Final Decision

H1: Not a bug on current evidence.

H2: Validated downgraded P3 conditional UI/state bug; transition to Mode A for
stable-ID disambiguation. Fixed in Mode A by appending stable IDs only when
All Systems display names collide. The stale row remains non-operational and
trusted records are not deleted.

Mode A follow-up: the online PowerShell installer now performs the same
cwd-independent installed-version/module-path verification as the shell and
local PowerShell install paths. This is diagnostic hardening, not a reversal
of the H1 verdict.
