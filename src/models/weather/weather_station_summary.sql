-- One aggregate row per synthetic station across the observation period.
{{ config(materialized = 'table') }}

select
    station_id,
    station_name,
    min(observation_date) as first_observation_date,
    max(observation_date) as last_observation_date,
    count(*) as observation_days,
    round(avg(mean_temp_c), 2) as average_mean_temp_c,
    min(min_temp_c) as period_min_temp_c,
    max(max_temp_c) as period_max_temp_c,
    round(sum(precipitation_mm), 2) as total_precipitation_mm,
    sum(case when is_wet_day then 1 else 0 end) as wet_days

from {{ ref('weather_daily_observations') }}

group by station_id, station_name
