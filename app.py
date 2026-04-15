from flask import Flask, render_template, request, redirect, session, flash, url_for
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret123"

# ---------------- MONGODB ----------------
client = MongoClient("mongodb://localhost:27017/")
db = client["tutorlink"]

users_collection = db["users"]
slots_collection = db["slots"]
requests_collection = db["requests"]
ratings_collection = db["ratings"]


# ---------------- DEMO DATA ----------------
def ensure_demo_data():

    tutor = users_collection.find_one({"email": "sarah@demo.com"})
    student = users_collection.find_one({"email": "alex@demo.com"})

    tutor_id = None

    if not tutor:
        tutor_id = users_collection.insert_one({
            "name": "Sarah Tutor",
            "email": "sarah@demo.com",
            "password": generate_password_hash("demo123"),
            "role": "tutor",
            "bio": "Python expert"
        }).inserted_id
    else:
        tutor_id = tutor["_id"]

    if not student:
        users_collection.insert_one({
            "name": "Alex Student",
            "email": "alex@demo.com",
            "password": generate_password_hash("demo123"),
            "role": "student",
            "bio": ""
        })

    slots_collection.delete_many({})
    requests_collection.delete_many({})

    slots_collection.insert_many([
        {
            "tutor_id": tutor_id,
            "subject": "Math",
            "date": "2026-04-15",
            "start": "10:00",
            "end": "11:00",
            "status": "available"
        },
        {
            "tutor_id": tutor_id,
            "subject": "Physics",
            "date": "2026-04-16",
            "start": "14:00",
            "end": "15:00",
            "status": "available"
        }
    ])


# Call once if needed
# ensure_demo_data()


# ---------------- HOME ----------------
@app.route("/")
def home():
    return render_template("index.html")


# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        if users_collection.find_one({"email": request.form["email"]}):
            flash("Email already exists")
            return redirect("/signup")

        users_collection.insert_one({
            "name": request.form["name"],
            "email": request.form["email"],
            "password": generate_password_hash(request.form["password"]),
            "role": request.form["role"],
            "bio": request.form.get("bio", "")
        })

        return redirect("/login")

    return render_template("signup.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        user = users_collection.find_one({"email": request.form["email"]})

        if user and check_password_hash(user["password"], request.form["password"]):

            session["user_id"] = str(user["_id"])
            session["role"] = user["role"]

            return redirect("/student_dashboard" if user["role"] == "student" else "/tutor_dashboard")

        flash("Invalid credentials")
        return redirect("/login")

    return render_template("login.html")


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- ADD SLOT ----------------
@app.route("/add_slot", methods=["GET", "POST"])
def add_slot():

    if "user_id" not in session:
        return redirect("/login")

    if request.method == "POST":

        slots_collection.insert_one({
            "tutor_id": ObjectId(session["user_id"]),
            "subject": request.form["subject"],
            "date": request.form["date"],
            "start": request.form["start"],
            "end": request.form["end"],
            "status": "available"
        })

        return redirect("/tutor_dashboard")

    return render_template("add_slot.html")


# ---------------- SEARCH TUTOR ----------------
@app.route("/search_tutor")
def search_tutor():

    tutors = users_collection.find({"role": "tutor"})
    tutor_list = []

    for t in tutors:

        tutor_id = t["_id"]

        ratings = list(ratings_collection.find({"tutor_id": tutor_id}))
        count = len(ratings)
        avg = sum(r["rating"] for r in ratings) / count if count else 0

        slots = slots_collection.find({"tutor_id": tutor_id, "status": "available"})

        for slot in slots:
            tutor_list.append({
                "id": str(tutor_id),
                "name": t["name"],
                "subject": slot["subject"],
                "date": slot["date"],
                "start": slot["start"],
                "end": slot["end"],
                "slot_id": str(slot["_id"]),
                "rating": avg,
                "reviews": count
            })

    return render_template("search_tutor.html", tutors=tutor_list)


# ---------------- REQUEST SLOT ----------------
@app.route("/request_slot", methods=["POST"])
def request_slot():

    if "user_id" not in session:
        return redirect("/login")

    requests_collection.insert_one({
        "slot_id": ObjectId(request.form["slot_id"]),
        "student_id": ObjectId(session["user_id"]),
        "status": "pending"
    })

    return redirect("/student_dashboard")


# ---------------- ACCEPT REQUEST ----------------
@app.route("/accept_request", methods=["POST"])
def accept_request():

    req = requests_collection.find_one({"_id": ObjectId(request.form["request_id"])})

    if not req:
        return "Request not found"

    slots_collection.update_one(
        {"_id": req["slot_id"]},
        {"$set": {
            "status": "booked",
            "student_id": req["student_id"]
        }}
    )

    requests_collection.update_one(
        {"_id": req["_id"]},
        {"$set": {"status": "accepted"}}
    )

    return redirect("/tutor_dashboard")


# ---------------- REJECT REQUEST ----------------
@app.route("/reject_request", methods=["POST"])
def reject_request():

    requests_collection.update_one(
        {"_id": ObjectId(request.form["request_id"])},
        {"$set": {"status": "rejected"}}
    )

    return redirect("/tutor_requests")


# ---------------- RATE TUTOR ----------------
@app.route("/rate/<tutor_id>", methods=["POST"])
def rate_tutor(tutor_id):

    if "user_id" not in session:
        return redirect("/login")

    rating_value = int(request.form.get("rating", 0))

    existing = ratings_collection.find_one({
        "tutor_id": ObjectId(tutor_id),
        "student_id": ObjectId(session["user_id"])
    })

    if existing:
        ratings_collection.update_one(
            {"_id": existing["_id"]},
            {"$set": {"rating": rating_value}}
        )
    else:
        ratings_collection.insert_one({
            "tutor_id": ObjectId(tutor_id),
            "student_id": ObjectId(session["user_id"]),
            "rating": rating_value
        })

    return redirect("/student_dashboard")


# ---------------- STUDENT DASHBOARD ----------------
@app.route("/student_dashboard")
def student_dashboard():

    if "user_id" not in session:
        return redirect("/login")

    student_id = ObjectId(session["user_id"])

    student = users_collection.find_one({"_id": student_id})

    bookings = []
    req_list = []

    # ---------------- BOOKED SESSIONS ----------------
    booked_slots = slots_collection.find({
        "student_id": student_id,
        "status": "booked"
    })

    for slot in booked_slots:

        tutor = users_collection.find_one({"_id": slot.get("tutor_id")})

        my_rating = ratings_collection.find_one({
            "tutor_id": slot.get("tutor_id"),
            "student_id": student_id
        })

        bookings.append({
            "slot_id": str(slot["_id"]),
            "subject": slot.get("subject", ""),
            "date": slot.get("date", ""),
            "start": slot.get("start", ""),
            "end": slot.get("end", ""),
            "tutor_name": tutor["name"] if tutor else "Unknown",
            "tutor_id": str(slot.get("tutor_id")),
            "my_rating": my_rating["rating"] if my_rating else None
        })

    # ---------------- REQUESTS ----------------
    reqs = requests_collection.find({
        "student_id": student_id
    })

    for r in reqs:

        slot = slots_collection.find_one({
            "_id": r.get("slot_id")
        })

        if slot:

            req_list.append({
                "subject": slot.get("subject", ""),
                "date": slot.get("date", ""),
                "start": slot.get("start", ""),
                "status": r.get("status", "pending")
            })

    return render_template(
        "student_dashboard.html",
        student=student,
        bookings=bookings,
        requests=req_list
    )

# ---------------- TUTOR DASHBOARD ----------------
@app.route("/tutor_dashboard")
def tutor_dashboard():

    if "user_id" not in session:
        return redirect("/login")

    tutor_id = ObjectId(session["user_id"])
    tutor = users_collection.find_one({"_id": tutor_id})

    available = []
    booked = []

    slots = slots_collection.find({"tutor_id": tutor_id})

    for s in slots:

        # ---------------- AVAILABLE ----------------
        if s.get("status") == "available":
            available.append({
    "slot_id": str(s["_id"]),
    "subject": s.get("subject", ""),
    "date": s.get("date", ""),
    "start": s.get("start", ""),
    "end": s.get("end", "")
})
        # ---------------- BOOKED / COMPLETED ----------------
        elif s.get("status") in ["booked", "completed"]:

            student_name = "Not Assigned"

            student_id = s.get("student_id")

            if student_id:
                student = users_collection.find_one({
                    "_id": ObjectId(student_id) if not isinstance(student_id, ObjectId) else student_id
                })

                if student:
                    student_name = student.get("name", "Unknown")

            booked.append({
                "slot_id": str(s["_id"]),
                "subject": s.get("subject", ""),
                "date": s.get("date", ""),
                "start": s.get("start", ""),
                "end": s.get("end", ""),
                "status": s.get("status", ""),
                "student_name": student_name
            })

    # ---------------- RATING ----------------
    ratings = list(ratings_collection.find({"tutor_id": tutor_id}))

    avg_rating = (
        sum(r.get("rating", 0) for r in ratings) / len(ratings)
        if ratings else 0
    )

    return render_template(
        "tutor_dashboard.html",
        tutor=tutor,
        available_slots=available,
        booked_slots=booked,
        avg_rating=avg_rating,
        total_reviews=len(ratings)
    )
# ---------------- TUTOR REQUESTS ----------------
@app.route("/tutor_requests")
def tutor_requests():

    tutor_id = ObjectId(session["user_id"])

    data = []

    for r in requests_collection.find({"status": "pending"}):

        slot = slots_collection.find_one({"_id": r["slot_id"]})

        if slot and slot["tutor_id"] == tutor_id:

            student = users_collection.find_one({"_id": r["student_id"]})

            data.append({
                "request_id": str(r["_id"]),
                "subject": slot["subject"],
                "date": slot["date"],
                "start": slot["start"],
                "student_name": student["name"]
            })

    return render_template("tutor_requests.html", requests=data)


# ---------------- COMPLETE SESSION ----------------
@app.route("/complete_session", methods=["POST"])
def complete_session():

    slot_id = request.form.get("slot_id")

    if not slot_id:
        return "Missing slot_id"

    try:
        slot_object_id = ObjectId(slot_id)
    except:
        return "Invalid slot_id"

    slots_collection.update_one(
        {"_id": slot_object_id},
        {"$set": {"status": "completed"}}
    )

    return redirect("/tutor_dashboard")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)