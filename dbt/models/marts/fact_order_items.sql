{{ config(materialized='incremental', unique_key='order_item_id') }}
{{ configure_gold() }}

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
    where greatest(items.ingestion_timestamp, orders.ingestion_timestamp) >= (
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
        where purchases.ingestion_timestamp >= (
            select coalesce(max(target.ingestion_timestamp), cast('1900-01-01' as timestamp))
            from {{ this }} as target
        )
    {% endif %}
{% endif %}

{% if is_incremental() %}
    -- Re-read the boundary for tied arrivals; matching rows produce no merge input.
    except
    select
        order_item_id,
        order_id,
        customer_id,
        product_id,
        quantity,
        unit_price,
        line_total,
        country,
        event_timestamp,
        ingestion_timestamp
    from {{ this }}
{% endif %}
