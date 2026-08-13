{% snapshot product_snapshot %}
{{ config(
    target_schema=(target.schema if target.type == 'databricks' else 'snapshots'),
    unique_key='product_id',
    strategy='check',
    check_cols=['average_price']
) }}
{% if target.type == 'databricks' %}
{{ config(
    file_format='delta',
    location_root=env_var(
        'RETAILPULSE_DBT_GOLD_LOCATION',
        'abfss://retailpulse@stretailpulsedevrp999.dfs.core.windows.net/gold/dbt'
    )
) }}
{% endif %}
select * from {{ ref('dim_product') }}
{% endsnapshot %}
