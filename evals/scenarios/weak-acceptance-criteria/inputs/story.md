# Epic Story Pack — PROJ-200 Invoice Export

## Epic PROJ-200: Invoice export improvements

Business goal: reduce support tickets about missing or incorrect invoice
exports.

## Story PROJ-201: Improve invoice export reliability (target story)

As an accountant I want invoice exports to be reliable so that I stop losing
time on failed downloads.

Description:
Exports currently fail sometimes for large date ranges. The export should be
improved so that it works better for big customers. Pricing team still needs
to decide whether refunded invoices are included.

Acceptance criteria:
1. Exports work correctly for large date ranges.
2. The system handles errors gracefully.
3. Export performance is acceptable for big customers.
4. Refunded invoices are handled appropriately.
