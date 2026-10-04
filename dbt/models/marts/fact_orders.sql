{{ config(materialized='incremental', unique_key='order_id') }}
{{ configure_gold() }}

{% if target.type == 'databricks' %}
with changed_orders as (
    select orders.order_id
    from {{ source('silver', 'orders') }} as orders
    {% if is_incremental() %}
        where orders.ingestion_timestamp >= (
            select coalesce(max(target.ingestion_timestamp), cast('1900-01-01' as timestamp))
            from {{ this }} as target
        )
    {% endif %}

    union

    select items.order_id
    from {{ source('silver', 'order_items') }} as items
    {% if is_incremental() %}
        where items.ingestion_timestamp >= (
            select coalesce(max(target.ingestion_timestamp), cast('1900-01-01' as timestamp))
            from {{ this }} as target
        )
    {% endif %}
)

select
    orders.order_id,
    orders.customer_id,
    orders.order_timestamp,
    orders.country,
    sum(items.quantity) as units,
    sum(items.quantity * items.unit_price) as order_total,
    greatest(max(items.ingestion_timestamp), orders.ingestion_timestamp) as ingestion_timestamp
from {{ source('silver', 'orders') }} as orders
inner join changed_orders on orders.order_id = changed_orders.order_id
inner join {{ source('silver', 'order_items') }} as items on orders.order_id = items.order_id
group by
    orders.order_id,
    orders.customer_id,
    orders.order_timestamp,
    orders.country,
    orders.ingestion_timestamp
{% else %}
    with changed_orders as (
        select distinct order_id
        from {{ ref('int_purchases') }}
        {% if is_incremental() %}
            where ingestion_timestamp >= (
                select coalesce(max(target.ingestion_timestamp), cast('1900-01-01' as timestamp))
                from {{ this }} as target
            )
        {% endif %}
    )

    select
        purchases.order_id,
        max(purchases.customer_id) as customer_id,
        min(purchases.event_timestamp) as order_timestamp,
        max(purchases.country) as country,
        sum(purchases.quantity) as units,
        sum(purchases.line_total) as order_total,
        max(purchases.ingestion_timestamp) as ingestion_timestamp
    from {{ ref('int_purchases') }} as purchases
    inner join changed_orders on purchases.order_id = changed_orders.order_id
    group by purchases.order_id
{% endif %}

{% if is_incremental() %}
    except
    select
        order_id,
        customer_id,
        order_timestamp,
        country,
        units,
        order_total,
        ingestion_timestamp
    from {{ this }}
{% endif %}
