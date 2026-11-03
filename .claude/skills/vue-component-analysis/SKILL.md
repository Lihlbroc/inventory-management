---
name: vue-component-analysis
description: Analyze Vue 3 component structure and suggest performance and code-reuse optimizations. Use when asked to review, audit or optimize Vue components, find duplicated logic/markup/CSS, reduce component size, or improve rendering performance in client/src. Read-only; produces a prioritized report and does not edit files.
---

# Vue Component Analysis

Produces a prioritized, evidence-backed report of performance and code-reuse opportunities in the Vue components under `client/src`. **This skill only analyzes.** Do not edit `.vue` files while running it. Per CLAUDE.md, any follow-up that creates or significantly modifies a `.vue` file must be delegated to the `vue-expert` subagent.

## Workflow

1. **Scope.** Use the path the user named. Default to `client/src`. If they named one component, scan just that file but still scan `client/src` for duplicates elsewhere.
2. **Scan.** Run the structure scanner (Python 3, standard library only; `-I` keeps it from importing stray modules from the working directory):
   ```bash
   python -I .claude/skills/vue-component-analysis/scripts/analyze_vue.py client/src
   ```
   Add `--json` for machine-readable output. It reports per-file size, API style, computed/watch counts, rule-based findings, and duplicates across files.
3. **Verify every candidate.** The scanner is a regex heuristic that surfaces *candidates*. Open the code (`Read`) for each one before reporting it. Drop false positives. Never report a finding you haven't read.
4. **Look beyond the scanner** at the top few components by size (see checklist below), since structure problems such as mixed concerns are not regex-detectable.
5. **Report** in the format below.

## What to look for

### Performance
- **Function calls in the template that loop or filter** (`getByStatus('x').length`): they re-run on every render. Move to a `computed` (or one computed returning a grouped object).
- **`v-for` keys:** missing `:key`, or `:key="index"` on lists that can reorder/insert/filter (breaks DOM reuse and local state). Index keys are fine for static, never-reordered lists, so say so rather than flagging blindly.
- **`v-if` on the same element as `v-for`:** filter in a computed instead.
- **Heavy derived state in `ref`s updated by watchers:** prefer `computed`.
- **`deep: true` watchers** and watching whole objects when one field matters.
- **Redundant fetching:** several watchers or `onMounted` calls triggering overlapping requests, or the same endpoint loaded by multiple components with no shared cache.
- **Large lists** (hundreds of rows) rendered fully: suggest pagination or virtual scrolling only if the data can actually be that large. Check `server/data/` for real sizes first.
- **Whole-page components:** a 1000+ line view re-renders everything on any reactive change. Splitting into child components with narrow props localizes updates.

### Code reuse
- **Duplicated CSS** across components (the scanner lists identical declaration blocks): candidates for shared classes or a base component (e.g. one `BaseModal` instead of per-modal overlay/container/header/close-button CSS).
- **Duplicated template markup**, such as repeated card, badge, table or modal structure: extract a component with props/slots.
- **Duplicated functions** across files (formatters, translators, `handleBlur`): move to `client/src/utils/` or a composable in `client/src/composables/`.
- **Repeated fetch + loading + error logic:** extract a composable.
- **Mixed concerns** in one component (data fetching, formatting, layout, modal state): split along those lines.

## Project conventions to respect

- Stack: Vue 3 Composition API + Vite. The codebase mixes `setup()` and `<script setup>`. Recommend matching the surrounding file instead of a blanket migration.
- Shared state lives in `client/src/composables/` (`useFilters`, `useI18n`, `useAuth`). Prefer extending these over new global state.
- Design system: slate/gray palette, custom SVG charts, no emojis in UI. Suggestions must not change visual output.
- Filters (time, warehouse, category, status) flow through `client/src/api.js`. Do not suggest changing API contracts, and state requirements for the backend instead.
- Use `:key` with a stable id (`sku`, `month`, `id`), never the index, in any code you suggest.

## Report format

Start with a 2-3 sentence summary and the scan table (size/API/computed/watch per file). Then list findings, **highest impact first**:

```
### <number>. <short title>   [Impact: high|medium|low] [Effort: S|M|L] [Type: performance|reuse]
- Where: path/File.vue:123 (and other locations)
- Problem: what is wrong, as observed in the code
- Suggestion: the concrete change (small snippet if it clarifies)
- Risk: what could break / how to verify
```

Ranking guide: duplicated code across many files, or work repeated on every render of a large list, ranks high. A single cheap call in a small component ranks low or is omitted.

End with **Recommended order of work** (3-5 steps, quick wins first) and offer to hand the chosen items to `vue-expert`. Be explicit about anything you did not verify.

## Do not

- Edit, create or delete files.
- Report scanner output unverified, or inflate the list with trivial nits. A short, accurate report beats a long one.
- Recommend memoization, virtual scrolling or a state library without evidence that the data size or update rate justifies it.
