# Data sources & provenance

Every number has both a value and a source. The source tells you how directly it
was observed; confidence and coverage tell you how complete it is.

| Label | Meaning |
| --- | --- |
| Provider native | Dated buckets returned by a provider usage/billing API. Usually authoritative. |
| Provider reported | A provider measurement collected in a snapshot. |
| Snapshot-derived | A delta or history derived from successive saved provider readings. |
| Hermes observed | Workload seen by Hermes. Authoritative for what passed through Hermes, not necessarily for the whole account. |
| Estimated | Computed from observations, such as token pricing or a forecast. |
| Billing history | Provider-native monetary buckets for dated periods. |
| Corroborating | A compatible secondary observation used to check the authoritative value. |
| Partial | Some relevant workload was observed or priced, but not all. |
| Unavailable | No safe value can be produced. |

For reconciled analytics, source priority is provider-native, then
snapshot-derived, Hermes-observed, and estimated. A lower-priority source is not
blindly added to a higher-priority description of the same activity.

Material disagreement is surfaced when corroborating capacity differs by more
than 15 percentage points or activity differs by more than 50% relatively. A
corroborating source more than six hours fresher can flag the authoritative
reading as stale. Disagreement and staleness lower confidence.

Use **Why this number?** and **Data sources & quality** on the Usage page to see
the source, window, reset, confidence, corroboration, and warnings for a value.
