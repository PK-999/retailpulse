select
    {% if target.type == 'databricks' %}
    cast(event_id as string) as event_id,
    cast(event_type as string) as event_type,
    cast(customer_id as string) as customer_id,
    cast(product_id as string) as product_id,
    cast(order_id as string) as order_id,
    cast(country as string) as country,
    {% else %}
        cast(event_id as varchar) as event_id,
        cast(event_type as varchar) as event_type,
        cast(customer_id as varchar) as customer_id,
        cast(product_id as varchar) as product_id,
        cast(order_id as varchar) as order_id,
        cast(country as varchar) as country,
    {% endif %}
    cast(quantity as integer) as quantity,
    cast(price as decimal(12, 2)) as price,
    cast(event_timestamp as timestamp) as event_timestamp,
    cast(ingestion_timestamp as timestamp) as ingestion_timestamp
{% if target.type == 'databricks' %}
from {{ source('silver', 'streaming_events') }}
{% else %}
    from read_json_auto(
        '{{ env_var("RETAILPULSE_DBT_DATA_DIR", "data") }}/silver/events.jsonl',
        format = 'newline_delimited'
    )
{% endif %}
