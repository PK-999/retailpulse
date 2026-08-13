{% if target.type == 'databricks' %}
{{ config(
    file_format='delta',
    location_root=env_var(
        'RETAILPULSE_DBT_GOLD_LOCATION',
        'abfss://retailpulse@stretailpulsedevrp999.dfs.core.windows.net/gold/dbt'
    )
) }}
{% endif %}

with bounds as (
    select
        min(cast(order_timestamp as date)) as start_date,
        max(cast(order_timestamp as date)) as end_date
    from {{ ref('fact_orders') }}
)

{% if target.type == 'databricks' %}
select
    date_day as date_key,
    year(date_day) as calendar_year,
    quarter(date_day) as calendar_quarter,
    month(date_day) as calendar_month,
    day(date_day) as calendar_day,
    date_format(date_day, 'EEEE') as day_name
from bounds
lateral view explode(sequence(start_date, end_date, interval 1 day)) dates as date_day
{% else %}
    select
        cast(date_day as date) as date_key,
        year(date_day) as calendar_year,
        quarter(date_day) as calendar_quarter,
        month(date_day) as calendar_month,
        day(date_day) as calendar_day,
        dayname(date_day) as day_name
    from bounds, generate_series(start_date, end_date, interval 1 day) as dates (date_day)
{% endif %}
