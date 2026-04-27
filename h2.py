import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# --- Cloudinary 設定 ---
# RenderのEnvironmentに登録した変数から読み込みます
cloudinary.config(
  cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME'),
  api_key = os.environ.get('CLOUDINARY_API_KEY'),
  api_secret = os.environ.get('CLOUDINARY_API_SECRET')
)

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    if not DATABASE_URL: return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT)')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY, "user" TEXT, content TEXT, 
                    start TEXT, deadline TEXT, created_at TIMESTAMP, 
                    priority INTEGER DEFAULT 1, is_notice BOOLEAN DEFAULT FALSE, 
                    file_path TEXT
                )
            ''')
            cur.execute('CREATE TABLE IF NOT EXISTS chat_messages (id SERIAL PRIMARY KEY, username TEXT, message TEXT, created_at TEXT, receiver TEXT DEFAULT \'all\', file_path TEXT)')
            cur.execute("INSERT INTO users (username, password, role) VALUES ('admin', '1234', 'admin') ON CONFLICT DO NOTHING")
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
    
    content = request.form.get('content')
    start = request.form.get('start') or "-"
    deadline = request.form.get('deadline') or "-"
    priority = int(request.form.get('priority', 1))
    
    # --- Cloudinary ファイルアップロード ---
    file = request.files.get('file')
    file_url = None
    if file and file.filename != '':
        upload_result = cloudinary.uploader.upload(file,resource_type="auto")
        file_url = upload_result['secure_url']

    if content or file_url:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO tasks ("user", content, start, deadline, created_at, priority, is_notice, file_path) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (session['username'], content, start, deadline, get_now_jst(), priority, is_notice, file_url))
            conn.commit()
    return redirect(url_for('index'))

@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'username' not in session: return redirect(url_for('login'))
    if session.get('role') == 'teacher': return "先生はチャットを利用できません。"
    
    me = session['username']
    partner = request.args.get('user')
    group = request.args.get('group')
    
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # 1. ユーザーリスト取得
            cur.execute("SELECT username FROM users WHERE role = 'student'")
            users = cur.fetchall()

            # 2. 通知用バッジ
            last_ids = {}
            try:
                cur.execute("SELECT receiver, MAX(id) as last_id FROM chat_messages GROUP BY receiver")
                for r in cur.fetchall():
                    last_ids[r['receiver']] = r['last_id']
            except:
                conn.rollback()

            # 3. グループリスト取得
            cur.execute("SELECT DISTINCT receiver FROM chat_messages WHERE receiver LIKE 'grp_%%'")
            my_groups = [r['receiver'].replace('grp_', '') for r in cur.fetchall()]
            if group and group not in my_groups:
                my_groups.append(group)

            # --- POST: メッセージ・ファイル送信 ---
                     # --- POST処理（送信時） ---
            if request.method == 'POST':
                msg_content = request.form.get('message', '')
                file = request.files.get('file')
                file_url = None

                # Cloudinaryへアップロード
                if file and file.filename != '':
                    try:
                        res = cloudinary.uploader.upload(file, resource_type="auto")
                        file_url = res.get('secure_url')
                    except Exception as e:
                        print(f"Cloudinary Error: {e}")

                target = f"grp_{group}" if group else (partner if partner else "all")
                
                # 文字列に変換した現在時刻
                now_str = get_now_jst().strftime('%Y-%m-%d %H:%M:%S')

                if msg_content or file_url:
                    try:
                        # init_dbの定義に合わせて、username, message, file_path, created_at を使用
                        cur.execute("""
                            INSERT INTO chat_messages (username, message, receiver, file_path, created_at) 
                            VALUES (%s, %s, %s, %s, %s)
                        """, (me, msg_content, target, file_url, now_str))
                        conn.commit()
                    except Exception as e:
                        print(f"DB Insert Error: {e}")
                        conn.rollback()

                return redirect(url_for('chat', user=partner, group=group))


            # --- GET: メッセージ表示用データ取得 ---
            target = f"grp_{group}" if group else (partner if partner else "all")
            
            # 全てのカラムを取得して、後で安全に処理
            if target == "all" or target.startswith("grp_"):
                cur.execute('SELECT * FROM chat_messages WHERE receiver = %s ORDER BY id ASC LIMIT 50', (target,))
            else:
                cur.execute('''
                    SELECT * FROM chat_messages 
                    WHERE (username = %s AND receiver = %s) OR (username = %s AND receiver = %s)
                    OR (sender = %s AND receiver = %s) OR (sender = %s AND receiver = %s)
                    ORDER BY id ASC LIMIT 50
                ''', (me, target, target, me, me, target, target, me))
            
            raw_messages = cur.fetchall()
            
            # HTMLが期待するキー名 (username, message, created_at) に統一して変換
            messages = []
            for m in raw_messages:
                messages.append({
                    'username': m.get('username') or m.get('sender', 'Unknown'),
                    'message': m.get('message') or m.get('content', ''),
                    'file_path': m.get('file_path'),
                    'created_at': m.get('created_at', '')
                })

    return render_template('chat.html', 
                           messages=messages, 
                           partner=partner, 
                           group=group, 
                           my_groups=my_groups, 
                           users=users, 
                           last_ids=last_ids, 
                           username=me)

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
                    cur.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (request.form['username'], request.form['password'], 'user'))
                conn.commit()
            return redirect(url_for('login'))
        except: return "既に使われている名前です"
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
