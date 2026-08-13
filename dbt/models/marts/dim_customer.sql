{% if target.type == 'databricks' %}
{{ config(
    file_format='delta',
    location_root=env_var(
        'RETAILPULSE_DBT_GOLD_LOCATION',
        'abfss://retailpulse@stretailpulsedevrp999.dfs.core.windows.net/gold/dbt'
    )
) }}

select
    customers.customer_id,
    customers.country,
    coalesce(min(orders.order_timestamp), customers.ingestion_timestamp) as first_seen_at,
    coalesce(max(orders.order_timestamp), customers.ingestion_timestamp) as last_seen_at
from {{ source('silver', 'customers') }} as customers
left join {{ source('silver', 'orders') }} as orders
    on customers.customer_id = orders.customer_id
group by customers.customer_id, customers.country, customers.ingestion_timestamp
{% else %}
    select
        customer_id,
        max(country) as country,
        min(event_timestamp) as first_seen_at,
        max(event_timestamp) as last_seen_at
    from {{ ref('stg_events') }}
    where customer_id is not null
    group by customer_id
{% endif %}
