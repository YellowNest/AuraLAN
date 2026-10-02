# Contributing to AuraLAN

AuraLAN is a local-first network console. Keep changes focused, evidence-based, portable, and testable.

Start with [Installation](docs/INSTALLATION.md), [Configuration](docs/CONFIGURATION.md), and [Compatibility](docs/COMPATIBILITY.md).

## Your first contribution

You do not need to understand the whole discovery pipeline before contributing.

1. Pick an open issue labeled **good first issue** or **help wanted**.
2. Comment on the issue before starting substantial work so effort is not duplicated.
3. Fork AuraLAN and branch from `dev`.
4. Keep the change limited to the issue unless a closely related fix is required.
5. Add or update tests that prove the behavior.
6. Open the pull request against `dev`, not `main`.

Good first contributions include documentation/compatibility notes, focused frontend tests, accessibility fixes, and evidence-backed device-family recognition.

If an issue is underspecified, ask in the issue rather than guessing. Maintainer review should explain the reason for requested changes, not only reject them.

## Branch model

- `main` is the release-ready branch and should remain deployable.
- `dev` is the persistent integration branch for reviewed development work.
- Feature/fix branches should normally target `dev`.
- A release promotion from `dev` to `main` must pass the full CI and release checks.

## Development rules

- Do not add mandatory cloud dependencies, telemetry, remote fonts, CDN scripts, or runtime third-party assets.
- Do not assume hostnames, private IP ranges, usernames, installation paths, or interface names from one deployment.
- Preserve the read-first security model. New host/network write operations require explicit authentication, authorization, CSRF protection, auditability, validation, rollback, and a separate design review.
- Keep `project.json` as the canonical product/version metadata source.
- Do not bump the version for ordinary feature/fix commits. Release preparation owns the version change, changelog date, and Git tag.
- Add user-facing changes to `CHANGELOG.md` under `Unreleased`.

## Device identity and icons

Device identification must be conservative. OUI data identifies an organization, not an exact model.

- Broad category inference belongs in `backend/app/discovery/device_inference.py`.
- Product-family icon selection belongs in `device_icon_key()` and should use explicit local evidence such as resolved vendor, service type, advertised model/family, or a user-owned alias.
- The backend `icon_key` is canonical. `frontend/js/device-icons.js` only provides compatibility fallbacks for older payloads.
- New icon keys must be added to the API contract, frontend key set, local icon library, and regression tests in the same change.
- Prefer a recognizable device-family pictogram over a generic smart-home glyph when the evidence is strong enough.
- Never infer a precise hardware model from a MAC prefix alone.

## UI

- Preserve the single canonical `@media(max-width:760px)` mobile layout block.
- Keep mobile form controls at 16px or larger to avoid iOS focus zoom.
- Keep assets local and usable in light/dark themes.
- English and Swedish translation keys must stay in parity.

## Tests

Backend:

```bash
cd backend
.venv/bin/python -m unittest discover -s tests -v
```

Frontend/unit checks:

```bash
node --test frontend/tests/*.test.mjs
```

Release validation:

```bash
python3 scripts/validate-release.py
```

Browser sanity check against a running local instance:

```bash
./scripts/test-ui.sh
```

A device-identity or icon PR should include at least one regression test that proves both the positive match and a safe fallback where practical.
