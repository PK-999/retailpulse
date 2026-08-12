select
    product_id,
    min(event_timestamp) as first_seen_at,
    max(event_timestamp) as last_seen_at,
    avg(price) filter (where price is not null) as average_price
from {{ ref('stg_events') }}
where product_id is not null
group by product_id
