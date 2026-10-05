{% snapshot product_snapshot %}
{{ config(
    target_schema=(target.schema if target.type == 'databricks' else 'snapshots'),
    unique_key='product_id',
    strategy='check',
    check_cols=['average_price']
) }}
{{ configure_gold() }}
select * from {{ ref('dim_product') }}
{% endsnapshot %}
