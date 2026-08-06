# Tooling appendix — THIS machine, current stack

Machine-specific gotchas earned the hard way. Ignore freely on other
machines; verify versions before trusting on this one. (Windows 11,
PowerShell 5.1, Python via `py`, Claude Code as lead, Codex CLI as
reviewer, Inno Setup, MS Word installed.)

## Codex CLI as the adversarial reviewer

- Invoke as `codex exec --sandbox read-only -C . "<prompt>"` from a
  BACKGROUND shell with `< /dev/null` (REQUIRED — it hangs waiting on
  stdin otherwise) and a hard timeout; capture stdout to a file (output
  runs to hundreds of KB; read the TAIL for the verdict).
- Give it: the diff range, the design doc pointer, priority surfaces
  ranked by risk, "construct concrete counterexamples", and demand an
  explicit APPROVED/FINDINGS verdict with clean surfaces stated.
- Fix loop: fix at the root, pin each finding with the reviewer's own
  counterexample, FALSIFY the pins (revert fixes -> tests must fail),
  then a NARROWING re-confirmation pass scoped to only the fixed
  surfaces.
- Codex has its own usage quota; if it dies mid-gate, record gate state
  + a boundary commit and schedule the confirm pass after reset.
- Its sandbox may lack a writable temp dir — expect some fixture-driven
  tests to be replayed as in-memory probes; that is acceptable evidence
  when the probes are independent.

## Word COM for docx -> PDF

`powershell -File script.ps1` HANGS in the agent harness when the script
drives Word COM. Run the COM sequence inside a `Start-Job` runspace
inline instead (~2 s): open doc read-only, `SaveAs([ref]$pdf, [ref]17)`,
quit, release the COM object, `Wait-Job -Timeout`.

## Shell traps

- `pytest | tail` swallows the exit code — assert `${PIPESTATUS[0]}`
  (bash) or run unpiped. A "green" suite behind a pipe hid a real
  failure once.
- PowerShell 5.1: no `&&`/`||`, no ternary; `Set-Content` defaults to
  ANSI (pass `-Encoding utf8`); heredoc-equivalents are here-strings
  with the closing `'@` at column 0.
- Bash heredocs with apostrophes inside `$(cat <<'EOF' ...)` command
  substitutions can break quoting — prefer the file-Write tool for long
  content, then reference the file.

## Python / Qt

- Suite must pass `python -m pytest` AND `python -O -m pytest`; no
  load-bearing asserts anywhere in production code.
- PySide6 headless tests: `QT_QPA_PLATFORM=offscreen` set BEFORE any Qt
  import.
- Qt traps that cost real time: `QGraphicsItemGroup` delegates
  `setSelected` to the group (children unselectable); `QTreeWidget`
  `itemChanged` -> rebuilding the tree in the slot is a use-after-free;
  `indexWidget` returns BOTH permanent cell widgets and transient
  editors (same slot); keyboard shortcuts fire without committing an
  open cell editor — flush explicitly before reading tables.
- A top-level package named `io/` shadows the stdlib; name it `fileio/`.

## Packaging (PyInstaller + Inno Setup)

- PyInstaller freezes a SCRIPT (no `-m`): a two-line `launch.py` calling
  the package's real entry keeps frozen and source launches identical.
- Deferred imports need explicit `hiddenimports`; NEVER exclude a
  library your dependencies import lazily (the numpy-under-ezdxf trap:
  bundle builds, dies on first use). Pin the non-exclusion by test.
- The frozen bundle gets a `--selftest` (headless, raise-not-assert,
  exercises every lazy dependency + bundled assets) run as a build gate.
- Inno: AppId generated ONCE and frozen; `Root: HKA` for associations
  under per-user/admin dual installs; quote `"%1"`; ISCC at
  `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.
- Doc-freshness release gates check file CONTENT (the PDF's own text
  states the version), never mtimes.

## Repo hygiene

- Project lives OUTSIDE OneDrive (sync churn on venvs/build outputs has
  crashed it).
- Version literal single-sourced in code; manual/build/installer all
  READ it; a suite-level pin turns the suite red on bump until generated
  docs are rebuilt.
