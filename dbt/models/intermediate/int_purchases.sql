select
    event_id,
    order_id,
    customer_id,
    product_id,
    quantity,
    price,
    country,
    event_timestamp,
    ingestion_timestamp,
    quantity * price as line_total
from {{ ref('stg_events') }}
where event_type = 'purchase'
