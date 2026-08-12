select * from {{ ref('fact_order_items') }}
where quantity <= 0
