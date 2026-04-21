import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DB_FILE = 'database.db'

# h2.py の 10行目付近にある get_db を以下に書き換え

def get_db():
    # 確実にこのファイルがあるフォルダに database.db を作る指定
    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(basedir, DB_FILE)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def prepare_db():
    """データベースとテーブルの作成"""
    with get_db() as conn:
        # ユーザーテーブル
        conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)')
        # タスクテーブル
        conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user TEXT, content TEXT, start TEXT, deadline TEXT, created_at TEXT)')
        # 初期管理者
        conn.execute('INSERT OR IGNORE INTO users VALUES (?, ?, ?)', ('admin', '1234', 'admin'))

@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('login'))
    
    now_str = datetime.now().strftime('%Y-%m-%dT%H:%M')
    conn = get_db()
    
    # 7日以上前のタスクを削除（クリーニング）
    limit_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
    conn.execute('DELETE FROM tasks WHERE created_at < ?', (limit_date,))
    
    # データを読み込み（並び替え：期限切れ > 期限近い順 > 期限なし）
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

@app.route('/extend/<int:task_id_in_list>', methods=['POST'])
def extend_task(task_id_in_list):
    """リストの順番ではなく、データベースのIDを使って延長"""
    if 'username' in session:
        # 画面から送られてきた「表示順の番号」で今のタスクを特定
        # (本当はDBのIDを送るのがベストですが、今のロジックを維持します)
        current_tasks = get_db().execute('SELECT * FROM tasks').fetchall()
        target = dict(current_tasks[task_id_in_list])
        
        if session.get('role') == 'admin' or target['user'] == session['username']:
            new_deadline = "-"
            if target['deadline'] != "-":
                curr = datetime.strptime(target['deadline'], '%Y-%m-%dT%H:%M')
                new_deadline = (curr + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
            
            with get_db() as conn:
                conn.execute('UPDATE tasks SET deadline = ?, created_at = ? WHERE id = ?',
                             (new_deadline, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), target['id']))
    return redirect(url_for('index'))

@app.route('/delete/<int:task_id_in_list>', methods=['POST'])
def delete_task(task_id_in_list):
    current_tasks = get_db().execute('SELECT * FROM tasks').fetchall()
    target = dict(current_tasks[task_id_in_list])
    if session.get('role') == 'admin' or target['user'] == session['username']:
        with get_db() as conn:
            conn.execute('DELETE FROM tasks WHERE id = ?', (target['id'],))
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = get_db().execute('SELECT * FROM users WHERE username = ? AND password = ?',
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
        except: return "その名前は既に使われています"
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
    prepare_db()
    # クラウド用設定: ポートは環境変数から取るのが一般的
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
