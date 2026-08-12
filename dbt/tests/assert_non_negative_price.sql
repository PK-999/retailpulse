select * from {{ ref('fact_order_items') }}
where unit_price < 0
