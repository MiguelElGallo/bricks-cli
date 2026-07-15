-- One typed row per synthetic station and observation date.
{{ config(materialized = 'view') }}

with typed as (

    select
        cast(station_id as string) as station_id,
        cast(station_name as string) as station_name,
        cast(observation_date as date) as observation_date,
        cast(min_temp_c as double) as min_temp_c,
        cast(max_temp_c as double) as max_temp_c,
        cast(precipitation_mm as double) as precipitation_mm

    from {{ ref('weather_daily_seed') }}

)

select
    concat(station_id, '__', date_format(observation_date, 'yyyy-MM-dd'))
        as weather_observation_key,
    station_id,
    station_name,
    observation_date,
    min_temp_c,
    max_temp_c,
    round((min_temp_c + max_temp_c) / 2.0, 2) as mean_temp_c,
    round(max_temp_c - min_temp_c, 2) as temperature_range_c,
    precipitation_mm,
    precipitation_mm > 0 as is_wet_day

from typed
