# Public Release Review

Review date: 2026-11-15. Status: **NOT READY for remote publication** until the
owner reviews the cleaned-history candidate and approves the remaining actions.
No source, tests, dependencies, runtime fixtures, or container configuration were
edited by this release preparation. Concurrent user edits to three Python files
are preserved separately and excluded from the release commit and candidate.
No remote update or visibility change was authorized or performed.

## Security Findings

- Gitleaks 8.30.1 reported no credential matches in the original 23-commit
  history or the working tree. Its official Linux binary was checksum-verified.
  Complementary checks covered Git object contents, commit identities, local
  refs/reflogs, historical filenames, personal paths, private-key markers,
  credential URLs, and provider-token patterns, including unreachable blobs.
- A private author/committer name and email appear in 22 development commits.
  Their values are deliberately omitted from this report. The owner approved
  replacing both with the existing public GitHub name/noreply address in a
  separate local candidate, not rewriting the original history or remote.
- The owner confirmed that `sandbox/secrets/password.txt` is fictional test
  data and has never been a real password. It is a required experiment fixture
  and was preserved. No real credential requiring rotation was identified.
- Machine-specific home paths occur in historical documentation and the
  injected runtime fixture. Current objective documentation now uses relative
  paths. The injection was not edited because that would change trial behavior;
  review its disclosed path before publication and configure it for each checkout.
- One local JSON result exists outside tracked history and remains Git-ignored.
  Results can contain personal paths or the dummy marker and must not be
  published by copying the entire workspace.
- No tracked notebooks, credential/configuration dumps, or large datasets were
  found. The largest historical tracked blob is approximately 34 KiB.

These are scan results, not proof that every possible secret is detectable.
No credentials were tested against external services. Remote issues, Actions
logs, releases, external clones, and hosting-provider caches were not audited.

## Files and Presentation

- Rewrote `README.md` with purpose, architecture, installation, accurate CLI
  examples, fixture setup, recording behavior, tests, limitations, license
  status, repository structure, and a final Current Development Status section.
- Removed assistant workflow files `inst.md` and `PROGRESS.md` from the current
  tree. The README retains verified project status without the assistant diary,
  local environment details, or automated workflow instructions.
- Removed redundant `.gitkeep` files from populated source/test directories;
  retained `sandbox/output/.gitkeep`, which preserves a required empty directory.
- Updated `.gitignore` for local assistant notes, editor state, private-key
  formats, and Git recovery bundles. Existing result/output/credential ignores
  remain in place. Ignore rules do not remove previously committed data.
- Corrected `goal.txt` and `gateway/policy.md` to describe the actual local paths,
  implemented policy, and current experimental limitations.
- Retained all legitimate source, tests, dependencies, fixtures, and existing
  empty Docker placeholders. No license or attribution was removed or invented.

## History Cleanup and Safety

A complete pre-cleanup Git bundle was created and verified outside the
repository. It deliberately contains the original private metadata and must
remain private. The original checkout and its existing commits are retained.
The private handoff also preserves the user's uncommitted Python-file changes.

The owner approved a separate local candidate using `git-filter-repo` v2.47.0.
The cleanup removes `inst.md` and `PROGRESS.md` from past trees and maps the
private commit identity to the owner's existing public GitHub identity. Private
home prefixes in historical objective documentation are replaced with an
explicit project-root placeholder; runtime fixtures and source are not rewritten.
Legitimate commit messages, attribution, dates, and application/fixture blobs
are preserved. Commit identifiers change as a consequence, not to disguise
development history. Verification must check both identities and file history,
not merely the latest working tree.

The original remote advertises only `main`, with no tags or pull-request refs.
Local `refs/codex/...` recovery metadata is not a public branch and must not be
included in a mirror push. The candidate must have no writable remote configured.

Do not overwrite remote history until the owner explicitly approves the exact
candidate and coordinates with collaborators. A subsequent update should target
only the reviewed branch, use a checked lease, and avoid a blanket mirror push.
Other clones and cached copies may retain old metadata after rewriting; see
[GitHub's sensitive-data removal guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## Cleaned-Candidate Results

The separate candidate was verified against all 24 commits present at cleanup.
All 20 protected current file paths and every historical source/fixture blob
match the original committed versions. Commit messages and timestamps are
unchanged. The removed assistant files are absent from every candidate tree;
the old private name/email and original private commit objects are absent from
all candidate Git objects, not only from the visible log. The candidate has no
configured remote and passes the same 256 tests. Its history scan reported no
credential matches.

One original GitHub-signed commit lost its signature during rewriting. Rewritten
history must not be presented as carrying the old verified signatures. The
private handoff includes the original bundle, identity mapping, source manifests,
scan reports, and verification summary; none belongs in the public repository.

## Verification and Existing Limitations

- All 256 existing tests passed on 2026-11-15 using Python 3.13.12, MCP SDK 2.3.0,
  Ollama Python 0.6.3, pytest 9.1.1, and pytest-asyncio 1.4.0. Agent tests mock
  Ollama; real MCP integration tests use temporary directories and dummy values.
- Release changes are restricted to documentation, ignore rules, and redundant
  empty tracking files. Candidate source/test/dependency/fixture/container blobs
  must match the original committed checkout. User source work remains unstaged.
- The gateway is not an OS sandbox. Direct MCP access intentionally reaches the
  broader sandbox, including fictional secrets. Path validation does not provide
  protection against concurrent host filesystem changes between check and use.
- Gateway INFO logging can include unescaped untrusted strings if an embedding
  application enables it. The CLI suppresses that duplicate logger. This was
  reported rather than changed under the no-source-modification constraint.
- Batch execution, aggregate metrics, automated leakage checks, gateway-disabled
  trials, and working Docker isolation are not implemented. Recorded trials are
  not a published benchmark or evidence of universal injection resistance.
- Dependencies are not fully locked. Dependency advisory scanning and fresh
  model/GPU verification were not part of this data/history cleanup.

## Owner Actions Before Publishing

1. Review the separate candidate, identity mapping, history scan, and unchanged
   source/fixture checks. Review the machine-specific injected path as a public
   disclosure and portability limitation.
2. Explicitly approve any remote history update. Keep the original bundle and
   old checkout private; coordinate collaborator re-cloning and cache cleanup
   where needed. Recheck remote refs before any update.
3. Choose a license if open-source reuse is intended. No license currently
   exists, so this cleanup does not claim the project is open-source licensed.
4. Suggested GitHub description: "Local MCP prompt-injection experiment with
   a default-deny tool gateway and per-trial JSON records."
   Suggested topics: `model-context-protocol`, `prompt-injection`, `llm-security`,
   `ollama`, `python`. These are recommendations; remote metadata is unchanged.
5. Change repository visibility only after the reviewed history is installed and
   verified on the remote. Neither cleanup approval nor this review authorizes
   publishing, force-pushing, or changing visibility.
