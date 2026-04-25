import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# --- ファイル保存設定 ---
UPLOAD_FOLDER = '/tmp/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'txt'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    if not DATABASE_URL: return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)')
            cur.execute('CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, "user" TEXT, content TEXT, start TEXT, deadline TEXT, created_at TIMESTAMP, priority INTEGER DEFAULT 1, is_notice BOOLEAN DEFAULT FALSE)')
            cur.execute('CREATE TABLE IF NOT EXISTS chat_messages (id SERIAL PRIMARY KEY, username TEXT, message TEXT, created_at TEXT, receiver TEXT DEFAULT \'all\', file_path TEXT)')
            cur.execute("INSERT INTO users (username, password, role) VALUES ('admin', '1234', 'admin') ON CONFLICT DO NOTHING")
        conn.commit()

init_db()

def get_now_jst():
    return datetime.utcnow() + timedelta(hours=9)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('login'))
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute('SELECT role FROM users WHERE username = %s', (session['username'],))
            user_data = cur.fetchone()
            if user_data: session['role'] = user_data['role']
            if session['username'] == 'admin': session['role'] = 'admin'
            now_jst = get_now_jst()
            now_str = now_jst.strftime('%Y-%m-%dT%H:%M')
            cur.execute('SELECT * FROM tasks WHERE is_notice = TRUE ORDER BY created_at DESC')
            notices = [dict(r) for r in cur.fetchall()]
            cur.execute('SELECT * FROM tasks WHERE is_notice = FALSE')
            all_tasks = [dict(r) for r in cur.fetchall()]
    def sort_logic(x):
        d, p = x['deadline'], x.get('priority', 1)
        if d == "-": return (2, -p, "9999")
        if d < now_str: return (0, -p, d)
        return (1, -p, d)
    all_tasks.sort(key=sort_logic)
    return render_template('index.html', notices=notices, tasks=all_tasks, username=session['username'], role=session['role'], now=now_str)

@app.route('/add', methods=['POST'])
def add_task():
    if 'username' not in session: return redirect(url_for('login'))
    role = session.get('role')
    is_notice = True if request.form.get('is_notice') == 'on' and role in ['admin', 'teacher'] else False
    if role == 'teacher' and not is_notice: return "先生は一般タスクの投稿はできません。"
    content, start, deadline = request.form.get('content'), request.form.get('start') or "-", request.form.get('deadline') or "-"
    priority = int(request.form.get('priority', 1))
    if content:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('INSERT INTO tasks ("user", content, start, deadline, created_at, priority, is_notice) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                             (session['username'], content, start, deadline, get_now_jst(), priority, is_notice))
            conn.commit()
    return redirect(url_for('index'))

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') == 'teacher': return "先生はチャットを利用できません。"
    me = session['username']
    partner, group = request.args.get('user'), request.args.get('group')
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            if request.method == 'POST':
                msg, rx, g_name = request.form.get('message'), request.form.get('receiver'), request.form.get('group_name')
                file = request.files.get('file')
                filename = None
                if file and file.filename != '':
                    filename = secure_filename(f"{get_now_jst().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                final_rx = f"grp_{g_name}" if rx == "group" else ("admin" if rx in ["admin", "管理者"] else rx)
                if msg or filename:
                    cur.execute('INSERT INTO chat_messages (username, message, created_at, receiver, file_path) VALUES (%s, %s, %s, %s, %s)',
                                 (me, msg, get_now_jst().strftime('%m/%d %H:%M'), final_rx, filename))
                    conn.commit()
                return redirect(url_for('chat', user=partner, group=group))
            if group: cur.execute('SELECT * FROM chat_messages WHERE receiver = %s ORDER BY id DESC LIMIT 50', (f"grp_{group}",))
            elif partner: cur.execute('SELECT * FROM chat_messages WHERE (username = %s AND receiver = %s) OR (username = %s AND receiver = %s) ORDER BY id DESC LIMIT 50', (me, partner, partner, me))
            else: cur.execute('SELECT * FROM chat_messages WHERE receiver = %s OR username = %s OR receiver = %s ORDER BY id DESC LIMIT 50', ('all', me, me))
            messages = cur.fetchall()
            cur.execute('SELECT username FROM users WHERE username != %s ORDER BY username ASC', (me,))
            user_list = [dict(u) for u in cur.fetchall()]
    return render_template('chat.html', messages=messages, users=user_list, username=me, role=session.get('role'), partner=partner, group=group)

@app.route('/delete/<int:task_id>', methods=['POST'])
def delete_task(task_id):
    if 'username' in session:
        role = session.get('role')
        with get_db() as conn:
            with conn.cursor() as cur:
                if role in ['admin', 'teacher']: cur.execute('DELETE FROM tasks WHERE id = %s', (task_id,))
                else: cur.execute('DELETE FROM tasks WHERE id = %s AND "user" = %s', (task_id, session['username']))
            conn.commit()
    return redirect(url_for('index'))

# --- 管理者専用ルート（ここが抜けていました） ---

@app.route('/users')
def user_list():
    if session.get('role') != 'admin': return "権限なし"
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute('SELECT * FROM users ORDER BY username ASC')
            users = cur.fetchall()
    return render_template('users.html', users=users, username=session['username'])

@app.route('/update_role/<target_user>', methods=['POST'])
def update_role(target_user):
    if session.get('role') == 'admin':
        new_role = request.form['new_role']
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE users SET role = %s WHERE username = %s', (new_role, target_user))
            conn.commit()
    return redirect(url_for('user_list'))

@app.route('/clear', methods=['POST'])
def clear_tasks():
    if session.get('role') == 'admin':
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM tasks')
            conn.commit()
    return redirect(url_for('index'))

# --- 認証系 ---

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

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port)
