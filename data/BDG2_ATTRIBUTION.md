# BDG2 sample subset attribution

Source: Building Data Genome Project 2, [BUDS Lab repository](https://github.com/buds-lab/building-data-genome-project-2), cleaned electricity meter file `data/meters/cleaned/electricity_cleaned.csv`.

Attribution: Miller, Clayton; Kathirgamanathan, Anjukan; Picchetti, Bianca; Arjunan, Pandarasamy; Park, June Young; Nagy, Zoltan; Raftery, Paul; Hobson, Brodie W.; Shi, Zixiao; Meggers, Forrest. “The Building Data Genome Project 2, energy meter data from the ASHRAE Great Energy Predictor III competition.” *Scientific Data* 7, 368 (2020). https://doi.org/10.1038/s41597-020-00712-x

The source repository's `LICENSE` specifies Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0): https://creativecommons.org/licenses/by-sa/4.0/ . Preserve attribution and license terms when redistributing this adapted subset.

Adaptation: one electricity meter column, `Panther_education_Teofila`, selected because metadata identifies it as Education and marks electricity as available. All rows without a reading were removed; timestamps and kWh values are retained. The resulting `bdg2_education_sample.csv` contains 14,156 measured hourly records from 2016-05-01 19:00 through 2017-12-31 23:00 (local `US/Eastern` source clock, with source DST gaps/duplicates not normalized). Original metadata reports 8,723.3 m² floor area. The dataset is a non-residential sample from the Panther site, not an Indian building or institution.
