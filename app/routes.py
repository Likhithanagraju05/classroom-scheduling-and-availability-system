from flask import render_template, request, redirect, url_for, session, flash
from app import app
from app.db import get_db_connection
from flask_bcrypt import Bcrypt
from datetime import datetime, timedelta, time
import re

bcrypt = Bcrypt(app)
# ==================================================
# FLEXIBLE TIME PARSER (NEW - supports AM/PM formats)
# ==================================================

def parse_time_flexible(time_str):
    """
    Accepts:
    1PM, 1 PM
    1:30PM, 1:30 PM
    03:32AM, 3:32 AM
    """

    if not time_str:
        raise ValueError("Empty time")

    time_str = time_str.strip().upper()

    # Convert 1PM -> 1 PM
    time_str = re.sub(r'(?<=\d)(AM|PM)$', r' \1', time_str)

    formats = ["%I %p", "%I:%M %p"]

    for fmt in formats:
        try:
            return datetime.strptime(time_str, fmt)
        except ValueError:
            continue

    raise ValueError("Invalid time format")

# ==================================================
# TEMP STORAGE (in-memory)
# ==================================================

ongoing_classes = []
timetable_entries = []

# ✅ MCA Department Class Rooms (UPDATED → added section)
class_rooms = [
    {"room": "235", "name": "1st Year", "section": "A"},
    {"room": "213", "name": "1st Year", "section": "B"},
    {"room": "216", "name": "2nd Year", "section": "A"},
    {"room": "298", "name": "2nd Year", "section": "B"}
]

# ==================================================
# PUBLIC PAGES
# ==================================================

@app.route("/")
def home():
    return render_template("home.html")

@app.route("/features")
def features():
    return render_template("features.html")

@app.route("/about")
def about():
    return render_template("about.html")

# ==================================================
# LOGIN
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email").strip()
        password = request.form.get("password").strip()

        print("Email Entered:", email)

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM users1 WHERE email=%s", (email,))
        user = cursor.fetchone()

        print("Fetched User:", user)

        conn.close()

        if user and bcrypt.check_password_hash(user["password"], password):
            print("LOGIN SUCCESS")
            session["user_id"] = user["user_id"]
            session["name"] = user["name"]
            return redirect(url_for("dashboard"))
        else:
            print("LOGIN FAILED")
            flash("Invalid login credentials")

    return render_template("login.html")
# ==================================================
# DASHBOARD
# ==================================================
from datetime import datetime, time

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM ongoing_classes")
    classes = cursor.fetchall()

    now = datetime.now()

    for cls in classes:

        cls["free_datetime"] = datetime.max
        free_time_raw = cls.get("free_at")

        if free_time_raw:

            try:
                if isinstance(free_time_raw, str):
                    free_time_time = datetime.strptime(
                        free_time_raw, "%H:%M:%S"
                    ).time()

                elif isinstance(free_time_raw, time):
                    free_time_time = free_time_raw

                else:
                    free_time_str = str(free_time_raw)
                    free_time_time = datetime.strptime(
                        free_time_str, "%H:%M:%S"
                    ).time()

                free_time_obj = datetime.combine(
                    now.date(),
                    free_time_time
                )

                cls["free_datetime"] = free_time_obj

                if now >= free_time_obj and cls["status"] == "Ongoing":
                    cursor.execute("""
                        UPDATE ongoing_classes
                        SET status='Available'
                        WHERE id=%s
                    """, (cls["id"],))
                    cls["status"] = "Available"

                # ✅ 12-hour format
                cls["free_at"] = free_time_obj.strftime("%I:%M %p")

            except Exception as e:
                print("Time conversion error:", e)
                cls["free_at"] = "--"
        else:
            cls["free_at"] = "--"

    conn.commit()

    sorted_classes = sorted(
        classes,
        key=lambda x: x["free_datetime"]
    )

    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html",
        name=session["name"],
        classes=sorted_classes
    )
# ==================================================
# START / END CLASS (FIXED PROPER TIME STORAGE)
# ==================================================
@app.route("/start_end_class", methods=["GET", "POST"])
def start_end_class():

    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":

        room = request.form.get("room")
        subject = request.form.get("subject")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")
        lecturer = request.form.get("lecturer")

        if not room or not subject or not start_time or not end_time:
            flash("All fields are required")
            return redirect(url_for("start_end_class"))

        try:
            start_dt = parse_time_flexible(start_time)
            end_dt = parse_time_flexible(end_time) + timedelta(minutes=1)

        except ValueError:
            flash("Invalid time format")
            return redirect(url_for("start_end_class"))

        conn = get_db_connection()

        # ✅ buffered cursor prevents unread result error
        cursor = conn.cursor(dictionary=True, buffered=True)

        # 🔴 Check if room already has class in same time
        cursor.execute("""
           SELECT id FROM ongoing_classes
           WHERE room=%s
           AND (
               (%s BETWEEN start_time AND free_at)
               OR
               (%s BETWEEN start_time AND free_at)
            )
        """, (
            room,
            start_dt.strftime("%H:%M:%S"),
            end_dt.strftime("%H:%M:%S")
))

        existing_class = cursor.fetchone()

        if existing_class:
            flash(f"Room {room} already has an ongoing class")
            cursor.close()
            conn.close()
            return redirect(url_for("start_end_class"))

        # ✅ Insert new class
        cursor.execute("""
            INSERT INTO ongoing_classes
            (room, lecturer, subject, start_time, free_at, status)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (
            room,
            lecturer,
            subject,
            start_dt.strftime("%H:%M:%S"),
            end_dt.strftime("%H:%M:%S"),
            "Ongoing"
        ))

        conn.commit()
        cursor.close()
        conn.close()

        flash("Class started successfully")
        return redirect(url_for("dashboard"))

    return render_template(
        "start_end_class.html",
        lecturer=session["name"]
    )
# ==================================================
# EXTEND CLASS (FIXED PROPER TIME HANDLING)
# ==================================================
@app.route("/extend_class/<room>", methods=["POST"])
def extend_class(room):

    if "user_id" not in session:
        return redirect(url_for("dashboard"))

    extend_minutes = int(request.form.get("minutes", 0))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)

    cursor.execute("SELECT free_at FROM ongoing_classes WHERE room=%s", (room,))
    data = cursor.fetchone()

    if data and data["free_at"]:

        current_free = data["free_at"]

        # convert timedelta → time if needed
        if isinstance(current_free, timedelta):
            total_seconds = int(current_free.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            current_free = time(hours, minutes, seconds)

        today = datetime.now().date()
        current_free_dt = datetime.combine(today, current_free)

        new_free = current_free_dt + timedelta(minutes=extend_minutes + 1)

        cursor.execute("""
            UPDATE ongoing_classes
            SET free_at=%s
            WHERE room=%s
        """, (
            new_free.strftime("%H:%M:%S"),
            room
        ))

        conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for("dashboard"))
# ==================================================
# STOP CLASS (FIXED - NO UNREAD RESULT ERROR)
# ==================================================
@app.route("/stop_class/<room>")
def stop_class(room):

    if "user_id" not in session:
        return redirect(url_for("dashboard"))

    conn = get_db_connection()

    # ✅ buffered=True prevents unread result errors
    cursor = conn.cursor(dictionary=True, buffered=True)

    # ✅ GET CLASS FROM DATABASE (not memory list)
    cursor.execute("SELECT * FROM ongoing_classes WHERE room=%s", (room,))
    stopped_class = cursor.fetchone()   # clears result

    if stopped_class:

        # ✅ SAVE TO HISTORY TABLE
        cursor.execute("""
            INSERT INTO class_history
            (class_date, start_time, end_time, course_name, class_name, room_number)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            datetime.today().date(),
            stopped_class["start_time"],
            stopped_class["free_at"],
            stopped_class["subject"],
            stopped_class["lecturer"],
            stopped_class["room"]
        ))

        # ✅ DELETE FROM ONGOING TABLE (class stopped)
        cursor.execute("DELETE FROM ongoing_classes WHERE room=%s", (room,))

        conn.commit()

    cursor.close()
    conn.close()

    return redirect(url_for("dashboard"))
# ==================================================
# TIMETABLE (FULL DATABASE VERSION)
# ==================================================

@app.route("/timetable", methods=["GET", "POST"])
def timetable():

    if "user_id" not in session:
        return redirect(url_for("login"))

    # =========================
    # ADD TIMETABLE (POST)
    # =========================
    if request.method == "POST":

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO timetable (day, time, course, class_name, room)
            VALUES (%s,%s,%s,%s,%s)
        """, (
            request.form.get("day"),
            request.form.get("time"),
            request.form.get("course"),
            request.form.get("class_name"),
            request.form.get("room")
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("timetable"))

    # =========================
    # FETCH TIMETABLE (GET)
    # =========================
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM timetable")
    timetable_entries = cursor.fetchall()
    conn.close()

    # sort by day order
    day_order = {
        "Monday": 1, "Tuesday": 2, "Wednesday": 3,
        "Thursday": 4, "Friday": 5, "Saturday": 6, "Sunday": 7
    }

    sorted_timetable = sorted(
        timetable_entries,
        key=lambda x: day_order.get(x["day"], 99)
    )

    return render_template(
        "timetable.html",
        timetable=sorted_timetable,
    )


# ==================================================
# DELETE TIMETABLE (DATABASE)
# ==================================================

@app.route("/delete_timetable/<int:entry_id>")
def delete_timetable(entry_id):

    if "user_id" not in session:
        return redirect(url_for("timetable"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM timetable WHERE id=%s", (entry_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("timetable"))


# ==================================================
# EDIT TIMETABLE (DATABASE)
# ==================================================

@app.route("/edit_timetable", methods=["POST"])
def edit_timetable():

    if "user_id" not in session:
        return redirect(url_for("timetable"))

    entry_id = request.form.get("id")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE timetable
        SET day=%s, time=%s, course=%s, class_name=%s, room=%s
        WHERE id=%s
    """, (
        request.form.get("day"),
        request.form.get("time"),
        request.form.get("course"),
        request.form.get("class_name"),
        request.form.get("room"),
        entry_id
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("timetable"))
# ==================================================
# HISTORY
# ==================================================

@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT id, class_date, start_time, end_time,
               course_name, class_name, room_number
        FROM class_history
        ORDER BY class_date DESC, start_time DESC
    """)

    history_data = cursor.fetchall()
    conn.close()

    return render_template("history.html", history=history_data)

@app.route("/delete_history/<int:history_id>")
def delete_history(history_id):

    if "user_id" not in session:
        return redirect(url_for("login"))
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM class_history WHERE id = %s", (history_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("history"))

# ==================================================
# CLASS STATUS (SYNC WITH DATABASE)
# ==================================================

from datetime import datetime
@app.route("/class_status")
def class_status():

    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            cr.id,
            cr.room,
            cr.year,
            cr.section,
            oc.status,
            oc.free_at
        FROM class_rooms cr
        LEFT JOIN ongoing_classes oc
            ON cr.room = oc.room
    """)

    rooms = cursor.fetchall()
    now = datetime.now()

    for room in rooms:

        if room["free_at"]:

            try:
                free_time_raw = room["free_at"]

                # ✅ Convert DB TIME safely
                if isinstance(free_time_raw, str):
                    free_time_time = datetime.strptime(
                        free_time_raw, "%H:%M:%S"
                    ).time()
                else:
                    free_time_time = free_time_raw

                free_datetime = datetime.combine(
                    now.date(),
                    free_time_time
                )

                # 🔴 Auto expire
                if now > free_datetime and room["status"] == "Ongoing":
                    cursor.execute("""
                        UPDATE ongoing_classes
                        SET status='Available'
                        WHERE room=%s
                    """, (room["room"],))
                    room["status"] = "Available"

                # ✅ Convert to 12-hour format for display
                room["free_at"] = free_datetime.strftime("%I:%M %p")

            except Exception as e:
                print("Time error:", e)

        # If no class running → show Available
        if not room["status"]:
            room["status"] = "Available"

    conn.commit()
    cursor.close()
    conn.close()

    return render_template(
        "class_status.html",
        rooms=rooms
    )
# ==================================================
# ADD CLASS ROOM → SAVE TO DATABASE
# ==================================================

@app.route("/add_class_room", methods=["POST"])
def add_class_room():

    if "user_id" not in session:
        return redirect(url_for("class_status"))

    room = request.form.get("room")
    name = request.form.get("name")   # this goes into "year" column
    section = request.form.get("section")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO class_rooms (room, year, section)
        VALUES (%s, %s, %s)
    """, (room, name, section))

    conn.commit()
    conn.close()

    return redirect(url_for("class_status"))


# ==================================================
# DELETE CLASS ROOM (DATABASE)
# ==================================================

@app.route("/delete_class_room/<int:id>")
def delete_class_room(id):

    if "user_id" not in session:
        return redirect(url_for("class_status"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM class_rooms WHERE id=%s", (id,))
    conn.commit()
    conn.close()

    return redirect(url_for("class_status"))


# ==================================================
# EDIT CLASS ROOM (DATABASE)
# ==================================================

@app.route("/edit_class_room", methods=["POST"])
def edit_class_room():

    if "user_id" not in session:
        return redirect(url_for("class_status"))

    room_id = request.form.get("id")   # HTML must send id

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE class_rooms
        SET room=%s, year=%s, section=%s
        WHERE id=%s
    """, (
        request.form.get("room"),
        request.form.get("name"),
        request.form.get("section"),
        room_id
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("class_status"))

# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

