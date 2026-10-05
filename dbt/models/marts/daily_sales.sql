{{ config(
    materialized='incremental',
    unique_key='order_date',
    pre_hook='{{ prune_empty_sales_dates() }}'
) }}
{{ configure_gold() }}

-- Current dates alone cannot identify the former date of a corrected order.
-- Compare complete Gold aggregates, then write only dates whose rows differ.
select
    cast(orders.order_timestamp as date) as order_date,
    count(*) as orders,
    sum(orders.units) as units,
    sum(orders.order_total) as revenue,
    avg(orders.order_total) as average_order_value,
    max(orders.ingestion_timestamp) as ingestion_timestamp
from {{ ref('fact_orders') }} as orders
group by cast(orders.order_timestamp as date)

{% if is_incremental() %}
    except
    select
        order_date,
        orders,
        units,
        revenue,
        average_order_value,
        ingestion_timestamp
    from {{ this }}
{% endif %}
