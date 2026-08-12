with inventory as (
    select
        product_id,
        sum(case when event_type = 'inventory_update' then quantity else 0 end) as units_updated,
        max(case when event_type = 'inventory_update' then event_timestamp end) as last_inventory_update
    from {{ ref('stg_events') }}
    where product_id is not null
    group by product_id
)

select
    product_id,
    units_updated,
    last_inventory_update,
    date_diff('minute', last_inventory_update, current_timestamp) as freshness_minutes,
    case
        when last_inventory_update is null then 'unknown'
        when date_diff('minute', last_inventory_update, current_timestamp) > 60 then 'stale'
        else 'healthy'
    end as inventory_status
from inventory
