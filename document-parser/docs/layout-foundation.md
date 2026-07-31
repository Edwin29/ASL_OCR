# Layout Foundation

## Current Scope

This milestone adds the first layout reconstruction layer after OCR.

- OCR tokens are grouped into `LayoutLine` objects.
- Lines are grouped into `LayoutBlock` objects.
- TEXT-only Page IR now emits one TEXT node per layout line, not one node per OCR token.
- Each emitted TEXT node keeps line provenance through a `layout` object.

## Current Reading Order

The current resolver is intentionally conservative:

1. Sort blocks top-to-bottom, then left-to-right.
2. Sort lines inside each block top-to-bottom, then left-to-right.
3. Emit a flat `reading_order` list of TEXT node IDs.

This is enough for one-column fixture tests and early OCR adapter integration. It is not the final EBS reading-order resolver.

## Not Yet Implemented

- robust one-column/two-column container detection
- box-shaped problem container ordering
- header/footer ordering rules
- reading-order graph edges
- layout debug overlay images
- table-aware ownership of OCR tokens
- math span splitting inside a line

## Verified Behavior

Unit tests now cover:

- same-baseline tokens becoming one line
- vertical gaps creating separate blocks
- top-to-bottom reading order
- TEXT-only Page IR using line nodes

