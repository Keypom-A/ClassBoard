import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# クラウドで確実に書き込みができる場所を指定
DB_PATH = "/tmp/classboard.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    # 接続のたびにテーブルを確認（エラー防止）
    conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, content TEXT, start TEXT, deadline TEXT, created_at TEXT)')
    # 管理者(admin/1234)を確実に作成
    conn.execute('INSERT OR IGNORE INTO users VALUES (?, ?, ?)', ('admin', '1234', 'admin'))
    conn.commit()
    return conn

@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('login'))
    
    now_str = datetime.now().strftime('%Y-%m-%dT%H:%M')
    conn = get_db()
    
    # 7日経過したタスクを削除
    limit_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('DELETE FROM tasks WHERE created_at < ?', (limit_date,))
    conn.commit()
    
    # データを取得して並び替え
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
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
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
        # 並び替え後の順番で対象を特定
        temp_tasks = [dict(r) for r in rows]
        now_str = datetime.now().strftime('%Y-%m-%dT%H:%M')
        temp_tasks.sort(key=lambda x: (0, x['deadline']) if x['deadline'] != "-" and x['deadline'] < now_str else (1, x['deadline']) if x['deadline'] != "-" else (2, "9999"))
        
        if 0 <= task_idx < len(temp_tasks):
            target = temp_tasks[task_idx]
            if session.get('role') == 'admin' or target['user'] == session['username']:
                new_deadline = "-"
                if target['deadline'] != "-":
                    curr = datetime.strptime(target['deadline'], '%Y-%m-%dT%H:%M')
                    new_deadline = (curr + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
                
                with conn:
                    conn.execute('UPDATE tasks SET deadline = ?, created_at = ? WHERE id = ?',
                                 (new_deadline, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), target['id']))
    return redirect(url_for('index'))

@app.route('/delete/<int:task_idx>', methods=['POST'])
def delete_task(task_idx):
    if 'username' in session:
        conn = get_db()
        rows = conn.execute('SELECT * FROM tasks').fetchall()
        temp_tasks = [dict(r) for r in rows]
        # 並び替え後の順番で削除対象を特定
        now_str = datetime.now().strftime('%Y-%m-%dT%H:%M')
        temp_tasks.sort(key=lambda x: (0, x['deadline']) if x['deadline'] != "-" and x['deadline'] < now_str else (1, x['deadline']) if x['deadline'] != "-" else (2, "9999"))
        
        if 0 <= task_idx < len(temp_tasks):
            target = temp_tasks[task_idx]
            if session.get('role') == 'admin' or target['user'] == session['username']:
                with conn:
                    conn.execute('DELETE FROM tasks WHERE id = ?', (target['id'],))
    return redirect(url_for('index'))

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
    return render_template('users.html', users=users)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
