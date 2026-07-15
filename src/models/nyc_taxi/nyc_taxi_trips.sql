-- nyc_taxi_trips
--
-- "Move the seed into a table." This model reads the committed
-- samples.nyctaxi.trips extract and materializes a real Delta table in Unity
-- Catalog, adding light typing and one derived column.
{{ config(materialized = 'table') }}

with source as (

    select * from {{ ref('nyc_taxi_trips_seed') }}

)

select
    cast(tpep_pickup_datetime  as timestamp)            as pickup_at,
    cast(tpep_dropoff_datetime as timestamp)            as dropoff_at,
    cast(trip_distance         as double)               as trip_distance,
    cast(fare_amount           as double)               as fare_amount,
    cast(pickup_zip            as int)                  as pickup_zip,
    cast(dropoff_zip           as int)                  as dropoff_zip,
    round(
        timestampdiff(SECOND, tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0,
        2
    )                                                   as trip_minutes

from source
