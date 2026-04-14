from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))

db = client["p2p_tutoring"]

users_collection = db["users"]
slots_collection = db["slots"]
sessions_collection = db["sessions"]
ratings_collection = db["ratings"]