# Contributing to yaatv

yaatv is a small CLI focused on YouTube-ready audio videos. The best way to help is to send clear bug reports or cohesive pull requests.

- [Opening an issue](#opening-an-issue)
- [Coordinating work on an issue](#coordinating-work-on-an-issue)
- [Your first contribution](#your-first-contribution)
- [Development setup](#development-setup)
- [Pull requests](#pull-requests)
- [AI contributions](#ai-contributions)
- [Versioning](#versioning)
- [Coding style](#coding-style)

## Opening an issue

Use GitHub Issues for bug reports and feature requests. Before opening one:

- Search existing issues first.
- Reproduce the issue on the latest release or current `main`.
- Report one problem or feature request per issue.
- Use the issue template and do not remove sections that apply.

For bug reports, include:

- The exact command you ran.
- The full terminal output as text, not a screenshot.
- Your OS and `yaatv --version`.
- `ffmpeg -version` and `ffprobe -version` when media conversion is involved.
- A small reproducible example when possible.

For feature requests, include:

- The problem you are trying to solve.
- The behavior you want.
- Why existing options do not cover it.

Do not share private audio, artwork, credentials, tokens, or copyrighted material you do not have permission to publish.

## Coordinating work on an issue

Before starting work on an issue, it is best to leave a comment saying you plan to work on it. This lets others know and helps prevent overlapping effort. Check open pull requests for work that may already address the issue. If work overlaps, coordinate with the other contributor or a maintainer.

If an assigned issue has no update or draft pull request for 7 days, a maintainer may make it available to others.

## Your first contribution

Getting started with a contribution follows a straightforward flow:

1. **Find an issue**: Browse [good first issues](https://github.com/yaatv/yaatv/labels/good%20first%20issue), and check existing pull requests for duplicate work. Before starting, it is best to comment that you plan to work on the issue so others can avoid overlapping effort.
2. **Fork and clone**:
   ```sh
   git clone https://github.com/<your-username>/yaatv.git
   cd yaatv
   ```
3. **Create a virtual environment**:
   ```sh
   python -m venv .venv
   ```
   Activate it:
   - Windows: `.\.venv\Scripts\activate`
   - Linux / macOS: `source .venv/bin/activate`
4. **Install development dependencies**:
   ```sh
   python -m pip install -e ".[dev]"
   ```
5. **Create a topic branch**:
   ```sh
   git checkout -b fix/brief-description
   ```
6. **Run targeted tests during development**:
   ```sh
   python -m pytest -k <test_name_or_keyword>
   ```
7. **Run project checks before submitting**:
   ```sh
   python scripts/check.py
   ```
8. **Submit a pull request**: Push your branch to your fork and open a pull request against `main`.

## Development setup

Python 3.11 or newer is required.

```sh
python -m pip install -e ".[dev]"
```

You can run all checks with one command:

```sh
python scripts/check.py
```

Or run fast checks only (linter, typechecker, unit tests):

```sh
python scripts/check.py --fast
```

For more details on tests and architecture:
- See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for a map of the codebase and media processing pipeline.
- See [docs/TESTING.md](docs/TESTING.md) for test suite organization, running single tests, and platform considerations.

Some tests require FFmpeg and FFprobe to be available.

## Pull requests

Before opening a PR:

- Check open pull requests to ensure someone else hasn't already submitted a fix for the same issue.
- Keep the PR focused on one issue or one change. Related tests and documentation belong with that change; ask a maintainer before including unrelated scope.
- For substantial architecture changes or new CLI commands, consider opening an issue or discussion first to align on direction before writing code.
- Add or update tests for behavior changes.
- Update README or docs when user-facing behavior changes.
- Open a draft PR while work is in progress. When it is ready, the PR author must mark it "Ready for review" and contributors should request a maintainer review.
- Do not commit generated build outputs, local media files, virtual environments, secrets, or machine-specific files.
- Feel free to add your GitHub username to `CONTRIBUTORS` in your PR.
- Run the checks you can run locally (`python scripts/check.py --fast`).
 
If a PR is unclear, untested, or unrelated to yaatv, maintainers will provide feedback to help shape or split it.

## AI contributions

AI tools may assist with contributions under the [AI Contribution Policy](.AI_POLICY/README.md).

### Merging and credit

Pull requests are squash-merged into `main` to keep commit history clean. Your original git authorship is always preserved on the squash commit. If multiple people collaborated on a PR, maintainers will add `Co-authored-by:` trailers so everyone receives credit.

### Resolving merge conflicts

If changes land on `main` that conflict with your PR branch:

1. Fetch the latest `main` from upstream:
   ```sh
   git fetch upstream main
   ```
2. Merge upstream `main` into your topic branch:
   ```sh
   git merge upstream/main
   ```
3. Reconcile the conflicting files, run checks (`python scripts/check.py --fast`), and push the resolution to your fork. Avoid closing and reopening duplicate pull requests.

## Versioning

yaatv uses `major.minor.patch` versions.
Here, "minor" means the middle version component; a small change can still be a
patch release such as `0.7.1`.

### Before 1.0

While yaatv is before 1.0, the major version stays `0`.

- Patch: bug fixes, docs, tests, release workflow fixes, internal hardening, and narrowly scoped corrections to existing workflows that preserve normal defaults and output profiles. This can include better recovery from an exceptional failure or additive metadata.
- Minor: new features or CLI flags, new workflows, changes to normal user-facing behavior, breaking changes, output-format or profile changes, broader output contract changes, release packaging changes that alter install or download behavior, or removed behavior.
- Major: reserved for the first stable release.

### After 1.0

After stable 1.0:

- Patch: bug fixes, docs, tests, release workflow fixes, and internal hardening that do not change user-facing behavior.
- Minor: new user-facing CLI flags, new supported workflows, release packaging changes that alter install or download behavior, or other backward-compatible behavior changes.
- Major: breaking CLI changes, output contract changes, or removed behavior.

### Keeping versions in sync

Set the package version in `yaatv/__init__.py` (`__version__`), the single source of truth.
`pyproject.toml` reads `yaatv.__version__` dynamically through setuptools; it does not
store a second version. The README publishing example uses the placeholder
`v<version>` rather than a separately maintained version number.

The release workflow imports `yaatv.__version__` and refuses a tag build when the
tag's version does not match it.

### Windows Defender and SmartScreen false positives

Because standalone release binaries are generated with PyInstaller without a commercial code-signing certificate, Windows Defender or SmartScreen may occasionally flag new releases until download reputation accumulates.

If a new Windows release triggers false positives, submit `yaatv.exe` for analysis:

- [Microsoft Security Intelligence file submission](https://www.microsoft.com/en-us/wdsi/filesubmission)
- [VirusTotal file scan](https://www.virustotal.com/gui/home/upload)

### Tags

For a release, tag the commit as `v<__version__>`, using the value in
`yaatv/__init__.py`. If `__version__` is `0.5.1`, tag that commit as `v0.5.1`.
This keeps the release history clean and the CI build trigger working.

## Coding style

- Follow the existing code style.
- Keep code readable and boring.
- Prefer standard library tools unless a dependency is already used by the project.
- Handle missing files, invalid media, and FFmpeg failures with errors that say what failed.
- Keep CLI output useful for people who are not Python developers.
- Use type hints for new Python code.
- Keep tests small and deterministic.
