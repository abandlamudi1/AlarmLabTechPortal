
| Date | Sprint | Wave | Streams | Models | Copilot rounds | CI re-fixes | PRs | Friction refs |
|------|--------|------|---------|--------|----------------|-------------|-----|---------------|
| 2026-05-13 | Sprint 5 | Wave 1 | 4 (A, B, C, D) | Sonnet×4 | 1 each | 0 | #85, #86, #87, #88 | new:Friction-1(module-level-IO-guard), new:Friction-2(Celery5-config-casing) |
| 2026-05-13 | Sprint 5 | Wave 2 | 5 (E, F, G, H, I) | Sonnet×5 | 1 each | 0 | #93, #94, #95, #96, #97 | new:F04(celery-task-autodiscovery), new:F05(crontab-implicit-wildcard), new:F06(schema-check-in-hot-path) |
| 2026-05-14 | Sprint 5 | Wave 3 | 1 (J) | Sonnet×1 | 1 | 0 | #102 | new:F07(wave-under-load), new:XSS-in-polling-JS |
| 2026-05-14 | Sprint 6 | Wave 1 | 7 (A, B, D, E, F, G, H) | Sonnet×5 + Haiku×2 | 1 each | 0 | #108, #112, #110, #111, #109, #113, #114 | new:F09(sh-c-exec), new:F10(exc-info-leak), new:F11(config-casing), watch:F08(XSS-innerHTML) |
| 2026-05-14 | Sprint 6 | Wave 2 | 1 (C) | Sonnet×1 | 1 | 0 | #117 | new:F12(over-parameterization), watch:F03 (no recurrence) |
| 2026-05-15 | Sprint 7 | Wave 1 | 3 (A, B, D — C dropped) | Sonnet×2 + Haiku×1 | 1 each | 0 | #128, #129, #130 | new:F13(adc-github-sdk-install), new:F14(inline-dup-vs-copilot), new:F15(yaml11-octal), resolved:F12 |
| 2026-05-15 | Sprint 8 | Wave 1 | 5 (A, B, C, D, E) | Sonnet×3 + Haiku×2 | 1 each | C×1 (UID mismatch) | #134, #135, #136, #137, #139 | new:F16(dockerfile-vs-reqdev), new:F17(uid-mismatch), new:F18(load-test-guards), new:F19(shim-at-wrong-layer), new:F20(url-cred-leak), zero:F12 |
| 2026-05-15 | Sprint Next | Wave 1 | 7 (A, B, C, D, F, G, H) | Sonnet×5 + Haiku×2 | 1 each | H×2 (.dockerignore scripts/ exclusion — pre-existing CI gap) | #140, #141, #142, #143, #144, #145, #146 | new:F21(legacy-path-idempotency), new:F22(minio-localhost), new:F23(logging-basicConfig-scope), new:F24(dockerignore-scripts-exclusion) |
