# remote/ — pdc-remote 2.0.0

Drive `pdc-reset.sh` on the PDC VM from this Windows workstation, with
checkpoints, guidance and independent verification.

**Full write-up: [docs/PDC-REMOTE-RESET.md](../docs/PDC-REMOTE-RESET.md)**

## Quick start

```bash
.\pdc-remote.ps1 help
```

First time through, in order: `config` → `probe` → `enable-ssh` → `wait-ssh` →
`enroll` → `ssh-test` → `doctor`. Then `plan`, `dry-run`, `reset`.

Every command explains itself before it acts and writes a transcript to `logs\`.
Any `KEY=VALUE` argument overrides configuration for that one run:

```bash
.\pdc-remote.ps1 logs SVC=public-api N=500
```

## Requirements

Nothing to install. Windows PowerShell 5.1 plus `ssh.exe`, `scp.exe`,
`ssh-keygen.exe` and `curl.exe`, all of which ship with Windows 10/11. No WSL,
no Git Bash, no make.

You do need SSH reachable on the VM (`.\pdc-remote.ps1 enable-ssh` prints the
console commands) and the VM account in the `docker` group. Passwordless sudo is
*not* required — see `.\pdc-remote.ps1 sudo-help`.

## Layout

| Path | |
|---|---|
| `pdc-remote.ps1` | the driver, 36 commands |
| `lib\ui.ps1` | console UI, checkpoints, render, ssh/scp/curl plumbing |
| `lib\txt\` | the long-form guidance the commands print |
| `pdc-remote.env.example` | config template (`config` writes the real one) |
| `.state\`, `logs\` | checkpoints, tokens, transcripts — all gitignored |

## Editing notes

**ASCII only.** Em-dashes and smart quotes break PowerShell 5.1 parsing.

**PowerShell 5.1, not 7.** No `&&`/`||` chain operators, no ternary, no `??`,
no `?.`. Use `if`/`else` and explicit `$null -eq` checks.

**Remote commands are base64-wrapped.** 5.1 does not escape embedded double
quotes when handing arguments to a native exe, so any remote command containing
quotes, pipes or `||` reaches bash mangled. `Get-RemotePayload` encodes it to
`[A-Za-z0-9+/=]` and pipes it through `base64 -d | bash` on the VM. Build remote
commands as plain strings and let that helper handle them.

**Never redirect a native exe's stderr with `2>&1` on the PowerShell side.**
5.1 wraps each line in an ErrorRecord and reports failure even on exit 0. Merge
on the Linux side instead — `Invoke-Remote -Merge` does exactly that.

**Long prose belongs in `lib\txt\*.txt`**, printed via `Invoke-Render <name>
@{KEY=value}` with `@KEY@` placeholders, so the text reaches the console exactly
as written.
