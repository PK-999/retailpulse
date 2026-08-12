select * from {{ ref('fact_orders') }}
where order_total < 0
