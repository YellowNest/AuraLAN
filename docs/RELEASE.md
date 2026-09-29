# Release checklist

AuraLAN releases are cut deliberately. A green application test suite is not enough by itself.

## Code and privacy

- [ ] `python3 scripts/validate-release.py` passes.
- [ ] `python3 scripts/audit-history.py` passes.
- [ ] Backend tests pass.
- [ ] Frontend syntax and unit tests pass.
- [ ] No real household/device identifiers are present in the current tree.
- [ ] No credentials, private keys, tokens, runtime databases, logs or captures are tracked.
- [ ] Example addresses use documentation ranges.
- [ ] Installation-specific paths are either documented defaults or runtime overrides.

## Portability

- [ ] No conventional interface name is assumed by production discovery.
- [ ] Missing optional providers degrade gracefully.
- [ ] At least one Debian/Raspberry Pi test host is verified.
- [ ] At least one non-Raspberry-Pi Linux host is verified before calling a release broadly portable.

## Product

- [ ] Version is finalized in `project.json` and synchronized fallbacks.
- [ ] Changelog has a dated release section.
- [ ] README matches current behavior.
- [ ] Installation/configuration docs match the shipped service files.
- [ ] Verified product screenshots contain no private local identifiers.
- [ ] A public-use license has been selected.

## Publishing

- [ ] Historical personal fixtures have been removed from any history that will become public.
- [ ] CI is green on the exact release commit.
- [ ] Release tag is created from the exact reviewed commit.
- [ ] GitHub repository description/topics/social preview match the release.
