{{ configure_gold() }}
{% if target.type == 'databricks' %}

select
    products.product_id,
    coalesce(min(orders.order_timestamp), products.ingestion_timestamp) as first_seen_at,
    coalesce(max(orders.order_timestamp), products.ingestion_timestamp) as last_seen_at,
    cast(products.unit_price as decimal(12, 2)) as average_price
from {{ source('silver', 'products') }} as products
left join {{ source('silver', 'order_items') }} as items
    on products.product_id = items.product_id
left join {{ source('silver', 'orders') }} as orders
    on items.order_id = orders.order_id
group by products.product_id, products.unit_price, products.ingestion_timestamp
{% else %}
    select
        product_id,
        min(event_timestamp) as first_seen_at,
        max(event_timestamp) as last_seen_at,
        avg(price) as average_price
    from {{ ref('stg_events') }}
    where product_id is not null
    group by product_id
{% endif %}
