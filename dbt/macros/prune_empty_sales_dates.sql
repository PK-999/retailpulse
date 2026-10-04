{% macro prune_empty_sales_dates() %}
    {% if is_incremental() %}
        delete from {{ this }} as sales
        where not exists (
            select 1
            from {{ ref('fact_orders') }} as orders
            where sales.order_date = cast(orders.order_timestamp as date)
        )
    {% endif %}
{% endmacro %}
