from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
import os
from datetime import datetime
from contextlib import closing
import secrets
import string

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
                taluka TEXT,
                village TEXT NOT NULL,
                phone TEXT UNIQUE NOT NULL,
                password TEXT,
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
                    INSERT INTO citizens (citizenRegNo, fullName, state, district, taluka, village, phone, password, createdAt)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    reg.get('citizenRegNo', ''),
                    reg.get('fullName', ''),
                    reg.get('state', ''),
                    reg.get('district', ''),
                    reg.get('taluka', ''),
                    reg.get('village', ''),
                    reg.get('phone', ''),
                    reg.get('password', ''),
                    reg.get('createdAt', datetime.utcnow().isoformat() + 'Z')
                ))
            except sqlite3.IntegrityError:
                # Skip duplicates (if any)
                continue
        db.commit()

# ------------------- Helper Functions -------------------
def generate_password(length=12):
    """Generate a random password."""
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*()_+'
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# ------------------- API endpoints -------------------
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required = ['fullName', 'state', 'district', 'taluka', 'village', 'phone']
    for field in required:
        if field not in data or not data[field].strip():
            return jsonify({'error': f'Missing or empty {field}'}), 400

    fullName = data['fullName'].strip()
    state = data['state'].strip()
    district = data['district'].strip()
    taluka = data['taluka'].strip()
    village = data['village'].strip()
    phone = data['phone'].strip()
    password = data.get('password', '').strip()
    
    # If password not provided, generate one
    if not password:
        password = generate_password()

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
                INSERT INTO citizens (citizenRegNo, fullName, state, district, taluka, village, phone, password, createdAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (citizenRegNo, fullName, state, district, taluka, village, phone, password, datetime.utcnow().isoformat() + 'Z'))
            db.commit()
            # Get the auto-generated ID
            reg_id = db.lastrowid
        except sqlite3.IntegrityError as e:
            error_msg = str(e)
            if 'UNIQUE constraint failed: citizens.phone' in error_msg:
                return jsonify({'error': 'Phone number already registered'}), 400
            elif 'UNIQUE constraint failed: citizens.citizenRegNo' in error_msg:
                return jsonify({'error': 'Registration number already exists'}), 400
            return jsonify({'error': 'Database error: ' + error_msg}), 400

    # Return the newly created record
    new_reg = {
        'id': reg_id,
        'citizenRegNo': citizenRegNo,
        'fullName': fullName,
        'state': state,
        'district': district,
        'taluka': taluka,
        'village': village,
        'phone': phone,
        'password': password,
        'createdAt': datetime.utcnow().isoformat() + 'Z'
    }
    return jsonify(new_reg), 201

@app.route('/api/registrations', methods=['GET'])
def get_all():
    with closing(get_db()) as db:
        rows = db.execute('SELECT * FROM citizens ORDER BY id').fetchall()
        result = [dict(row) for row in rows]
    return jsonify(result)

@app.route('/api/registrations/<int:reg_id>', methods=['GET'])
def get_single(reg_id):
    with closing(get_db()) as db:
        row = db.execute('SELECT * FROM citizens WHERE id = ?', (reg_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Registration not found'}), 404
        return jsonify(dict(row))

@app.route('/api/registrations/<int:reg_id>', methods=['PUT'])
def update_registration(reg_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    fullName = data.get('fullName', '').strip()
    state = data.get('state', '').strip()
    district = data.get('district', '').strip()
    taluka = data.get('taluka', '').strip()
    village = data.get('village', '').strip()
    phone = data.get('phone', '').strip()
    password = data.get('password', '').strip()

    if not all([fullName, state, district, taluka, village, phone]):
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
                SET fullName = ?, state = ?, district = ?, taluka = ?, village = ?, phone = ?
                WHERE id = ?
            ''', (fullName, state, district, taluka, village, phone, reg_id))
            db.commit()
            # Fetch the updated row
            updated = db.execute('SELECT * FROM citizens WHERE id = ?', (reg_id,)).fetchone()
            return jsonify(dict(updated))
        except sqlite3.IntegrityError as e:
            if 'UNIQUE constraint failed: citizens.phone' in str(e):
                return jsonify({'error': 'Phone number already used by another record'}), 400
            return jsonify({'error': 'Database error: ' + str(e)}), 400

@app.route('/api/registrations/<int:reg_id>', methods=['DELETE'])
def delete_registration(reg_id):
    with closing(get_db()) as db:
        db.execute('DELETE FROM citizens WHERE id = ?', (reg_id,))
        if db.total_changes == 0:
            return jsonify({'error': 'Registration not found'}), 404
        db.commit()
    return jsonify({'message': 'Deleted successfully'}), 200

@app.route('/api/check-phone', methods=['POST'])
def check_phone():
    """Check if phone number already exists."""
    data = request.get_json()
    if not data or 'phone' not in data:
        return jsonify({'error': 'Phone number required'}), 400
    
    phone = data['phone'].strip()
    with closing(get_db()) as db:
        existing = db.execute('SELECT phone FROM citizens WHERE phone = ?', (phone,)).fetchone()
        if existing:
            return jsonify({'exists': True, 'message': 'Phone number already registered'}), 200
        return jsonify({'exists': False, 'message': 'Phone number available'}), 200

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'database': 'connected'
    }), 200

# ------------------- Error Handlers -------------------
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(400)
def bad_request(error):
    return jsonify({'error': 'Bad request'}), 400

# ------------------- Initialization -------------------
init_db()
migrate_json_to_sqlite()

if __name__ == '__main__':
    # Get port from environment variable for Render deployment
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
