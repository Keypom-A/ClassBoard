import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    if not DATABASE_URL: return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)')
            cur.execute('CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, "user" TEXT, content TEXT, start TEXT, deadline TEXT, created_at TIMESTAMP, priority INTEGER DEFAULT 1)')
            cur.execute('CREATE TABLE IF NOT EXISTS chat_messages (id SERIAL PRIMARY KEY, username TEXT, message TEXT, created_at TEXT, receiver TEXT DEFAULT \'all\')')
            cur.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING', ('admin', '1234', 'admin'))
        conn.commit()

init_db()

def get_now_jst():
    return datetime.utcnow() + timedelta(hours=9)

@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('login'))
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute('SELECT role FROM users WHERE username = %s', (session['username'],))
            user_data = cur.fetchone()
            if user_data: session['role'] = user_data['role']
            if session['username'] == 'admin':
                session['role'] = 'admin'
                cur.execute('UPDATE users SET role = %s WHERE username = %s', ('admin', 'admin'))
            
            now_jst = get_now_jst()
            now_str = now_jst.strftime('%Y-%m-%dT%H:%M')
            limit_date = now_jst - timedelta(days=7)
            cur.execute('DELETE FROM tasks WHERE created_at < %s', (limit_date,))
            cur.execute('SELECT * FROM tasks')
            tasks = [dict(r) for r in cur.fetchall()]
    
    def sort_logic(x):
        d, p = x['deadline'], x.get('priority', 1)
        if d == "-": return (2, -p, "9999")
        if d < now_str: return (0, -p, d)
        return (1, -p, d)
    tasks.sort(key=sort_logic)
    return render_template('index.html', tasks=tasks, username=session['username'], role=session['role'], now=now_str)

@app.route('/add', methods=['POST'])
def add_task():
    if 'username' in session:
        # get('priority', 1) とすることで、送られてこなくてもエラー(400)にならないようにします
        content = request.form.get('content')
        start = request.form.get('start') or "-"
        deadline = request.form.get('deadline') or "-"
        priority = int(request.form.get('priority', 1))
        
        if content:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute('INSERT INTO tasks ("user", content, start, deadline, created_at, priority) VALUES (%s, %s, %s, %s, %s, %s)',
                                 (session['username'], content, start, deadline, get_now_jst(), priority))
                conn.commit()
    return redirect(url_for('index'))

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'username' not in session: return redirect(url_for('login'))
    me = session['username']
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            if request.method == 'POST':
                msg, rx = request.form.get('message'), request.form.get('receiver', 'all')
                if msg:
                    cur.execute('INSERT INTO chat_messages (username, message, created_at, receiver) VALUES (%s, %s, %s, %s)',
                                 (me, msg, get_now_jst().strftime('%m/%d %H:%M'), rx))
                    conn.commit()
                return redirect(url_for('chat'))

            cur.execute('SELECT * FROM chat_messages WHERE receiver = %s OR username = %s OR receiver = %s ORDER BY id DESC LIMIT 50', ('all', me, me))
            messages = cur.fetchall()
            cur.execute('SELECT username FROM users WHERE username != %s AND username != %s', (me, 'admin'))
            user_list = cur.fetchall()
            
    return render_template('chat.html', messages=messages, users=user_list, username=me, role=session.get('role'))

@app.route('/extend/<int:task_idx>', methods=['POST'])
def extend_task(task_idx):
    if 'username' in session:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute('SELECT * FROM tasks')
                temp_tasks = [dict(r) for r in cur.fetchall()]
                now_str = get_now_jst().strftime('%Y-%m-%dT%H:%M')
                def task_sort(x):
                    d, p = x['deadline'], x.get('priority', 1)
                    if d == "-": return (2, -p, "9999")
                    if d < now_str: return (0, -p, d)
                    return (1, -p, d)
                temp_tasks.sort(key=task_sort)
                if 0 <= task_idx < len(temp_tasks):
                    target = temp_tasks[task_idx]
                    if session.get('role') == 'admin' or target['user'] == session['username']:
                        new_dl = "-"
                        if target['deadline'] != "-":
                            try:
                                curr = datetime.strptime(target['deadline'], '%Y-%m-%dT%H:%M')
                                new_dl = (curr + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
                            except: pass
                        cur.execute('UPDATE tasks SET deadline = %s, created_at = %s WHERE id = %s', (new_dl, get_now_jst(), target['id']))
            conn.commit()
    return redirect(url_for('index'))

@app.route('/delete/<int:task_idx>', methods=['POST'])
def delete_task(task_idx):
    if 'username' in session:
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute('SELECT * FROM tasks')
                temp_tasks = [dict(r) for r in cur.fetchall()]
                now_str = get_now_jst().strftime('%Y-%m-%dT%H:%M')
                def task_sort(x):
                    d, p = x['deadline'], x.get('priority', 1)
                    if d == "-": return (2, -p, "9999")
                    if d < now_str: return (0, -p, d)
                    return (1, -p, d)
                temp_tasks.sort(key=task_sort)
                if 0 <= task_idx < len(temp_tasks):
                    target = temp_tasks[task_idx]
                    if session.get('role') == 'admin' or target['user'] == session['username']:
                        cur.execute('DELETE FROM tasks WHERE id = %s', (target['id'],))
            conn.commit()
    return redirect(url_for('index'))

@app.route('/delete_chat/<int:msg_id>', methods=['POST'])
def delete_chat(msg_id):
    if session.get('role') == 'admin':
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM chat_messages WHERE id = %s', (msg_id,))
            conn.commit()
    return redirect(url_for('chat'))

@app.route('/update_role/<target_user>', methods=['POST'])
def update_role(target_user):
    if session.get('role') == 'admin':
        new_role = request.form['new_role']
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE users SET role = %s WHERE username = %s', (new_role, target_user))
            conn.commit()
    return redirect(url_for('user_list'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', (request.form['username'], request.form['password']))
                user = cur.fetchone()
                if user:
                    session['username'], session['role'] = user['username'], user['role']
                    return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute('INSERT INTO users VALUES (%s, %s, %s)', (request.form['username'], request.form['password'], 'user'))
                conn.commit()
            return redirect(url_for('login'))
        except: return "既に使われている名前です"
    return render_template('register.html')

@app.route('/users')
def user_list():
    if session.get('role') != 'admin': return "権限なし"
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute('SELECT * FROM users')
            users = cur.fetchall()
    return render_template('users.html', users=users, username=session['username'])

@app.route('/clear', methods=['POST'])
def clear_tasks():
    if session.get('role') == 'admin':
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM tasks')
            conn.commit()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
