from flask import Flask, render_template, jsonify, request
from faker import Faker
import random
import psycopg2
from psycopg2.extras import RealDictCursor
import time

app = Flask(__name__)
fake = Faker('ru_RU')

DB_CONFIG = {
    "host": "db",
    "database": "my_company_db",
    "user": "db_user",
    "password": "db_password",
    "port": 5432
}

def get_db_connection():
    for _ in range(5):
        try:
            return psycopg2.connect(**DB_CONFIG)
        except psycopg2.OperationalError:
            time.sleep(2)
    raise Exception("Не удалось подключиться к PostgreSQL")

def generate_data():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Полная очистка со сбросом счетчиков ID
    cur.execute("TRUNCATE TABLE users RESTART IDENTITY CASCADE;")
    
    for i in range(1, 1002):
        gender = random.choice(['male', 'female'])
        if gender == 'male':
            first_name = fake.first_name_male()
            middle_name = fake.middle_name_male()
            last_name = fake.last_name_male()
            sex = "Мужской"
        else:
            first_name = fake.first_name_female()
            middle_name = fake.middle_name_female()
            last_name = fake.last_name_female()
            sex = "Женский"
            
        birth_date = fake.date_of_birth(minimum_age=18, maximum_age=70)
        
        # Запись в Users
        cur.execute("""
            INSERT INTO users (last_name, first_name, middle_name, mobile_phone, home_phone, birth_date, gender, email)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """, (last_name, first_name, middle_name, fake.phone_number(), 
              fake.phone_number() if random.random() > 0.3 else "-", birth_date, sex, fake.ascii_free_email()))
        
        user_id = cur.fetchone()[0]
        
        # Запись в Passports
        cur.execute("""
            INSERT INTO passports (user_id, passport_series_number, last_name, first_name, middle_name, birth_date, issue_date, department_code, issued_by, birth_place, address, foreign_passport)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (user_id, f"{random.randint(10, 99)} {random.randint(10, 99)} {random.randint(100000, 999999)}",
              last_name, first_name, middle_name, birth_date, fake.date_between(start_date=birth_date),
              f"{random.randint(100, 999)}-{random.randint(100, 999)}", f"УВМ ГУ МВД по {fake.region()}", 
              f"г. {fake.city()}", fake.address(), f"53 № {random.randint(1000000, 9999999)}" if random.random() > 0.5 else "-"))
        
    conn.commit()
    cur.close()
    conn.close()

try:
    generate_data()
except Exception as e:
    print(f"Ожидание запуска БД: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/users', methods=['GET'])
def get_users():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT u.id, u.last_name, u.first_name, u.middle_name, u.mobile_phone, u.home_phone, 
               TO_CHAR(u.birth_date, 'YYYY-MM-DD') as birth_date, u.gender, u.email,
               p.passport_series_number, TO_CHAR(p.issue_date, 'YYYY-MM-DD') as issue_date, 
               p.department_code, p.issued_by, p.birth_place, p.address, p.foreign_passport
        FROM users u
        JOIN passports p ON u.id = p.user_id
        ORDER BY u.id DESC;
    """)
    combined_list = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(combined_list)

@app.route('/api/users', methods=['POST'])
def add_user():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Транзакционная запись в первую таблицу
        cur.execute("""
            INSERT INTO users (last_name, first_name, middle_name, mobile_phone, home_phone, birth_date, gender, email)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """, (data['last_name'], data['first_name'], data['middle_name'], data['mobile_phone'], 
              data['home_phone'] or '-', data['birth_date'], data['gender'], data['email']))
        
        user_id = cur.fetchone()[0]
        
        # Транзакционная запись во вторую таблицу (связь по user_id)
        cur.execute("""
            INSERT INTO passports (user_id, passport_series_number, last_name, first_name, middle_name, birth_date, issue_date, department_code, issued_by, birth_place, address, foreign_passport)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (user_id, data['passport_series_number'], data['last_name'], data['first_name'], data['middle_name'], 
              data['birth_date'], data['issue_date'], data['department_code'], data['issued_by'], 
              data['birth_place'], data['address'], data['foreign_passport'] or '-'))
        
        conn.commit()
        return jsonify({"status": "success"}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400
    finally:
        cur.close()
        conn.close()

@app.route('/api/regenerate', methods=['POST'])
def regenerate():
    generate_data()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
