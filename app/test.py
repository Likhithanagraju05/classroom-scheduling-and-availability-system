from flask_bcrypt import Bcrypt
from flask import Flask

app = Flask(__name__)
bcrypt = Bcrypt(app)

password = "sdc123"   # ← use the password you want to login with

hashed = bcrypt.generate_password_hash(password).decode('utf-8')

print(hashed)