# StegnoZ research site design

The supplied `stegnoz_platform_researcher_console.html` is the visual source. Its capsule animation, monochrome palette, Fraunces display type, Geist and Space Grotesk interface type, pill controls, cards, sidebar, and cockpit layout are retained. The fonts, Three.js, GSAP, and compiled Tailwind CSS are served locally. The implementation uses actual aggregate API results in place of the mockup's fixed metrics and unsupported telemetry claims.

## Landing page

`/` uses the supplied hero and four-stage card layout to describe ingestion, clinical preservation, patient linkage, and policy verification. Its question bar passes a supported question to `/dashboard`. The capsule can be dimmed; its animation becomes static under reduced-motion preferences.

## Researcher console

`/dashboard` has a persistent navigation rail, question input, explicit filters, cohort metrics, condition and age charts, a breakdown table, saved cohorts, CSV export, and methodology. Counts and the minimum group size come from API responses. Demo and sanitized-release modes are visibly labeled. Small breakdowns are withheld and repeated-query inference remains a documented limitation.

Narrow layouts stack the navigation and data panels; focus and interaction states remain visible.
