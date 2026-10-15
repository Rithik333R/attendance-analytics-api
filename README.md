
@'
# Employee Attendance & Analytics API

A FastAPI and MongoDB REST API for employee management and attendance tracking, developed as part of the HROne Software Engineer hiring assignment.

## Tech Stack

- Python 3.11+
- FastAPI and Pydantic
- PyMongo
- MongoDB 6.0+
- Uvicorn

## Features Implemented

- Health check that verifies MongoDB connectivity.
- Employee creation with input validation and duplicate employee-code protection.
- Employee listing with department filtering, sorting, pagination, and total count.
- Attendance punch-in with employee validation, timestamp validation, IST handling, late-arrival calculation, and duplicate protection.
- Attendance punch-out with work-hour calculation, overtime calculation, and half-day determination.
- Attendance listing with filters, database-side sorting and pagination, and timestamp conversion.
- MongoDB indexes for unique employee codes and unique employee attendance per date.

## API Endpoints

| Method | Endpoint | Status |
|---|---|---|
| GET | `/health` | Implemented |
| POST | `/employees` | Implemented |
| GET | `/employees` | Implemented |
| POST | `/attendance/punch-in` | Implemented |
| POST | `/attendance/punch-out` | Implemented |
| GET | `/attendance` | Implemented |
| PATCH | `/attendance/{emp_code}/{date}` | Implemented; needs testing |
| GET | `/analytics/employees/{emp_code}/monthly` | Implemented and tested |
| GET | `/analytics/departments/summary` | Implemented and tested |
| GET | `/analytics/leaderboard/late` | Implemented and tested |
| GET | `/analytics/departments/{department}/trend` | Implemented; missing-date handling incomplete |
| GET | `/admin/explain/{endpoint}` | Not implemented yet |

The status above reflects the current implementation and will be updated as additional endpoints are completed.

## Prerequisites

- Python 3.11 or newer
- MongoDB 6.0 or newer, either locally or through MongoDB Atlas
- Git

## Setup

Run these commands from the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a local `.env` file in the repository root with your own MongoDB connection details:

```dotenv
MONGO_URI=your_mongodb_connection_string
MONGO_DB=attendance_db
```

Keep `.env` private. Do not commit database credentials or other secrets to Git.

## Run the API

```powershell
uvicorn app.main:app --port 8000
```

Open the interactive API documentation at:

- Swagger UI: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

The application creates its configured MongoDB indexes when the module is loaded.

## Data and Business Rules

- API timestamps are represented as epoch milliseconds.
- Attendance dates use the Asia/Kolkata (IST) calendar date.
- Attendance records are uniquely identified by employee code and attendance date.
- Supported punch-in statuses are `PRESENT`, `WFH`, and `ON_DUTY`.
- Work hours use two-decimal half-up rounding.
- Overtime is counted only when it reaches the required 30-minute threshold.
- Pagination starts at page 1 and uses a maximum page size of 100.

## Current Limitations

The admin explain endpoint is not implemented. Department trend currently omits dates with zero attendance, and PATCH still needs runtime testing. Some assignment requirements and edge cases may remain incomplete.

## Submission

Repository: https://github.com/Rithik333R/attendance-analytics-api
'@ | Set-Content README.md -Encoding utf8
