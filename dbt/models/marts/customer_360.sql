select
    c.customer_id,
    c.country,
    c.first_seen_at,
    c.last_seen_at,
    count(o.order_id) as lifetime_orders,
    coalesce(sum(o.order_total), 0) as lifetime_value
from {{ ref('dim_customer') }} as c
left join {{ ref('fact_orders') }} as o on c.customer_id = o.customer_id
group by c.customer_id, c.country, c.first_seen_at, c.last_seen_at
