with expected as (

    select
        station_id,
        min(observation_date) as first_observation_date,
        max(observation_date) as last_observation_date,
        count(*) as observation_days,
        round(avg(mean_temp_c), 2) as average_mean_temp_c,
        min(min_temp_c) as period_min_temp_c,
        max(max_temp_c) as period_max_temp_c,
        sum(case when is_wet_day then 1 else 0 end) as wet_days,
        round(sum(precipitation_mm), 2) as total_precipitation_mm,
        count(distinct station_name) as station_names

    from {{ ref('weather_daily_observations') }}

    group by station_id

),

actual as (

    select * from {{ ref('weather_station_summary') }}

)

select coalesce(actual.station_id, expected.station_id) as station_id

from actual

full outer join expected
    on actual.station_id = expected.station_id

where
    actual.station_id is null
    or expected.station_id is null
    or actual.station_name is null
    or actual.first_observation_date is null
    or actual.last_observation_date is null
    or actual.observation_days is null
    or actual.average_mean_temp_c is null
    or actual.period_min_temp_c is null
    or actual.period_max_temp_c is null
    or actual.total_precipitation_mm is null
    or actual.wet_days is null
    or expected.station_names <> 1
    or actual.first_observation_date > actual.last_observation_date
    or actual.observation_days <= 0
    or actual.wet_days < 0
    or actual.wet_days > actual.observation_days
    or actual.total_precipitation_mm < 0
    or actual.average_mean_temp_c < actual.period_min_temp_c
    or actual.average_mean_temp_c > actual.period_max_temp_c
    or actual.observation_days <> expected.observation_days
    or actual.first_observation_date <> expected.first_observation_date
    or actual.last_observation_date <> expected.last_observation_date
    or abs(actual.average_mean_temp_c - expected.average_mean_temp_c) > 0.01
    or abs(actual.period_min_temp_c - expected.period_min_temp_c) > 0.01
    or abs(actual.period_max_temp_c - expected.period_max_temp_c) > 0.01
    or actual.wet_days <> expected.wet_days
    or abs(actual.total_precipitation_mm - expected.total_precipitation_mm) > 0.01
