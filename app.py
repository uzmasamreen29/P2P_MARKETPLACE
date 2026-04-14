from flask import Flask, render_template, request, redirect, session, flash
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

#ensure_demo_data()

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

            if user["role"] == "student":
                return redirect("/student_dashboard")
            else:
                return redirect("/tutor_dashboard")

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

    if request.method == "GET":
        return render_template("add_slot.html")

    slots_collection.insert_one({
        "tutor_id": ObjectId(session["user_id"]),
        "subject": request.form.get("subject"),
        "date": request.form.get("date"),
        "start": request.form.get("start"),
        "end": request.form.get("end"),
        "status": "available"
    })

    return redirect("/tutor_dashboard")

# ---------------- SEARCH ----------------
@app.route("/search_tutor")
def search_tutor():

    tutors = users_collection.find({"role": "tutor"})
    tutor_list = []

    for t in tutors:
        tutor_id = t["_id"]

        # 🔥 get rating
        ratings = list(ratings_collection.find({"tutor_id": tutor_id}))

        if ratings:
            total = sum(r["rating"] for r in ratings)
            count = len(ratings)
            avg = total / count
        else:
            avg = 0
            count = 0

        # 🔥 get slots of this tutor
        slots = slots_collection.find({
            "tutor_id": tutor_id,
            "status": "available"
        })

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

    slot_id = request.form.get("slot_id")

    requests_collection.insert_one({
        "slot_id": ObjectId(slot_id),
        "student_id": ObjectId(session["user_id"]),
        "status": "pending"
    })

    return redirect("/student_dashboard")

# ---------------- ACCEPT REQUEST ----------------
@app.route("/accept_request", methods=["POST"])
def accept_request():

    req_id = request.form.get("request_id")

    req = requests_collection.find_one({"_id": ObjectId(req_id)})

    if not req:
        return "Request not found"

    slot_id = req["slot_id"]

    # 🔥 FORCE PRINT (CHECK IN TERMINAL)
    print("REQ FOUND:", req)
    print("SLOT ID:", slot_id)

    # ✅ BOOK SLOT (FIX IS HERE)
    result = slots_collection.update_one(
        {"_id": ObjectId(slot_id)},
        {"$set": {
            "status": "booked",
            "student_id": req["student_id"]
        }}
    )

    print("MATCHED:", result.matched_count)
    print("UPDATED:", result.modified_count)

    return redirect("/tutor_dashboard")
# ---------------- REJECT REQUEST ----------------
@app.route("/reject_request", methods=["POST"])
def reject_request():

    req_id = request.form.get("request_id")

    requests_collection.update_one(
        {"_id": ObjectId(req_id)},
        {"$set": {"status": "rejected"}}
    )

    return redirect("/tutor_requests")

#----student_dashboard-
@app.route("/student_dashboard")
def student_dashboard():

    student_id = ObjectId(session["user_id"])
    student = users_collection.find_one({"_id": student_id})

    bookings = []
    req_list = []

    # ---------------- BOOKINGS ----------------
    booked_slots = slots_collection.find({
        "student_id": student_id,
        "status": "booked"
    })

    for slot in booked_slots:
        tutor = users_collection.find_one({"_id": slot["tutor_id"]})

        if tutor:
            # 🔥 get student's rating for this tutor
            r = ratings_collection.find_one({
                "student_id": student_id,
                "tutor_id": slot["tutor_id"]
            })

            bookings.append({
                "slot_id": str(slot["_id"]),
                "subject": slot["subject"],
                "date": slot["date"],
                "start": slot["start"],
                "end": slot["end"],
                "tutor_name": tutor["name"],
                "tutor_id": str(slot["tutor_id"]),
                "my_rating": r["rating"] if r else None   # ⭐ IMPORTANT
            })

    # ---------------- REQUESTS ----------------
    req_cursor = requests_collection.find({
        "student_id": student_id
    })

    for r in req_cursor:
        slot = slots_collection.find_one({"_id": r["slot_id"]})

        if slot:
            req_list.append({
                "subject": slot["subject"],
                "date": slot["date"],
                "start": slot["start"],
                "status": r["status"]
            })

    return render_template(
        "student_dashboard.html",
        student=student,
        bookings=bookings,
        requests=req_list
    )
#-------------------ratings-----------
from flask import Flask, render_template, request, redirect, session, url_for
@app.route("/rate/<tutor_id>", methods=["POST"])
def rate_tutor(tutor_id):

    student_id = ObjectId(session["user_id"])
    tutor_id_obj = ObjectId(tutor_id)

    rating = int(request.form.get("rating", 0))

    # 🔍 Check if already rated
    existing = ratings_collection.find_one({
        "student_id": student_id,
        "tutor_id": tutor_id_obj
    })

    if existing:
        # 🔄 update rating
        ratings_collection.update_one(
            {"_id": existing["_id"]},
            {"$set": {"rating": rating}}
        )
    else:
        # ➕ new rating
        ratings_collection.insert_one({
            "student_id": student_id,
            "tutor_id": tutor_id_obj,
            "rating": rating
        })

    return redirect(url_for("student_dashboard"))
# ---------------- TUTOR DASHBOARD ----------------
@app.route("/tutor_dashboard")
def tutor_dashboard():

    tutor_id = ObjectId(session["user_id"])
    tutor = users_collection.find_one({"_id": tutor_id})

    available = []
    booked = []

    slots = slots_collection.find({"tutor_id": tutor_id})

    for s in slots:

        # ---------------- AVAILABLE ----------------
        if s["status"] == "available":
            available.append({
                "slot_id": str(s["_id"]),
                "subject": s["subject"],
                "date": s["date"],
                "start": s["start"],
                "end": s["end"]
            })

        # ---------------- BOOKED / COMPLETED ----------------
        elif s["status"] in ["booked", "completed"]:

            student = users_collection.find_one({"_id": s.get("student_id")})

            booked.append({
                "slot_id": str(s["_id"]),
                "subject": s["subject"],
                "date": s["date"],
                "start": s["start"],
                "end": s["end"],
                "student_name": student["name"] if student else "Unknown",
                "status": s["status"]
            })

    # 🔥 ----------- CALCULATE RATING -----------
    ratings = list(ratings_collection.find({"tutor_id": tutor_id}))

    if ratings:
        total = sum(r["rating"] for r in ratings)
        count = len(ratings)
        avg_rating = total / count
    else:
        avg_rating = 0
        count = 0

    return render_template(
        "tutor_dashboard.html",
        tutor=tutor,
        available_slots=available,
        booked_slots=booked,
        avg_rating=avg_rating,        # ⭐ pass this
        total_reviews=count           # ⭐ pass this
    )


# ---------------- TUTOR REQUESTS ----------------
@app.route("/tutor_requests")
def tutor_requests():

    tutor_id = ObjectId(session["user_id"])

    all_requests = requests_collection.find({"status": "pending"})
    data = []

    for r in all_requests:
        slot = slots_collection.find_one({"_id": r["slot_id"]})

        if slot and slot["tutor_id"] == tutor_id:
            student = users_collection.find_one({"_id": r["student_id"]})

            if student:
                data.append({
                    "request_id": str(r["_id"]),
                    "subject": slot["subject"],
                    "date": slot["date"],
                    "start": slot["start"],
                    "student_name": student["name"]
                })

    return render_template("tutor_requests.html", requests=data)


# ---- mark_session_completed -----
@app.route("/complete_session", methods=["POST"])
def complete_session():

    slot_id = request.form.get("slot_id")

    slots_collection.update_one(
        {"_id": ObjectId(slot_id)},
        {"$set": {"status": "completed"}}
    )

    return redirect("/tutor_dashboard")
# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)