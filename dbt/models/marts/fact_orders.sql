{{ config(materialized='incremental', unique_key='order_id') }}

with changed_orders as (
    select distinct order_id
    from {{ ref('int_purchases') }}
    {% if is_incremental() %}
        where ingestion_timestamp > (
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
