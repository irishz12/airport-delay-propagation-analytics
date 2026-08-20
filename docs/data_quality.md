# Data Quality Report

This report documents the quality checks performed on the 2024 BTS flight
extract and the reconstructed aircraft-rotation dataset. Results below were
measured from the 12 local source files and `rotation_links.csv`; no rows were
sampled.

## Summary

| Check | Result |
|---|---:|
| Monthly source files present | 12 of 12 |
| Flight rows | 7,079,061 |
| Date coverage | 2024-01-01 to 2024-12-31 |
| Required-field nulls | 0 |
| Full-row duplicates | 0 |
| Candidate flight-key duplicates | 0 |
| Invalid airport codes | 0 |
| Nonpositive distances | 0 |
| Valid rotation links | 6,725,770 of 7,058,909 (95.28%) |
| Valid links with missing calculation inputs | 0 |
| Valid links with a negative propagation estimate | 0 |

## Coverage by month

| Month | Rows |
|---|---:|
| January | 547,271 |
| February | 519,221 |
| March | 591,767 |
| April | 582,185 |
| May | 609,743 |
| June | 611,132 |
| July | 634,613 |
| August | 619,025 |
| September | 582,622 |
| October | 615,497 |
| November | 575,404 |
| December | 590,581 |
| **Total** | **7,079,061** |

All records fall within calendar year 2024. The download step also verifies
archive size and ZIP integrity before retaining the 29 selected source fields.

## Completeness

The schema-required fields—flight date, reporting airline, origin,
destination, scheduled departure and arrival times, cancellation flag,
diversion flag, and distance—contain no null values.

| Nullable field or group | Null rows | Interpretation |
|---|---:|---|
| `Tail_Number` | 20,152 | Excluded from rotation reconstruction because an aircraft cannot be linked |
| Flight number | 1 | Retained; flight number is nullable in the database schema |
| Departure time | 92,659 | Primarily unavailable for flights that did not depart normally |
| Arrival time | 97,854 | Primarily unavailable for flights that did not arrive normally |
| Arrival-delay metrics | 113,814 | Expected for cancelled or diverted flights |
| Actual elapsed time / air time | 113,814 | Expected for cancelled or diverted flights |
| Each BTS delay-cause field | 5,629,097 | Structurally expected; BTS populates these fields only for qualifying delayed flights |

The dataset contains 96,315 cancelled flights and 17,499 diverted flights.
These records are preserved for network and cancellation analysis but are not
treated as valid aircraft-rotation links when their movement cannot be
reconstructed reliably.

## Duplicate and domain checks

- No exact full-row duplicates were found.
- No duplicates were found for the candidate flight key
  (`FlightDate`, `Reporting_Airline`, flight number, `Origin`, `Dest`,
  `CRSDepTime`). The database intentionally does not enforce this as a unique
  constraint because it is a validation key rather than a guaranteed BTS
  natural key.
- All origin and destination values match the three-uppercase-letter IATA
  format used by this dataset.
- No records fall outside 2024, have nonpositive distance, or have negative
  `DepDelayMinutes`/`ArrDelayMinutes` values.

## Rotation-link validation

The rotation pipeline starts with the 7,058,909 rows that have a tail number.
Every row receives a `link_status`; excluded or suspicious links are retained
with a reason instead of being silently dropped.

| Link status | Rows |
|---|---:|
| `valid` | 6,725,770 |
| `excluded_airport_mismatch` | 113,033 |
| `excluded_prior_cancelled` | 76,116 |
| `suspicious_long_turnaround` | 53,212 |
| `excluded_current_cancelled` | 48,370 |
| `excluded_current_diverted` | 17,138 |
| `excluded_prior_diverted` | 15,790 |
| `excluded_no_prior_flight` | 6,112 |
| `invalid_negative_turnaround` | 2,355 |
| `suspicious_short_turnaround` | 1,013 |
| **Total** | **7,058,909** |

A valid link has complete scheduled and observed turnaround inputs. The
propagation formula is clipped at zero, and the measured valid-link output
contains no negative estimates.

## Quality rules in the pipeline

- Monthly downloads are resumable and checked against HTTP content length.
- ZIP CRC validation rejects corrupt archives before extraction.
- `usecols` enforces the expected 29-column source contract.
- PostgreSQL types and `NOT NULL` constraints protect core identifiers and
  scheduled-flight fields.
- Rotation ordering uses timezone-aware UTC timestamps rather than subtracting
  local airport clock times.
- Cancelled, diverted, airport-mismatched, missing-time, negative-turnaround,
  and implausible-turnaround links receive explicit statuses.

## Known limitations

- The checks validate the received BTS extract; they cannot verify facts that
  BTS did not publish or detect a correctly formatted but factually incorrect
  source value.
- Tail numbers can be missing or reused across carriers and codeshares.
- A cancelled flight can break the observed aircraft-movement chain.
- Delay-cause fields are BTS attributions, not independently verified ground
  truth.
- The dataset covers one calendar year, so the findings should not be treated
  as a long-term baseline without repeating the checks on additional years.
