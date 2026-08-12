{{ config(materialized='incremental', unique_key='order_date') }}

with changed_dates as (
    select distinct cast(order_timestamp as date) as order_date
    from {{ ref('fact_orders') }}
    {% if is_incremental() %}
        where ingestion_timestamp > (
            select coalesce(max(target.ingestion_timestamp), cast('1900-01-01' as timestamp))
            from {{ this }} as target
        )
    {% endif %}
)

select
    cast(orders.order_timestamp as date) as order_date,
    count(*) as orders,
    sum(orders.units) as units,
    sum(orders.order_total) as revenue,
    avg(orders.order_total) as average_order_value,
    max(orders.ingestion_timestamp) as ingestion_timestamp
from {{ ref('fact_orders') }} as orders
inner join changed_dates on cast(orders.order_timestamp as date) = changed_dates.order_date
group by cast(orders.order_timestamp as date)
