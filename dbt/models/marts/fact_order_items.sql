{{ config(materialized='incremental', unique_key='order_item_id') }}
{% if target.type == 'databricks' %}
{{ config(
    incremental_strategy='merge',
    file_format='delta',
    location_root=env_var(
        'RETAILPULSE_DBT_GOLD_LOCATION',
        'abfss://retailpulse@stretailpulsedevrp999.dfs.core.windows.net/gold/dbt'
    )
) }}
{% endif %}

{% if target.type == 'databricks' %}
select
    items._record_hash as order_item_id,
    items.order_id,
    orders.customer_id,
    items.product_id,
    items.quantity,
    items.unit_price,
    items.quantity * items.unit_price as line_total,
    orders.country,
    orders.order_timestamp as event_timestamp,
    greatest(items.ingestion_timestamp, orders.ingestion_timestamp) as ingestion_timestamp
from {{ source('silver', 'order_items') }} as items
inner join {{ source('silver', 'orders') }} as orders on items.order_id = orders.order_id
{% if is_incremental() %}
    where greatest(items.ingestion_timestamp, orders.ingestion_timestamp) > (
        select coalesce(max(target.ingestion_timestamp), cast('1900-01-01' as timestamp))
        from {{ this }} as target
    )
{% endif %}
{% else %}
    select
        purchases.event_id as order_item_id,
        purchases.order_id,
        purchases.customer_id,
        purchases.product_id,
        purchases.quantity,
        purchases.price as unit_price,
        purchases.line_total,
        purchases.country,
        purchases.event_timestamp,
        purchases.ingestion_timestamp
    from {{ ref('int_purchases') }} as purchases
    {% if is_incremental() %}
        where purchases.ingestion_timestamp > (
            select coalesce(max(target.ingestion_timestamp), cast('1900-01-01' as timestamp))
            from {{ this }} as target
        )
    {% endif %}
{% endif %}
