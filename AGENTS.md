# AGENTS.md

## Cursor Cloud specific instructions

### Repository state

This repository (`Linkedin-Updater`) is currently a stub. As of this writing it
contains only `README.md` and this `AGENTS.md` — there is **no application code,
no dependency manifest (e.g. `package.json`, `requirements.txt`,
`pyproject.toml`, `go.mod`), no tests, and no build tooling**.

Because of that there is nothing to install, lint, build, test, or run yet.

### Toolchains available on the VM

The base image already provides common runtimes, so once real code + a
dependency manifest are added, no extra system setup should be needed:

- Node `v22.14.0` / npm `10.9.7`
- Python `3.12.3` / pip `24.0`
- Go `1.22.2`
- OpenJDK `21`

### Update script

The configured startup update script auto-detects a dependency manifest and
installs dependencies only if one exists (npm / pip / uv). While the repo is a
stub the script is effectively a no-op, and it will start doing useful work
automatically once a manifest is committed. If you add a project that uses a
different package manager (e.g. pnpm, yarn, poetry), update the startup script
accordingly.
