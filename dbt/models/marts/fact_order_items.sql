{{ config(materialized='incremental', unique_key='order_item_id') }}

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
