# AuraLAN roadmap

AuraLAN 1.0 established a local-first network inventory and monitoring foundation. This roadmap is problem-oriented rather than a promise of dates.

## 1.x priorities

### Broader Linux compatibility

AuraLAN should work well outside the maintainer's primary Raspberry Pi/Debian environment.

- Verify clean installs on current Debian and Ubuntu releases.
- Exercise client Wi-Fi, Ethernet-only and mixed-interface hosts.
- Add regression fixtures only when they are generic and portable.
- Improve diagnostics when optional local providers are unavailable.

### Better device identity

Identity remains evidence-based and conservative.

- Add signatures for device families supported by standards-based local evidence.
- Improve model-family normalization without turning vendor hints into unsupported exact-model claims.
- Expand regression coverage for multi-interface devices and randomized/private MAC addresses.
- Improve explanations for why a particular identity was selected.

### Activity Center

Make local change history more useful without turning AuraLAN into an intrusion-detection product.

- Improve grouping for related changes.
- Improve filtering and empty states.
- Keep richer activity local unless a future integration is explicitly designed with privacy controls.

### Integrations

- Expand Home Assistant examples and validation.
- Explore additional aggregate, privacy-preserving local integrations.
- Keep cloud services optional and out of the core runtime.

### Accessibility and interface quality

- Keyboard navigation and focus-state audit.
- Screen-reader labeling audit.
- High-contrast review.
- Continue phone/tablet/desktop browser sanity coverage.

## Good contribution areas

Contributors do not need to understand the full discovery pipeline. Useful first contributions include:

- documentation corrections and installation notes for another Linux distribution
- a regression test for a real, evidence-backed device identity
- accessibility improvements with a reproducible before/after case
- frontend tests for an existing behavior
- clearer diagnostics for one optional provider

Look for issues labeled **good first issue** or **help wanted**.

## Design constraints

AuraLAN will remain:

- local-first
- evidence-based
- useful without a cloud account
- free of mandatory telemetry or remote runtime assets
- conservative about device identity
- explicit about actions that modify anything

Larger changes that alter these properties should start as an issue before implementation.
