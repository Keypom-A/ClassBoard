import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DB_PATH = "/tmp/classboard.db"

# 日本時間を取得するヘルパー関数
def get_now_jst():
    # Render等の海外サーバーでも日本時間(+9時間)にする
    return datetime.utcnow() + timedelta(hours=9)

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, content TEXT, start TEXT, deadline TEXT, created_at TEXT)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            username TEXT, 
            message TEXT, 
            created_at TEXT
        )
    ''')
    conn.execute('INSERT OR IGNORE INTO users VALUES (?, ?, ?)', ('admin', '1234', 'admin'))
    conn.commit()
    return conn

@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('login'))
    
    conn = get_db()
    
    user_data = conn.execute('SELECT role FROM users WHERE username = ?', (session['username'],)).fetchone()
    if user_data:
        session['role'] = user_data['role']
    
    if session['username'] == 'admin':
        session['role'] = 'admin'
        conn.execute('UPDATE users SET role = ? WHERE username = ?', ('admin', 'admin'))
        conn.commit()

    now_jst = get_now_jst()
    now_str = now_jst.strftime('%Y-%m-%dT%H:%M')
    
    # 日本時間基準で7日経過したものを削除
    limit_date = (now_jst - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('DELETE FROM tasks WHERE created_at < ?', (limit_date,))
    conn.commit()
    
    rows = conn.execute('SELECT * FROM tasks').fetchall()
    tasks = [dict(r) for r in rows]
    
    def sort_logic(x):
        d = x['deadline']
        if d == "-": return (2, "9999")
        if d < now_str: return (0, d)
        return (1, d)
    tasks.sort(key=sort_logic)
    
    return render_template('index.html', tasks=tasks, username=session['username'], role=session['role'], now=now_str)

@app.route('/add', methods=['POST'])
def add_task():
    if 'username' in session:
        content = request.form['content']
        start = request.form['start'] or "-"
        deadline = request.form['deadline'] or "-"
        created_at = get_now_jst().strftime('%Y-%m-%d %H:%M:%S')
        if content:
            with get_db() as conn:
                conn.execute('INSERT INTO tasks (user, content, start, deadline, created_at) VALUES (?, ?, ?, ?, ?)',
                             (session['username'], content, start, deadline, created_at))
    return redirect(url_for('index'))

@app.route('/extend/<int:task_idx>', methods=['POST'])
def extend_task(task_idx):
    if 'username' in session:
        conn = get_db()
        rows = conn.execute('SELECT * FROM tasks').fetchall()
        temp_tasks = [dict(r) for r in rows]
        now_str = get_now_jst().strftime('%Y-%m-%dT%H:%M')
        temp_tasks.sort(key=lambda x: (0, x['deadline']) if x['deadline'] != "-" and x['deadline'] < now_str else (1, x['deadline']) if x['deadline'] != "-" else (2, "9999"))
        
        if 0 <= task_idx < len(temp_tasks):
            target = temp_tasks[task_idx]
            if session.get('role') == 'admin' or target['user'] == session['username']:
                new_deadline = "-"
                if target['deadline'] != "-":
                    try:
                        curr = datetime.strptime(target['deadline'], '%Y-%m-%dT%H:%M')
                        new_deadline = (curr + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
                    except: pass
                
                with conn:
                    conn.execute('UPDATE tasks SET deadline = ?, created_at = ? WHERE id = ?',
                                 (new_deadline, get_now_jst().strftime('%Y-%m-%d %H:%M:%S'), target['id']))
    return redirect(url_for('index'))

@app.route('/delete/<int:task_idx>', methods=['POST'])
def delete_task(task_idx):
    if 'username' in session:
        conn = get_db()
        rows = conn.execute('SELECT * FROM tasks').fetchall()
        temp_tasks = [dict(r) for r in rows]
        now_str = get_now_jst().strftime('%Y-%m-%dT%H:%M')
        temp_tasks.sort(key=lambda x: (0, x['deadline']) if x['deadline'] != "-" and x['deadline'] < now_str else (1, x['deadline']) if x['deadline'] != "-" else (2, "9999"))
        
        if 0 <= task_idx < len(temp_tasks):
            target = temp_tasks[task_idx]
            if session.get('role') == 'admin' or target['user'] == session['username']:
                with conn:
                    conn.execute('DELETE FROM tasks WHERE id = ?', (target['id'],))
    return redirect(url_for('index'))

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'username' not in session: return redirect(url_for('login'))
    conn = get_db()
    if request.method == 'POST':
        message = request.form.get('message')
        if message:
            with conn:
                # 送信時刻も日本時間で保存
                conn.execute('INSERT INTO chat_messages (username, message, created_at) VALUES (?, ?, ?)',
                             (session['username'], message, get_now_jst().strftime('%m/%d %H:%M')))
            return redirect(url_for('chat'))
    messages = conn.execute('SELECT * FROM chat_messages ORDER BY id DESC LIMIT 50').fetchall()
    return render_template('chat.html', messages=messages, username=session['username'], role=session.get('role'))

@app.route('/delete_chat/<int:msg_id>', methods=['POST'])
def delete_chat(msg_id):
    if session.get('role') == 'admin':
        with get_db() as conn:
            conn.execute('DELETE FROM chat_messages WHERE id = ?', (msg_id,))
    return redirect(url_for('chat'))

@app.route('/update_role/<target_user>', methods=['POST'])
def update_role(target_user):
    if session.get('role') == 'admin':
        new_role = request.form['new_role']
        with get_db() as conn:
            conn.execute('UPDATE users SET role = ? WHERE username = ?', (new_role, target_user))
            conn.commit()
    return redirect(url_for('user_list'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?',
                                (request.form['username'], request.form['password'])).fetchone()
        if user:
            session['username'], session['role'] = user['username'], user['role']
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            with get_db() as conn:
                conn.execute('INSERT INTO users VALUES (?, ?, ?)', (request.form['username'], request.form['password'], 'user'))
            return redirect(url_for('login'))
        except: return "既に使われている名前です"
    return render_template('register.html')

@app.route('/users')
def user_list():
    if session.get('role') != 'admin': return "権限なし"
    users = get_db().execute('SELECT * FROM users').fetchall()
    return render_template('users.html', users=users, username=session['username'])

@app.route('/clear', methods=['POST'])
def clear_tasks():
    if session.get('role') == 'admin':
        with get_db() as conn:
            conn.execute('DELETE FROM tasks')
            conn.commit()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
