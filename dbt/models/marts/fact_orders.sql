select
    order_id,
    max(customer_id) as customer_id,
    min(event_timestamp) as order_timestamp,
    max(country) as country,
    sum(quantity) as units,
    sum(line_total) as order_total
from {{ ref('int_purchases') }}
group by order_id
