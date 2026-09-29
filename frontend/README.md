# Frontend checks

The UI uses browser-native ES modules and has no runtime Node dependency. `frontend/` is the single canonical production asset directory mounted by FastAPI; there is no parallel `dist/` or manual-copy deployment step. When Node 24+ is available for development, run the small pure-module test suite with:

```bash
node --test tests/data.test.mjs
```

Browser visual checks should cover 390×844, 430×932, 768×1024, and 1440×900 in both themes. The production host does not require Node or a browser test runner.
