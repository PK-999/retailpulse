# Event contract v1

All topics use UTF-8 JSON. Required fields are `event_id` (UUID), `event_type`,
timezone-aware `event_timestamp`, and `schema_version=1`. Product-centric events require
`product_id`; purchase and inventory events require a positive `quantity`; prices must be
non-negative. Unknown fields are rejected to surface contract drift early.

Routing:

| Topic | Events |
|---|---|
| `customer-events` | product_view, search, add_to_cart |
| `order-events` | checkout, purchase, payment |
| `inventory-events` | inventory_update |
