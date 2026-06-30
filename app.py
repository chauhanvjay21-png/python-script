# app.py
from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)  # allow cross-origin requests from Blogger

DATA_FILE = 'registrations.json'

# ------------------- JSON file helpers -------------------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# ------------------- API routes -------------------
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    required = ['fullName', 'state', 'district', 'village', 'phone']
    for field in required:
        if field not in data or not data[field].strip():
            return jsonify({'error': f'Missing or empty {field}'}), 400

    registrations = load_data()

    # Auto-generate registration number
    # Find max numeric part
    max_id = 0
    for reg in registrations:
        reg_no = reg.get('citizenRegNo', '')
        if reg_no.startswith('CIT-'):
            try:
                num = int(reg_no.split('-')[1])
                if num > max_id:
                    max_id = num
            except:
                pass
    new_id = max_id + 1
    citizen_reg_no = f"CIT-{new_id:04d}"

    registration = {
        'id': new_id,  # internal numeric ID for easier updates
        'citizenRegNo': citizen_reg_no,
        'fullName': data['fullName'].strip(),
        'state': data['state'].strip(),
        'district': data['district'].strip(),
        'village': data['village'].strip(),
        'phone': data['phone'].strip(),
        'createdAt': datetime.utcnow().isoformat() + 'Z'
    }

    registrations.append(registration)
    save_data(registrations)
    return jsonify(registration), 201

@app.route('/api/registrations', methods=['GET'])
def get_all():
    registrations = load_data()
    return jsonify(registrations)

@app.route('/api/registrations/<int:reg_id>', methods=['PUT'])
def update_registration(reg_id):
    registrations = load_data()
    for idx, reg in enumerate(registrations):
        if reg.get('id') == reg_id:
            updates = request.get_json()
            # Update fields (cannot change ID/regNo)
            reg['fullName'] = updates.get('fullName', reg['fullName']).strip()
            reg['state'] = updates.get('state', reg['state']).strip()
            reg['district'] = updates.get('district', reg['district']).strip()
            reg['village'] = updates.get('village', reg['village']).strip()
            reg['phone'] = updates.get('phone', reg['phone']).strip()
            registrations[idx] = reg
            save_data(registrations)
            return jsonify(reg)
    return jsonify({'error': 'Registration not found'}), 404

@app.route('/api/registrations/<int:reg_id>', methods=['DELETE'])
def delete_registration(reg_id):
    registrations = load_data()
    new_list = [reg for reg in registrations if reg.get('id') != reg_id]
    if len(new_list) == len(registrations):
        return jsonify({'error': 'Registration not found'}), 404
    save_data(new_list)
    return jsonify({'message': 'Deleted'}), 200

# ------------------- Developer Portal (frontend) -------------------
@app.route('/')
def portal():
    return render_template('portal.html')

# ------------------- Run -------------------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
