"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
import math
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from decimal import Decimal, ROUND_HALF_UP

load_dotenv()

client = MongoClient(
    os.getenv("MONGO_URI", "mongodb://localhost:27017"),
    serverSelectionTimeoutMS=3000,
)
db = client[os.getenv("MONGO_DB", "attendance_db")]


# Create required indexes idempotently at application startup.
db.employees.create_index(
    [("emp_code", 1)],
    unique=True,
    name="uniq_employee_code",
)


db.attendance_logs.create_index(
    [("emp_code", 1), ("date", 1)],
    unique=True,
)


db.attendance_logs.create_index(
    [("date", -1), ("emp_code", 1)],
    name="attendance_date_employee",
)


IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def parse_epoch_ms(value: Optional[int]) -> datetime:
    if value is None:
        return datetime.now(IST).replace(microsecond=0)

    if isinstance(value, bool) or not isinstance(value, int):
        raise HTTPException(422, "punched_at must be epoch milliseconds")

    if value < 100_000_000_000:
        raise HTTPException(422, "punched_at must be in milliseconds")

    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc) \
            .astimezone(IST).replace(microsecond=0)
    except (ValueError, OverflowError, OSError):
        raise HTTPException(422, "punched_at is out of range")





def compute_late_minutes(
    punch_in: datetime,
    shift_start: str,
    shift_end: str,
) -> int:
    h, m = map(int, shift_start.split(":"))
    end_h, end_m = map(int, shift_end.split(":"))

    start = punch_in.replace(
        hour=h,
        minute=m,
        second=0,
        microsecond=0,
    )

    # If this is an overnight shift and punch-in is
    # after midnight but before the shift's end,
    # the shift started on the previous calendar day.
    overnight = (end_h, end_m) <= (h, m)
    punch_time = (punch_in.hour, punch_in.minute)

    if overnight and punch_time < (end_h, end_m):
        start -= timedelta(days=1)

    elapsed_seconds = int((punch_in - start).total_seconds())

    # Grace period: up to and including 10 minutes.
    if elapsed_seconds <= 10 * 60:
        return 0

    # Count whole minutes since shift start.
    return elapsed_seconds // 60


def to_epoch_ms(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)



def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    elapsed_seconds = Decimal(str((punch_out - punch_in).total_seconds()))
    hours = elapsed_seconds / Decimal("3600")
    rounded_hours = hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(rounded_hours)




def compute_overtime(
    punch_out: datetime,
    shift_start: str,
    shift_end: str,
    date_str: str,
) -> int:
    start_h, start_m = map(int, shift_start.split(":"))
    end_h, end_m = map(int, shift_end.split(":"))

    shift_end_dt = datetime.fromisoformat(date_str).replace(
        hour=end_h,
        minute=end_m,
        second=0,
        microsecond=0,
        tzinfo=IST,
    )

    # An end time at or before the start time means an overnight shift.
    if (end_h, end_m) <= (start_h, start_m):
        shift_end_dt += timedelta(days=1)

    elapsed_seconds = (punch_out - shift_end_dt).total_seconds()
    whole_minutes = int(elapsed_seconds // 60)

    if whole_minutes < 30:
        return 0

    return whole_minutes



# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class EmployeeIn(BaseModel):
    emp_code: str = Field(
        pattern=r"^EMP\d{4,6}$"
    )
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(
        min_length=3,
        max_length=120,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    department: str = Field(min_length=1, max_length=50)
    
    shift_start: str = Field(
        default="09:30",
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )
    shift_end: str = Field(
        default="18:30",
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )

    joined_on: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("joined_on")
    @classmethod
    def validate_joined_on(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError("joined_on must be a real date in YYYY-MM-DD format")
        return value

    @model_validator(mode="after")
    def validate_shifts(self):
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start and shift_end must differ")
        return self



class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[StrictInt] = None
    status: str = "PRESENT"


class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[StrictInt] = None


# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #

@app.get("/health")
def health():
    try:
        client.admin.command("ping")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )



@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    if db.employees.find_one({"emp_code": body.emp_code}):
        raise HTTPException(409, "emp_code already exists")
    doc = body.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    
    try:
        result = db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Employee code already exists",
        )

    doc.pop("_id", None)
    doc["created_at"] = to_epoch_ms(doc["created_at"])
    return doc


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    q = {}

    if department:
        q["department"] = department

    skip = (page - 1) * page_size

    total = db.employees.count_documents(q)

    items = list(
        db.employees.find(q, {"_id": 0})
        .sort("emp_code", 1)
        .skip(skip)
        .limit(page_size)
    )
    for item in items:
        if item.get("created_at") is not None:
            item["created_at"] = to_epoch_ms(item["created_at"])

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    # 1. Validate the status
    allowed_statuses = {"PRESENT", "WFH", "ON_DUTY"}

    if body.status not in allowed_statuses:
        raise HTTPException(
            status_code=422,
            detail="Punch-in status must be PRESENT, WFH, or ON_DUTY",
        )

    # 2. Find the employee
    emp = db.employees.find_one({"emp_code": body.emp_code})

    if emp is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    # 3. Convert the timestamp to IST
    ts = parse_epoch_ms(body.punched_at)

    # 4. Determine the attendance date
    shift_start = emp["shift_start"]
    shift_end = emp["shift_end"]

    punch_time = ts.strftime("%H:%M")
    overnight = shift_end <= shift_start

    if overnight and punch_time < shift_end:
        attendance_date = (ts.date() - timedelta(days=1))
    else:
        attendance_date = ts.date()

    d = attendance_date.isoformat()

    # 5. Calculate late minutes
    late_minutes = compute_late_minutes(
    ts,
    shift_start,
    shift_end,
    )

    # 6. Create the attendance record
    doc = {
        "emp_code": body.emp_code,
        "date": d,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": late_minutes,
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }

    # 7. Insert the record
    
    try:
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Attendance already exists for this employee and date",
        )

    doc.pop("_id", None)
    doc["punch_in"] = to_epoch_ms(doc["punch_in"])
    doc["punch_out"] = to_epoch_ms(doc["punch_out"])
    return doc


@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    # 1. Verify that the employee exists.
    emp = db.employees.find_one({"emp_code": body.emp_code})

    if emp is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found",
        )

    # 2. Parse the requested punch-out time.
    ts = parse_epoch_ms(body.punched_at)

    # 3. Find the latest punch-in at or before this time.
    record = db.attendance_logs.find_one(
        {
            "emp_code": body.emp_code,
            "punch_in": {
                "$ne": None,
                "$lte": ts,
            },
        },
        sort=[("punch_in", -1)],
    )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="No punch-in found before the requested punch-out time",
        )

    # 4. Reject a record that has already been punched out.
    if record.get("punch_out") is not None:
        raise HTTPException(
            status_code=409,
            detail="Employee has already punched out",
        )

    # 5. MongoDB may return naive datetimes representing UTC.
    punch_in_time = record["punch_in"]

    if punch_in_time.tzinfo is None:
        punch_in_time = punch_in_time.replace(tzinfo=timezone.utc)

    punch_in_time = punch_in_time.astimezone(IST)

    if ts <= punch_in_time:
        raise HTTPException(
            status_code=422,
            detail="Punch-out must be after punch-in",
        )

    elapsed_seconds = (ts - punch_in_time).total_seconds()

    if elapsed_seconds > 24 * 60 * 60:
        raise HTTPException(
            status_code=422,
            detail="Punch-out cannot be more than 24 hours after punch-in",
        )

    # 6. Calculate derived attendance values.
    work_hours = compute_work_hours(punch_in_time, ts)

    overtime_minutes = compute_overtime(
        ts,
        emp["shift_start"],
        emp["shift_end"],
        record["date"],
    )

    half_day = work_hours < 4.50

    # 7. Atomically update only if the record is still open.
    result = db.attendance_logs.update_one(
        {
            "_id": record["_id"],
            "punch_out": None,
        },
        {
            "$set": {
                "punch_out": ts,
                "work_hours": work_hours,
                "overtime_minutes": overtime_minutes,
                "half_day": half_day,
            },
        },
    )

    # If another request punched out first, this update won't match.
    if result.modified_count != 1:
        raise HTTPException(
            status_code=409,
            detail="Attendance has already been punched out",
        )

    # 8. Return the updated record without MongoDB's internal ID.
    updated = db.attendance_logs.find_one({"_id": record["_id"]})

    updated.pop("_id", None)
    updated["punch_in"] = to_epoch_ms(updated["punch_in"])
    updated["punch_out"] = to_epoch_ms(updated["punch_out"])

    return updated




@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    # 1. Validate date format and calendar dates
    def validate_date(value: Optional[str]) -> None:
        if value is None:
            return

        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
            if parsed.strftime("%Y-%m-%d") != value:
                raise ValueError
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid date: {value}. Expected YYYY-MM-DD.",
            )

    validate_date(date_from)
    validate_date(date_to)

    # 2. Reject reversed date ranges
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="date_from must be less than or equal to date_to",
        )

    # 3. Validate attendance status
    allowed_statuses = {
        "PRESENT",
        "WFH",
        "ON_DUTY",
        "ABSENT",
        "LEAVE",
    }

    if status is not None and status not in allowed_statuses:
        raise HTTPException(
            status_code=422,
            detail="Invalid status",
        )

    # 4. Build the MongoDB filter
    q = {}

    if emp_code is not None:
        q["emp_code"] = emp_code

    if date_from or date_to:
        q["date"] = {}

        if date_from:
            q["date"]["$gte"] = date_from

        if date_to:
            q["date"]["$lte"] = date_to

    if status is not None:
        q["status"] = status

    # 5. Count all matching records without loading them
    total = db.attendance_logs.count_documents(q)

    # 6. Sort and paginate inside MongoDB
    docs = list(
        db.attendance_logs.find(q, {"_id": 0})
        .sort([("date", -1), ("emp_code", 1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )

    # 7. Convert API timestamps to epoch milliseconds
    for doc in docs:
        for field in ("punch_in", "punch_out"):
            value = doc.get(field)
            if isinstance(value, datetime):
                doc[field] = to_epoch_ms(value)

        for entry in doc.get("history", []):
            if isinstance(entry.get("at"), datetime):
                entry["at"] = to_epoch_ms(entry["at"])

            changes = entry.get("changes", {})

            for field in ("punch_in", "punch_out"):
                field_changes = changes.get(field)

                if isinstance(field_changes, dict):
                    for direction in ("from", "to"):
                        value = field_changes.get(direction)

                        if isinstance(value, datetime):
                            field_changes[direction] = to_epoch_ms(value)

    return {
        "items": docs,
        "total": total,
        "page": page,
        "page_size": page_size,
    }

# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out
#   PATCH /attendance/{emp_code}/{date}
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #

# ---------------------------------------------------------------------------
# Analytics helpers and employee monthly summary
# ---------------------------------------------------------------------------

def _month_bounds(month: str):
    """Validate YYYY-MM and return inclusive month-start/month-end strings."""
    try:
        parsed = datetime.strptime(month, "%Y-%m")
        if parsed.strftime("%Y-%m") != month:
            raise ValueError
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="month must use YYYY-MM format",
        )

    start = parsed.replace(day=1)
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)

    end = next_month - timedelta(days=1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _working_days_expr(month_start: str, month_end: str):
    """MongoDB expression: count weekdays from max(joined_on, month start)."""
    joined_date = {"$dateFromString": {"dateString": "$joined_on"}}
    end_date = {"$dateFromString": {"dateString": month_end}}
    start_date = {
        "$dateFromString": {
            "dateString": {
                "$cond": [
                    {"$gt": ["$joined_on", month_start]},
                    "$joined_on",
                    month_start,
                ]
            }
        }
    }

    offsets = {
        "$range": [
            0,
            {
                "$add": [
                    {
                        "$dateDiff": {
                            "startDate": "$$start",
                            "endDate": end_date,
                            "unit": "day",
                        }
                    },
                    1,
                ]
            },
        ]
    }

    days = {
        "$map": {
            "input": offsets,
            "as": "offset",
            "in": {
                "$dateAdd": {
                    "startDate": "$$start",
                    "unit": "day",
                    "amount": "$$offset",
                }
            },
        }
    }

    weekdays = {
        "$filter": {
            "input": days,
            "as": "day",
            "cond": {
                "$and": [
                    {"$gte": [{"$dayOfWeek": "$$day"}, 2]},
                    {"$lte": [{"$dayOfWeek": "$$day"}, 6]},
                ]
            },
        }
    }

    return {
        "$cond": [
            {"$gt": [joined_date, end_date]},
            0,
            {
                "$let": {
                    "vars": {"start": start_date},
                    "in": {"$size": weekdays},
                }
            },
        ]
    }


@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(emp_code: str, month: str = Query(...)):
    month_start, month_end = _month_bounds(month)

    pipeline = [
        {"$match": {"emp_code": emp_code}},
        {"$limit": 1},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"code": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$code"]},
                                    {"$gte": ["$date", month_start]},
                                    {"$lte": ["$date", month_end]},
                                ]
                            }
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "present_days": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$and": [
                                                {
                                                    "$in": [
                                                        "$status",
                                                        ["PRESENT", "WFH", "ON_DUTY"],
                                                    ]
                                                },
                                                {
                                                    "$gte": [
                                                        {
                                                            "$dayOfWeek": {
                                                                "$dateFromString": {
                                                                    "dateString": "$date"
                                                                }
                                                            }
                                                        },
                                                        2,
                                                    ]
                                                },
                                                {
                                                    "$lte": [
                                                        {
                                                            "$dayOfWeek": {
                                                                "$dateFromString": {
                                                                    "dateString": "$date"
                                                                }
                                                            }
                                                        },
                                                        6,
                                                    ]
                                                },
                                            ]
                                        },
                                        {
                                            "$cond": [
                                                {"$eq": [{"$ifNull": ["$half_day", False]}, True]},
                                                0.5,
                                                1,
                                            ]
                                        },
                                        0,
                                    ]
                                }
                            },
                            "leave_days": {
                                "$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}
                            },
                            "late_count": {
                                "$sum": {
                                    "$cond": [
                                        {"$gt": [{"$ifNull": ["$late_minutes", 0]}, 0]},
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "total_late_minutes": {
                                "$sum": {"$ifNull": ["$late_minutes", 0]}
                            },
                            "total_overtime_minutes": {
                                "$sum": {"$ifNull": ["$overtime_minutes", 0]}
                            },
                        }
                    },
                ],
                "as": "_stats",
            }
        },
        {
            "$set": {
                "_stats": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$_stats", 0]},
                        {
                            "present_days": 0,
                            "leave_days": 0,
                            "late_count": 0,
                            "total_late_minutes": 0,
                            "total_overtime_minutes": 0,
                        },
                    ]
                },
                "working_days": _working_days_expr(month_start, month_end),
            }
        },
        {
            "$set": {
                "attendance_pct": {
                    "$cond": [
                        {"$eq": ["$working_days", 0]},
                        None,
                        {
                            "$divide": [
                                {
                                    "$floor": {
                                        "$add": [
                                            {
                                                "$multiply": [
                                                    {
                                                        "$divide": [
                                                            "$_stats.present_days",
                                                            "$working_days",
                                                        ]
                                                    },
                                                    1000000,
                                                ]
                                            },
                                            0.5,
                                        ]
                                    }
                                },
                                10000,
                            ]
                        },
                    ]
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "emp_code": 1,
                "month": {"$literal": month},
                "working_days": 1,
                "present_days": "$_stats.present_days",
                "leave_days": "$_stats.leave_days",
                "late_count": "$_stats.late_count",
                "total_late_minutes": "$_stats.total_late_minutes",
                "total_overtime_minutes": "$_stats.total_overtime_minutes",
                "attendance_pct": 1,
            }
        },
    ]

    result = list(db.employees.aggregate(pipeline))
    if not result:
        raise HTTPException(status_code=404, detail="Employee not found")

    return result[0]



# ---------------------------------------------------------------------------
# Department summary analytics
# ---------------------------------------------------------------------------

@app.get("/analytics/departments/summary")
def department_summary(month: str = Query(...)):
    month_start, month_end = _month_bounds(month)

    pipeline = [
        {
            "$match": {
                "joined_on": {"$lte": month_end}
            }
        },
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"code": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$code"]},
                                    {"$gte": ["$date", month_start]},
                                    {"$lte": ["$date", month_end]},
                                ]
                            }
                        }
                    }
                ],
                "as": "logs",
            }
        },
        {"$unwind": {"path": "$logs", "preserveNullAndEmptyArrays": True}},
        {
            "$group": {
                "_id": "$department",
                "headcount": {"$sum": 1},
                "present_days": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["$logs.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                    {"$gte": [{"$dayOfWeek": {"$dateFromString": {"dateString": "$logs.date"}}}, 2]},
                                    {"$lte": [{"$dayOfWeek": {"$dateFromString": {"dateString": "$logs.date"}}}, 6]},
                                ]
                            },
                            {
                                "$cond": [
                                    {"$eq": [{"$ifNull": ["$logs.half_day", False]}, True]},
                                    0.5,
                                    1,
                                ]
                            },
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {"$gt": [{"$ifNull": ["$logs.late_minutes", 0]}, 0]},
                            1,
                            0,
                        ]
                    }
                },
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$logs.late_minutes", 0]}
                },
                "total_overtime_minutes": {
                    "$sum": {"$ifNull": ["$logs.overtime_minutes", 0]}
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "headcount": 1,
                "present_days": 1,
                "late_count": 1,
                "total_late_minutes": 1,
                "total_overtime_minutes": 1,
            }
        },
        {"$sort": {"department": 1}},
    ]

    results = list(db.employees.aggregate(pipeline))
    return {"month": month, "departments": results}



# ---------------------------------------------------------------------------
# Late arrival leaderboard
# ---------------------------------------------------------------------------

@app.get("/analytics/leaderboard/late")
def late_leaderboard(month: str = Query(...), limit: int = Query(10, ge=1, le=100)):
    month_start, month_end = _month_bounds(month)

    pipeline = [
        {
            "$match": {
                "date": {"$gte": month_start, "$lte": month_end},
                "late_minutes": {"$gt": 0},
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {"$sum": "$late_minutes"},
                "late_count": {"$sum": 1},
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "employee",
            }
        },
        {"$unwind": "$employee"},
        {
            "$setWindowFields": {
                "sortBy": {"total_late_minutes": -1},
                "output": {"rank": {"$rank": {}}},
            }
        },
        {"$sort": {"rank": 1, "_id": 1}},
        {"$limit": limit},
        {
            "$project": {
                "_id": 0,
                "emp_code": "$_id",
                "name": "$employee.name",
                "department": "$employee.department",
                "total_late_minutes": 1,
                "late_count": 1,
                "rank": 1,
            }
        },
    ]

    results = list(db.attendance_logs.aggregate(pipeline))
    return {"month": month, "leaderboard": results}


# ---------------------------------------------------------------------------
# Department attendance trend
# ---------------------------------------------------------------------------

@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        if start.strftime("%Y-%m-%d") != start_date or end.strftime("%Y-%m-%d") != end_date:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="Dates must use YYYY-MM-DD format")

    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")

    if (end - start).days > 365:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 366 days")

    pipeline = [
        {
            "$match": {
                "department": department,
                "joined_on": {"$lte": end_date},
            }
        },
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"code": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$code"]},
                                    {"$gte": ["$date", start_date]},
                                    {"$lte": ["$date", end_date]},
                                    {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                                ]
                            }
                        }
                    },
                    {"$group": {"_id": "$date", "present": {"$sum": 1}}},
                ],
                "as": "daily",
            }
        },
        {"$unwind": {"path": "$daily", "preserveNullAndEmptyArrays": True}},
        {
            "$group": {
                "_id": {"$ifNull": ["$daily._id", None]},
                "present_days": {"$sum": {"$ifNull": ["$daily.present", 0]}},
            }
        },
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"_id": 1}},
        {
            "$setWindowFields": {
                "sortBy": {"_id": 1},
                "output": {
                    "moving_average_7d": {
                        "$avg": "$present_days",
                        "window": {"documents": [-6, 0]},
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": "$_id",
                "present_days": 1,
                "moving_average_7d": {
                    "$round": ["$moving_average_7d", 2]
                },
            }
        },
    ]

    results = list(db.employees.aggregate(pipeline))
    return {
        "department": department,
        "start_date": start_date,
        "end_date": end_date,
        "trend": results,
    }


# ---------------------------------------------------------------------------
# Update attendance record
# ---------------------------------------------------------------------------

@app.patch("/attendance/{emp_code}/{date}")
def update_attendance(
    emp_code: str,
    date: str,
    payload: dict,
):
    try:
        parsed_date = datetime.strptime(date, "%Y-%m-%d")
        if parsed_date.strftime("%Y-%m-%d") != date:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="date must use YYYY-MM-DD format")

    allowed_fields = {"status", "late_minutes", "overtime_minutes", "half_day"}
    changes = {key: value for key, value in payload.items() if key in allowed_fields}

    if not changes:
        raise HTTPException(
            status_code=422,
            detail=f"Provide at least one field to update: {sorted(allowed_fields)}",
        )

    if "status" in changes and changes["status"] not in {
        "PRESENT", "WFH", "ON_DUTY", "ABSENT", "LEAVE"
    }:
        raise HTTPException(status_code=422, detail="Invalid status")

    if "late_minutes" in changes:
        if type(changes["late_minutes"]) is not int or changes["late_minutes"] < 0:
            raise HTTPException(status_code=422, detail="late_minutes must be a non-negative integer")

    if "overtime_minutes" in changes:
        if type(changes["overtime_minutes"]) is not int or changes["overtime_minutes"] < 0:
            raise HTTPException(status_code=422, detail="overtime_minutes must be a non-negative integer")

    if "half_day" in changes and type(changes["half_day"]) is not bool:
        raise HTTPException(status_code=422, detail="half_day must be a boolean")

    employee = db.employees.find_one({"emp_code": emp_code}, {"_id": 0, "emp_code": 1})
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    record = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    history_entry = {
        "updated_at": datetime.now(timezone.utc),
        "changes": changes,
    }

    update_result = db.attendance_logs.update_one(
        {"emp_code": emp_code, "date": date},
        {
            "$set": changes,
            "$push": {"history": history_entry},
        },
    )

    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Attendance record not found")

    updated = db.attendance_logs.find_one(
        {"emp_code": emp_code, "date": date},
        {"_id": 0},
    )

    for field in ("punch_in", "punch_out"):
        if isinstance(updated.get(field), datetime):
            updated[field] = to_epoch_ms(updated[field])

    for entry in updated.get("history", []):
        if isinstance(entry.get("updated_at"), datetime):
            entry["updated_at"] = to_epoch_ms(entry["updated_at"])

    return updated