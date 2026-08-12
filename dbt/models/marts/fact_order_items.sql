select
    event_id as order_item_id,
    order_id,
    customer_id,
    product_id,
    quantity,
    price as unit_price,
    line_total,
    country,
    event_timestamp
from {{ ref('int_purchases') }}
