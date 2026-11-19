# Migration notes

## Escape-route test (downgrade one step, check, come forward)

Running downgrade 53027269c641 -> 2c25fac5af3e, add gin index on metadata
current: 2c25fac5af3e
Running upgrade 2c25fac5af3e -> 53027269c641, add gin index on metadata

## History

2c25fac5af3e -> 53027269c641 (head), add gin index on metadata
<base> -> 2c25fac5af3e, create documents and pages
