# REVIEW.md

List every defect you found in the starter `app/main.py` (helpers and endpoints). For each one:

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | | | | |

Also note anything you looked at and decided was **not** a defect, and why.

# REVIEW.md

## 1. Defects Found in the Starter Code

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `list_employees` — pagination | The page calculation was wrong, so the first page could be empty even when employees existed. | There were 6 employees, but page 1 returned an empty list. | Fixed the calculation to `(page - 1) * page_size`. |
| 2 | `list_employees` — total count | The total count did not consider the department filter. | Filtering by a department returned the wrong total. | Used the same filter when counting employees. |
| 3 | `list_employees` — sorting | Employees were not sorted by employee code. | The employee codes were not returned in the required order. | Added sorting by `emp_code` in MongoDB. |
| 4 | `list_employees` — pagination validation | Invalid page numbers and page sizes were allowed. | Tried `page=0` or `page_size=101`. | Added validation for page and page size. |
| 5 | `EmployeeIn` / `create_employee` — validation | Invalid employee details were accepted. | Submitted `emp_code: "string"`, and it was stored. | Added validation for employee code, email, joining date, and shift times. |
| 6 | `create_employee` — duplicate check | Two requests could create the same employee because the database had no unique index on `emp_code`. | Two requests with the same code could arrive at almost the same time. | Added a unique index and handled duplicate-key errors. |
| 7 | `punch_in` — employee lookup | Punching in with an unknown employee code caused a server error. | Submitted an employee code that did not exist. | Checked whether the employee exists and returned `404` if missing. |
| 8 | `punch_in` — timestamp conversion | A timestamp in seconds was accepted as milliseconds, giving the wrong date. | Submitted `punched_at: 1791948600`; it became a date near 1970. | Added validation to reject seconds-based timestamps. |
| 9 | `punch_in` — timestamp check | A timestamp of `0` was treated as if no timestamp was provided. | Submitted `punched_at: 0`, but the current time was used instead. | Checked for `None` explicitly and added timestamp validation. |
| 10 | `punch_in` — timezone handling | The code depended on the server's timezone and created a datetime without timezone information. | The converted time could differ depending on the server timezone. | Used an explicit timezone and converted timestamps to IST. |
| 11 | `punch_in` — overnight shifts | The attendance date was wrong for shifts that continued past midnight. | Punched in after midnight for a `22:00–06:00` shift. | Added logic to identify the correct shift date. |
| 12 | `punch_in` — duplicate punch-ins | Two simultaneous punch-in requests could create duplicate attendance records. | Sent two punch-in requests for the same employee and date at the same time. | Added a unique index on `(emp_code, date)` and handled duplicate-key errors. |
| 13 | `punch_in` — response | The response included an unwanted `id` field. | Checked the response after punching in. | Removed the extra field from the API response. |
| 14 | `punch_in` — timestamp response | Timestamps were returned as strings instead of epoch milliseconds. | Checked the type of `punch_in` in the response. | Converted timestamp fields to integer epoch milliseconds. |
| 15 | `punch_in` — status validation | The API accepted unsupported attendance statuses. | Submitted `status: "FOO"`. | Allowed only `PRESENT`, `WFH`, and `ON_DUTY` for punch-in requests. |
| 16 | `compute_work_hours` — rounding | Normal floating-point rounding did not guarantee the required rounding behavior. | Tested work hours near a two-decimal rounding boundary. | Used `Decimal` with `ROUND_HALF_UP`. |
| 17 | `compute_overtime` — minimum duration | Overtime was counted even when it did not reach 30 minutes. | Punched out less than 30 minutes after shift end. | Added the 30-minute minimum before counting overtime. |
| 18 | `compute_overtime` — overnight shifts | Overtime was not calculated correctly for shifts crossing midnight. | Tested overtime for a `22:00–06:00` shift. | Calculated the correct shift-end time before computing overtime. |
| 19 | `/health` — database check | The health endpoint reported success without checking MongoDB. | Called `/health` when the database was unavailable. | Added a database ping and an error response when the check fails. |
| 20 | `list_attendance` — sorting | Records were sorted only by date in Python, not by both required fields in the database. | Records with the same date did not have the required employee-code order. | Added MongoDB sorting by date descending and employee code ascending. |
| 21 | `list_attendance` — pagination | The API loaded all matching attendance records before returning one page. | A large collection would require loading many unnecessary records. | Added database-side `skip()` and `limit()`. |
| 22 | `list_attendance` — total count | The total was calculated using the number of records loaded into memory. | The endpoint had to load all matching records just to calculate `total`. | Used `count_documents()` with the same filter. |
| 23 | `list_attendance` — pagination validation | Invalid page numbers and page sizes were not rejected. | Tried `page=0` or `page_size=101`. | Added validation for page and page size. |
| 24 | `list_attendance` — date validation | Invalid dates and reversed date ranges were not rejected. | Tried `date_from=2026-13-45` or a start date later than the end date. | Validated calendar dates and rejected reversed ranges with `422`. |
| 25 | `list_attendance` — status validation | Invalid status filters were accepted. | Called `/attendance?status=FOO`. | Added validation for supported attendance statuses. |
| 26 | `list_attendance` — response | The response included an unwanted `id` field. | Checked the returned attendance records. | Excluded MongoDB's `_id` and stopped adding `id`. |
| 27 | `list_attendance` — timestamp response | Required timestamps, including history timestamps, were not consistently returned as epoch milliseconds. | Checked `punch_in`, `punch_out`, and timestamps inside `history`. | Added conversion for the required timestamp fields. |

## 2. Things I Checked That Were Not Defects

| # | What I checked | Why it is not a defect |
|---|---|---|
| 1 | Overnight shifts | A shift like `22:00–06:00` is valid, even though its end time is earlier than its start time. |
| 2 | Late-arrival grace period | An employee arriving within the first 10 minutes is not late. |
| 3 | Late-minute calculation | Once an employee is late, the minutes are counted from the shift start, not from the end of the grace period. |
| 4 | Overtime below 30 minutes | Less than 30 minutes after shift end does not count as overtime. |
| 5 | Working days | Saturday and Sunday are excluded because the contract defines Monday to Friday as working days. |
| 6 | Calculated attendance fields | Fields such as `work_hours`, `late_minutes`, `overtime_minutes`, and `half_day` should be calculated by the server, not set by the client. |

## 3. Notes

- I compared the starter implementation with the required behavior and recorded the defects I found.
- I used validation, database indexes, correct timestamp handling, and database-side queries to address the relevant problems.
- The `GET /attendance` changes still need to be completed and tested before those fixes can be marked as finished.
- I will verify each entry against the original code and the final implementation before submission.
