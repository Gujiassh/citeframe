# Mixed-workspace UI test scope

[`v5d-mixed-workspace-primary.spec.ts`](../../../../apps/web/e2e/v5d-mixed-workspace-primary.spec.ts) exercises PDF, image, and Markdown asset lists, selected-scope Quick Chat and Research requests, citation opening, unavailable sources, and horizontal overflow at desktop 1440×1000 and mobile 390×844 viewports.

It uses deterministic fixtures and mocked BFF responses. Its screenshots and JSON results describe UI regression checks; they do not establish live API/Worker integration, model answer quality, or production deployment readiness. A live mixed-workspace check requires a running application and its corresponding test state.

See the [evaluation guide](../../../development/evaluation.md) for evidence scope and reproducibility, and the [workspace guide](../../../guides/workspaces.md) for current product usage.
