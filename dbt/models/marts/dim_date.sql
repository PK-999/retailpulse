with bounds as (
    select
        min(cast(event_timestamp as date)) as start_date,
        max(cast(event_timestamp as date)) as end_date
    from {{ ref('stg_events') }}
)

select
    cast(date_day as date) as date_key,
    year(date_day) as calendar_year,
    quarter(date_day) as calendar_quarter,
    month(date_day) as calendar_month,
    day(date_day) as calendar_day,
    dayname(date_day) as day_name
from bounds, generate_series(start_date, end_date, interval 1 day) as dates (date_day)
