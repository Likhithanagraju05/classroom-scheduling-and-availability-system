import mysql.connector

def get_db_connection():
    conn = mysql.connector.connect(
        host="localhost",
        user="root",           
        password="root",   
        database="classroom_db1"
    )
    return conn
