select *

from {{ ref('weather_daily_observations') }}

where
    station_id is null
    or station_name is null
    or observation_date is null
    or min_temp_c is null
    or max_temp_c is null
    or mean_temp_c is null
    or temperature_range_c is null
    or precipitation_mm is null
    or is_wet_day is null
    or min_temp_c > mean_temp_c
    or mean_temp_c > max_temp_c
    or abs(mean_temp_c - ((min_temp_c + max_temp_c) / 2.0)) > 0.01
    or temperature_range_c < 0
    or abs(temperature_range_c - (max_temp_c - min_temp_c)) > 0.01
    or precipitation_mm < 0
    or is_wet_day <> (precipitation_mm > 0)
