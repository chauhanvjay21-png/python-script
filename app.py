from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
import os
from datetime import datetime
from contextlib import closing

app = Flask(__name__)
CORS(app)

DATABASE = 'registrations.db'
JSON_BACKUP = 'registrations.json'   # optional backup file

# ------------------- Database helpers -------------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row   # allows accessing columns by name
    return conn

def init_db():
    """Create the table if it doesn't exist."""
    with closing(get_db()) as db:
        db.execute('''
            CREATE TABLE IF NOT EXISTS citizens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                citizenRegNo TEXT UNIQUE NOT NULL,
                fullName TEXT NOT NULL,
                state TEXT NOT NULL,
                district TEXT NOT NULL,
                village TEXT NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                createdAt TEXT NOT NULL
            )
        ''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_phone ON citizens(phone)')
        db.commit()

# ------------------- Migration from JSON (if file exists) -------------------
def migrate_json_to_sqlite():
    """Import existing JSON data into SQLite (if file exists and table is empty)."""
    if not os.path.exists(JSON_BACKUP):
        return

    with closing(get_db()) as db:
        # Check if table already has data
        count = db.execute('SELECT COUNT(*) FROM citizens').fetchone()[0]
        if count > 0:
            return   # already migrated

        with open(JSON_BACKUP, 'r') as f:
            try:
                data = json.load(f)
            except:
                return

        for reg in data:
            try:
                db.execute('''
                    INSERT INTO citizens (citizenRegNo, fullName, state, district, village, phone, createdAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    reg['citizenRegNo'],
                    reg['fullName'],
                    reg['state'],
                    reg['district'],
                    reg['village'],
                    reg['phone'],
                    reg.get('createdAt', datetime.utcnow().isoformat() + 'Z')
                ))
            except sqlite3.IntegrityError:
                # Skip duplicates (if any)
                continue
        db.commit()

# ------------------- API endpoints -------------------
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required = ['fullName', 'state', 'district', 'village', 'phone']
    for field in required:
        if field not in data or not data[field].strip():
            return jsonify({'error': f'Missing or empty {field}'}), 400

    fullName = data['fullName'].strip()
    state = data['state'].strip()
    district = data['district'].strip()
    village = data['village'].strip()
    phone = data['phone'].strip()

    # Basic validation (phone digits only, length 10)
    if not phone.isdigit() or len(phone) != 10:
        return jsonify({'error': 'Phone must be 10 digits'}), 400

    # Generate registration number
    with closing(get_db()) as db:
        # Find max numeric part from existing records
        max_id = db.execute('SELECT MAX(CAST(SUBSTR(citizenRegNo, 5) AS INTEGER)) FROM citizens').fetchone()[0]
        new_id = (max_id or 0) + 1
        citizenRegNo = f"CIT-{new_id:04d}"

        # Insert new record
        try:
            db.execute('''
                INSERT INTO citizens (citizenRegNo, fullName, state, district, village, phone, createdAt)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (citizenRegNo, fullName, state, district, village, phone, datetime.utcnow().isoformat() + 'Z'))
            db.commit()
            # Get the auto-generated ID
            reg_id = db.lastrowid
        except sqlite3.IntegrityError as e:
            if 'UNIQUE constraint failed: citizens.phone' in str(e):
                return jsonify({'error': 'Phone number already registered'}), 400
            return jsonify({'error': 'Duplicate registration number'}), 400

    # Return the newly created record
    new_reg = {
        'id': reg_id,
        'citizenRegNo': citizenRegNo,
        'fullName': fullName,
        'state': state,
        'district': district,
        'village': village,
        'phone': phone,
        'createdAt': datetime.utcnow().isoformat() + 'Z'
    }
    return jsonify(new_reg), 201

@app.route('/api/registrations', methods=['GET'])
def get_all():
    with closing(get_db()) as db:
        rows = db.execute('SELECT * FROM citizens ORDER BY id').fetchall()
        result = [dict(row) for row in rows]
    return jsonify(result)

@app.route('/api/registrations/<int:reg_id>', methods=['PUT'])
def update_registration(reg_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    fullName = data.get('fullName', '').strip()
    state = data.get('state', '').strip()
    district = data.get('district', '').strip()
    village = data.get('village', '').strip()
    phone = data.get('phone', '').strip()

    if not all([fullName, state, district, village, phone]):
        return jsonify({'error': 'All fields are required'}), 400

    with closing(get_db()) as db:
        # Check if record exists
        existing = db.execute('SELECT * FROM citizens WHERE id = ?', (reg_id,)).fetchone()
        if not existing:
            return jsonify({'error': 'Registration not found'}), 404

        # Try to update (phone uniqueness is enforced by SQLite)
        try:
            db.execute('''
                UPDATE citizens
                SET fullName = ?, state = ?, district = ?, village = ?, phone = ?
                WHERE id = ?
            ''', (fullName, state, district, village, phone, reg_id))
            db.commit()
            # Fetch the updated row
            updated = db.execute('SELECT * FROM citizens WHERE id = ?', (reg_id,)).fetchone()
            return jsonify(dict(updated))
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Phone number already used by another record'}), 400

@app.route('/api/registrations/<int:reg_id>', methods=['DELETE'])
def delete_registration(reg_id):
    with closing(get_db()) as db:
        db.execute('DELETE FROM citizens WHERE id = ?', (reg_id,))
        if db.total_changes == 0:
            return jsonify({'error': 'Registration not found'}), 404
        db.commit()
    return jsonify({'message': 'Deleted'}), 200

# ------------------- Initialization -------------------
init_db()
migrate_json_to_sqlite()

if __name__ == '__main__':
    app.run(debug=True)
