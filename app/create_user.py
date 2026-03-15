from flask_bcrypt import Bcrypt
from app import app
import mysql.connector

bcrypt = Bcrypt(app)

password = "sdc123"
hashed = bcrypt.generate_password_hash(password).decode("utf-8")

print("Generated Hash:", hashed)

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="YOUR_MYSQL_PASSWORD",
    database="classroom_db1"
)

cursor = conn.cursor()

cursor.execute("DELETE FROM users1 WHERE email=%s", ("lecturer@secure.com",))

cursor.execute(
    "INSERT INTO users1 (name, email, password) VALUES (%s,%s,%s)",
    ("Main User", "lecturer@secure.com", hashed)
)

conn.commit()
conn.close()

print("User inserted successfully!")