select
    customer_id,
    max(country) as country,
    min(event_timestamp) as first_seen_at,
    max(event_timestamp) as last_seen_at
from {{ ref('stg_events') }}
where customer_id is not null
group by customer_id
