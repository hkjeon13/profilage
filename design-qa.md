# Design QA — Layout Rhythm Improvements

## Comparison target

- Source visual truth:
  - `docs/ui-audit-assets-2026-07-11/03-main-desktop-1440.png`
  - `docs/ui-audit-assets-2026-07-11/04-company-profile-desktop-1440.png`
- Implementation screenshots:
  - `docs/ui-audit-assets-2026-07-11/06-main-improved-desktop-1440.png`
  - `docs/ui-audit-assets-2026-07-11/07-company-profile-improved-desktop-1440.png`
  - `docs/ui-audit-assets-2026-07-11/08-main-improved-mobile-390.png`
  - `docs/ui-audit-assets-2026-07-11/09-company-profile-improved-mobile-390.png`
- Combined full-view evidence:
  - `docs/ui-audit-assets-2026-07-11/10-main-before-after.png`
  - `docs/ui-audit-assets-2026-07-11/11-profile-before-after.png`
- Viewports: 1440 × 1000 desktop, 390 × 844 mobile
- State: idle main page; LG전자 company profile; local compare list empty

## Findings

- No remaining P0/P1/P2 layout findings.
- The main search group now uses a wider 680px control, a bounded hero height, shared horizontal gutters, and tighter source-chip spacing.
- The company header is 356px high rather than the previous approximately 400px, with a more balanced identity/basic-information split.
- The profile section navigation has a visible current-section treatment and communicates it with `aria-current="location"`.
- Mobile profile content has no horizontal overflow at 390px. The comparison actions occupy one two-column row instead of compressing beside the heading.

## Required fidelity surfaces

- Fonts and typography: existing Inter/system stack, weights, hierarchy, and content copy retained. Mobile title wrapping remains readable.
- Spacing and layout rhythm: shared max-width/gutter/spacing tokens introduced; header, footer, main shell, and company canvas now share one horizontal system.
- Colors and visual tokens: existing palette, borders, shadows, and state colors retained. The active profile tab reuses the existing accent color.
- Image quality and asset fidelity: no raster imagery or new image assets are used by these screens; existing logo and chart rendering were preserved.
- Copy and content: product copy remains unchanged. The visible added-state label was shortened to `추가됨`, while the full accessible label remains `비교함에 추가됨`.

## Focused comparison evidence

- Company header: identity card and basic-information grid were inspected at readable scale in `11-profile-before-after.png`.
- Mobile action area: verified in `09-company-profile-improved-mobile-390.png`; both actions remain 44px high and do not overlap the heading.
- Additional crops were not needed because the relevant typography and controls are readable in the saved full-view images.

## Interaction and runtime checks

- Profile section link click updates `aria-current` to `location`.
- Desktop and mobile pages report `scrollWidth === viewport width` at 1440px and 390px.
- Browser console errors: none.
- Full automated suite: 120 passed, 1 third-party deprecation warning.

## Comparison history

### Iteration 1

- [P2] Mobile company-summary actions competed with the heading and compressed into narrow multiline controls.
- Fix: stacked the heading above a two-column action grid below 560px.
- Post-fix evidence: `09-company-profile-improved-mobile-390.png`; action container is 334px wide and 44px high with no page overflow.

### Iteration 2

- [P2] Company identity header remained approximately 408px high after the first token pass because the basic-information rows still controlled the stretched grid height.
- Fix: reduced basic-card padding and row padding while keeping 44px interactive targets unchanged.
- Post-fix evidence: `07-company-profile-improved-desktop-1440.png`; header height reduced to approximately 356px.

## Known state differences

- The local main page has an empty compare list while the deployed reference contained two saved companies; this is browser storage state, not layout drift.
- The local profile did not have an OpenAI key, so the summary card shows its supported error state. Header, navigation, action, and responsive layout comparisons remain valid.

## Follow-up polish

- [P3] A future pass can add scroll-driven active-section updates; this change currently updates the active state on navigation clicks.

final result: passed
