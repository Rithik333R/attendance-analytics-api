
@'
# DECISIONS.md

1. **Indexes.** I created a unique index on `employees.emp_code` to prevent duplicate employee codes, and a unique compound index on `attendance_logs.emp_code` and `date` to allow only one attendance record per employee per day. I also use a date-and-employee index to support attendance queries. I would consider an index on `joined_on` for larger employee datasets, but would check query plans before adding it.

2. **Punch-in race.** Both requests may initially find no attendance record. The unique compound index is the final safeguard: one insert succeeds and the other hits a duplicate-key error. The API should return success for the winner and a conflict response for the other request.

3. **Ties.** Employees with equal total late minutes receive the same rank through MongoDB's `$rank`. Results are then ordered by employee code for deterministic output and limited to the requested number of rows. A tie at the cutoff can therefore be split by the limit.

4. **Headcount.** The department summary starts with employees who joined by the month's end, then uses `$lookup` and preserves employees with no matching attendance records. They still count toward headcount.

5. **100x data.** I would inspect execution statistics, validate index usage, and run realistic load tests. I would then tune indexes and aggregation pipelines based on measured bottlenecks.
'@ | Set-Content DECISIONS.md -Encoding utf8