{% snapshot product_snapshot %}
{{ config(target_schema='snapshots', unique_key='product_id', strategy='check', check_cols=['average_price']) }}
select * from {{ ref('dim_product') }}
{% endsnapshot %}
