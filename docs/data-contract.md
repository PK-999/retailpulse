# Event contract v1

All topics use UTF-8 JSON. Required fields are `event_id` (UUID), `event_type`,
timezone-aware `event_timestamp`, and `schema_version=1`. Product-centric events require
`product_id`; purchase and inventory events require a positive `quantity`; prices must be
non-negative. Unknown fields are rejected to surface contract drift early.

Purchase events also require `order_id` and `price`, so accepted purchases can contribute to
Gold revenue without silent omissions. The local processor rejects payloads on the wrong topic.
New Silver tables retain finite, nonnegative prices as Decimal text. Gold casts unit prices to
`DECIMAL(12,2)` (round half up) before multiplication; out-of-range Gold values fail the build
while Silver retains the original event. Required product/order IDs cannot be whitespace.
Quantity is a strict JSON integer in INT32 range; purchase/inventory quantities must be positive.
The schema version must be integer `1`, not a boolean or string. Event time must be an ISO
timestamp with a timezone; epoch numbers and numeric strings are rejected.

Python and Spark use the same model source. The Stage 7 upload bundles that source and worker
helper into a standalone notebook; executors require Pydantic, not a workspace package import.
Spark keeps aware UTC datetimes so executor OS timezone cannot alter the instant.

An existing Delta table with decimal price type is preserved. A valid event whose price cannot
be represented exactly in that legacy type enters quarantine as `SILVER_REPRESENTATION`.
Use a new string-price table for unrestricted contract precision. Records more than 30 minutes
older than ingestion time are retained as `LATE_EVENT`; this is a lateness policy, not stateful
Spark watermark eviction. Duplicate event IDs remain in Bronze and are excluded from Silver.

Routing:

| Topic | Events |
|---|---|
| `customer-events` | product_view, search, add_to_cart |
| `order-events` | checkout, purchase, payment |
| `inventory-events` | inventory_update |
