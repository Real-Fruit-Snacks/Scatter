# Scatter

Concurrent SSH executor for 100+ hosts with asyncio + AsyncSSH, Typer CLI, YAML inventory, retries, and rich output.

**Available as standalone binary (no Python required) or portable tarball for Linux Ubuntu systems.**

## Features
- Concurrent SSH to 100+ hosts (`--limit` controls max parallelism)
- Per-host auth (key/password) and per-host commands
- Command precedence: host.command > --command-file > CLI command
- Retries with backoff, timeouts, and optional PTY
- Rich table, progress bar, summaries, and JSONL logging
- Works transparently with proxychains
- Multiple distribution options: binary, tarball, or Python package

## Installation

Choose the installation method that best fits your needs:

| Method | Python Required | Size | Best For |
|--------|----------------|------|----------|
| **Standalone Binary** | ❌ No | ~20MB | End users, production systems |
| **Portable Tarball** | ✅ 3.10+ | ~6MB | Developers, source code access |
| **Python Package** | ✅ 3.10+ | varies | Python developers, existing environments |

### Option 1: Standalone Binary (Recommended)

**No Python installation required!** Download a pre-built standalone executable from the [GitHub Releases](https://github.com/Real-Fruit-Snacks/Scatter/releases) page.

1. Download the Linux executable:
   - `scatter-X.X.X-linux-x86_64` for Ubuntu/Linux x86_64

2. Make it executable and run:
   ```bash
   chmod +x scatter-*-linux-x86_64
   ./scatter-*-linux-x86_64 --help
   ```

3. Optionally, install system-wide:
   ```bash
   sudo mv scatter-*-linux-x86_64 /usr/local/bin/scatter
   scatter --help
   ```

### Option 2: Portable Tarball

**Python 3.10+ required.** For users who want all the source files and dependencies in a single package.

1. Download the portable tarball:
   - `scatter-X.X.X-linux-x86_64-portable.tar.gz`

2. Extract and run:
   ```bash
   tar -xzf scatter-*-portable.tar.gz
   cd scatter-*-portable/
   ./scatter.sh --help
   ```

3. Or use Python directly:
   ```bash
   python3 run_scatter.py --help
   ```

### Option 3: Install with pip (for Python developers)

Install with pip (local project):

```bash
pip install .
```

Or for development (editable):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Once installed, a top-level console command `scatter` is available.

### Option 4: Offline/air-gapped installation

We publish prebuilt wheel bundles for Linux systems with different Python versions in GitHub Releases.

- Asset naming: `wheels-Linux-py<MAJOR.MINOR>.zip`
  - Examples: `wheels-Linux-py3.10.zip`, `wheels-Linux-py3.11.zip`, `wheels-Linux-py3.12.zip`

1) Download the zip matching your Python version (e.g., `wheels-Linux-py3.11.zip`).
2) Extract to a folder, e.g., `./wheelhouse`.
3) Install offline:

```bash
pip install --no-index --find-links ./wheelhouse scatter
```

This installs `scatter` and all required dependencies without network access.

## Quick start

1) If not installed globally, activate your virtual environment from above.

2) Create an inventory file (YAML):

```yaml
# inventory.yaml
defaults:
  username: ubuntu
  port: 22
  connect_timeout: 10
  known_hosts: off  # enforced: StrictHostKeyChecking=no & no known_hosts file
  pty: false
  # Optional global auth defaults (can be overridden per-host)
  identity: ~/.ssh/id_rsa
  # password: "env:SSH_GLOBAL_PASSWORD"  # or inline (discouraged)
hosts:
  - host: 192.0.2.10
    username: ec2-user
    identity: ~/.ssh/special_id
    command: "uname -a"
    tags: [web]
  - host: server2.example.com
    password: "env:SERVER2_PASSWORD"
    command: "uptime"
```

3) Run a command across all hosts (precedence: host.command > --command-file > CLI command):

```bash
scatter run "uname -a" --inventory inventory.yaml --limit 50
```

Or read the command from a file:

```bash
echo 'uname -a; date -u' > cmd.sh
scatter run --command-file ./cmd.sh --inventory inventory.yaml --limit 50
```

- `--limit` controls max concurrency
- `--identity` sets the private key file to use
- Use `--known-hosts off` to skip verification (not recommended for production)

### Trying multiple usernames or passwords (optional)

You can provide lists for credential attempts:

```
# users.txt
admin
ubuntu
ec2-user

# passwords.txt
hunter2
changeme123
```

Examples:

```bash
# Try key-based auth with each username (if --identity or agent is available)
scatter run "id" --inventory inventory.yaml --identity ~/.ssh/id_ed25519 --username-list users.txt

# Try each (username, password) pair
scatter run "hostname" --inventory inventory.yaml --username-list users.txt --password-list passwords.txt

# Try password list for a single username
scatter run "uptime" --inventory inventory.yaml --username admin --password-list passwords.txt
```

When lists are provided, the tool first attempts key-based auth per username (if a key or agent is available),
then falls back to password attempts over the Cartesian product of usernames and passwords. Respect local laws and only use on systems you are authorized to access.

4) CLI help (excerpt):

```text
Usage: scatter run [OPTIONS] [COMMAND]

Run COMMAND across all hosts in the inventory.

Arguments
  command      [COMMAND]  Shell command to run on all hosts (overridden by per-host 'command' in inventory) [default: None]

Options
  --inventory PATH                 Path to inventory YAML [default: inventory.yaml]
  --limit INT                      Max concurrent SSH sessions [default: 50]
  --identity PATH                  Path to private key file to use [default: None]
  --username TEXT                  Override SSH username for all hosts [default: None]
  --username-list PATH             Path to a file with candidate usernames (one per line) [default: None]
  --port INT                       Override SSH port for all hosts [default: None]
  --known-hosts [off|strict]       Host key verification policy (off disables host key checking) [default: off]
  --connect-timeout FLOAT          SSH connect timeout (seconds) [default: 10.0]
  --pty / --no-pty                 Request a PTY (xterm) for the command [default: no-pty]
  --command-timeout FLOAT          Command timeout (seconds) [default: None]
  --retry-attempts INT             Connection retry attempts per host [1..5] [default: 1]
  --password-list PATH             Path to a file with candidate passwords (one per line) [default: None]
  --show-output                    Print full stdout per host after summary table [default: off]
  --show-stderr                    Also print stderr blocks for failed hosts [default: off]
  --save-dir PATH                  Directory to save per-host stdout/stderr files [default: None]
  --progress / --no-progress       Show progress bar and stream per-host results [default: progress]
  --dry-run                        Preview target hosts, auth, and commands without executing
  --command-file PATH              Read command text from a file (used if host has no 'command') [default: None]
  -v, --verbose INTEGER            Increase verbosity (repeat for more detail) [default: 0]
  --quiet                          Minimal output: only summary and exit code [default: off]
  --log-file PATH                  Write JSON lines log with per-host results [default: None]
  --help                           Show this message and exit.
```

5) Run tests (requires pytest):

```bash
pytest -q
```

## Inventory reference
- defaults (applies to all hosts unless overridden):
  - username: SSH user
  - port: SSH port (default 22)
  - connect_timeout: seconds (default 10)
  - known_hosts: off | strict (off disables host key checking)
  - pty: true | false (request PTY)
  - identity: private key path (e.g., ~/.ssh/id_rsa)
  - password: string or env:VAR_NAME
- hosts (array of host entries):
  - host: hostname or IP
  - username, port, pty, identity, password: per-host overrides
  - command: per-host command (string, folded >, or literal |)
  - tags: list of strings for targeting (future filters)

Precedence rules:
- Auth fields: host value > CLI option > defaults
- Command: host.command > --command-file > CLI command

Secrets via env:
- Use `password: env:MY_VAR` and export MY_VAR in your shell.

## Output options
- `--show-output`: print full stdout per host after the summary table
- `--show-stderr`: also print stderr blocks for failed hosts
- `--save-dir DIR`: save `host.stdout.txt` and `host.stderr.txt` files
- `--dry-run`: preview target set (host/user/port/auth/pty) and first line of the command
- `--progress/--no-progress`: show a progress bar and stream per-host results as they finish
- `-v/-vv`: increase verbosity (at `-vv`, show full outputs by default)
- `--quiet`: minimal output (summary only)
- `--log-file FILE`: write JSON lines log with per-host results

## Writing commands in YAML
You can provide long or multi-step commands per host in the inventory. Recommended patterns:

- Literal block scalar (runs lines as they appear; easiest to read for multi-step commands)

```yaml
hosts:
  - host: server1
    command: |
      set -e
      uname -a
      ls -latr | grep "abc"
      date -u
```

- Folded block scalar (visually wrapped in YAML, executed as a single line with spaces)

```yaml
hosts:
  - host: server1
    command: >
      uname -a; ls -latr | grep "abc"; date -u
```

- Inline string (escape quotes as needed)

```yaml
hosts:
  - host: server1
    command: "uname -a; ls -latr | grep \"abc\"; date -u"
```

Tips:
- Prefer `|` for multi-step scripts; add `set -e` to stop on the first failing command.
- Use spaces for indentation (no tabs).
- Quote paths with spaces or special characters as needed.

## Notes
- Supports per-host or global `identity` (private key path) and/or `password`. If both are provided, key auth is tried with password as fallback if the server allows it.
- Host key verification is disabled for speed/scale: equivalent to `-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null`.
- CLI paths for `--identity`, `--command-file`, `--save-dir`, and `--log-file` support `~` and environment variable expansion.

## Behavior and exit codes
- Succeeds (exit 0) only if all hosts report OK; otherwise exits 1.
- Summary shows Succeeded and Failed counts; failed hosts are listed with reasons.

## Using with proxychains
- Works out of the box: prefix your command, e.g. `proxychains -q scatter run ...`
- If your proxy is IPv4-only, ensure DNS is handled by proxychains (proxy_dns) and targets resolve to IPv4.

## Compatibility
- **Target Platform**: Linux Ubuntu (x86_64)
- **Supported Python**: 3.10+ (when using wheel installation)
- **Optimizations**: Uses `uvloop` for improved asyncio performance on Linux
