select
    cast(order_timestamp as date) as order_date,
    count(*) as orders,
    sum(units) as units,
    sum(order_total) as revenue,
    avg(order_total) as average_order_value
from {{ ref('fact_orders') }}
group by cast(order_timestamp as date)
