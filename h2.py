import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime, timedelta
import cloudinary
import cloudinary.uploader
import json
import urllib.request
from flask import jsonify
import requests

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
            # 1. 既存テーブルの作成
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
            
            # 2. 時間割テーブルの再構築（一度消して新しい構造にする）
            #cur.execute('DROP TABLE IF EXISTS timetable') # 一度リセット
            cur.execute('''
                CREATE TABLE IF NOT EXISTS timetable (
                id SERIAL PRIMARY KEY,
                date TEXT,              -- 日付がある場合はその日限定
                day_of_week INTEGER,    -- 0〜4。日付がない場合はテンプレとして扱う
                period INTEGER,
                subject TEXT,
                is_changed BOOLEAN DEFAULT FALSE,
                UNIQUE (date, period),
                UNIQUE (day_of_week, period)
              )
          ''')
            
            conn.commit()


init_db()


def get_now_jst():
    return datetime.utcnow() + timedelta(hours=9)

import json
import urllib.request
from flask import jsonify

@app.route("/api/unread_count")
def unread_count():
    if "username" not in session:
        return jsonify({"error": "not logged in"}), 403

    me = session["username"]

    with get_db() as conn:
        with conn.cursor() as cur:

            # ★ 全体チャット（receiver='all'）の未読数
            cur.execute("""
                UPDATE chat_messages
                SET is_read = TRUE
                WHERE receiver = 'all' AND is_read = FALSE
            """)
            conn.commit()

            # ★ DM の未読数（相手ごと）
            cur.execute("""
                SELECT username, COUNT(*)
                FROM chat_messages
                WHERE receiver = 'all'
                ORDER BY created_at ASC
            """)
            messages = cr.fetchall()
      return render_template("chat.html",messages=messges, username=me)

    # ★ unread_map に全体チャットも追加
    unread_map = {"all": unread_all}
    for row in rows:
        unread_map[row[0]] = row[1]

    return jsonify({"unread": unread_map})

@app.route("/api/weather")
def get_weather_api():
    try:
        # 郡山市のピンポイント座標（Open-Meteo API）
        url="https://api.open-meteo.com/v1/forecast?latitude=37.4&longitude=140.38&current=temperature_2m,wind_speed_10m,weathercode&daily=weathercode,temperature_2m_max,temperature_2m_min&forecast_days=3&timezone=Asia/Tokyo"

        # サーバー側でデータを取得
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        # 現在の天気
        current = {
            "temp": round(data["current"]["temperature_2m"]),
            "code": data["current"]["weathercode"]
        }

        # 3日分の予報を作る
        # hourly の 0時データを使う（1日1個）
        forecast = []
        labels = ["今日", "明日", "明後日"]

        for i in range(3):
            # 0時 → 24時 → 48時
            forecast.append({
                "label": labels[i],
                "max": round(data["daily"]["temperature_2m_max"][i]),
                "min": round(data["daily"]["temperature_2m_min"][i]),
                "code": data["daily"]["weathercode"][i]
            })

        return jsonify({
            "current": current,
            "forecast": forecast
        })

    except Exception as e:
        print(f"Weather Error: {e}")
        return jsonify({"error": "取得失敗"}), 500

@app.route("/")
def index():
    if "username" not in session:
        return redirect(url_for("login"))

    # --- 既存のDB処理 ---
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute(
                "SELECT role FROM users WHERE username = %s",
                (session["username"],),
            )
            user_data = cur.fetchone()
            if user_data:
                session["role"] = user_data["role"]

            now_jst = get_now_jst()
            now_str = now_jst.strftime("%Y-%m-%dT%H:%M")

            cur.execute(
                "SELECT * FROM tasks WHERE is_notice = TRUE ORDER BY created_at DESC"
            )
            notices = [dict(r) for r in cur.fetchall()]
            cur.execute("SELECT * FROM tasks WHERE is_notice = FALSE")
            all_tasks = [dict(r) for r in cur.fetchall()]

    def sort_logic(x):
        d, p = x["deadline"], x.get("priority", 1)
        if d == "-":
            return (2, -p, "9999")
        if d < now_str:
            return (0, -p, d)
        return (1, -p, d)

    all_tasks.sort(key=sort_logic)

    return render_template(
        "index.html",
        notices=notices,
        tasks=all_tasks,
        username=session["username"],
        role=session["role"],
        now=now_str,
    )
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
    if 'username' not in session: 
        return redirect(url_for('login'))
    if session.get('role') == 'teacher': 
        return "先生はチャットを利用できません。"
    
    me = session['username']
    partner = request.args.get('user')
    group = request.args.get('group')
    
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:

            # 1. ユーザーリスト取得
            cur.execute("SELECT username, role FROM users")
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

            # --- 既読処理（ここが修正ポイント） ---
            if partner:
                cur.execute("""
                    UPDATE chat_messages
                    SET is_read = TRUE
                    WHERE receiver = %s AND username = %s
                """, (me, partner))
                conn.commit()

            # --- POST処理（送信時） ---
            if request.method == 'POST':
                msg_content = request.form.get('message', '')
                file = request.files.get('file')
                file_url = None

                if file and file.filename != '':
                    try:
                        res = cloudinary.uploader.upload(file, resource_type="auto")
                        file_url = res.get('secure_url')
                    except Exception as e:
                        print(f"Cloudinary Error: {e}")

                target = f"grp_{group}" if group else (partner if partner else "all")
                now_str = get_now_jst().strftime('%m/%d %H:%M')

                if msg_content or file_url:
                    cur.execute("""
                        INSERT INTO chat_messages (username, message, receiver, file_path, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (me, msg_content, target, file_url, now_str))
                    conn.commit()

                return redirect(url_for('chat', user=partner, group=group))

            # --- GET処理（表示時） ---
            target = f"grp_{group}" if group else (partner if partner else "all")

            if target == "all" or target.startswith("grp_"):
                cur.execute("""
                    SELECT * FROM chat_messages
                    WHERE receiver = %s
                    ORDER BY id DESC LIMIT 50
                """, (target,))
            else:
                cur.execute("""
                    SELECT * FROM chat_messages
                    WHERE (username = %s AND receiver = %s)
                       OR (username = %s AND receiver = %s)
                    ORDER BY id DESC LIMIT 50
                """, (me, target, target, me))

            raw_messages = cur.fetchall()

            messages = []
            for m in reversed(raw_messages):
                messages.append({
                    'username': m.get('username') or m.get('sender', 'Unknown'),
                    'message': m.get('message') or m.get('content', ''),
                    'file_path': m.get('file_path'),
                    'created_at': m.get('created_at', '')
                })

    return render_template(
        'chat.html',
        messages=messages,
        partner=partner,
        group=group,
        my_groups=my_groups,
        users=users,
        last_ids=last_ids,
        username=me
    )

@app.route('/timetable', methods=['GET', 'POST'])
def timetable():
    if 'username' not in session: return redirect(url_for('login'))
    
    # 💡 修正ポイント：今日から「土日を除いた5日間」を作成
    week_dates = []
    week_labels = []
    jp_days = ["月", "火", "水", "木", "金", "土", "日"]
    
    d = get_now_jst().date()
    while len(week_dates) < 5:
        if d.weekday() < 5:  # 月〜金ならリストに追加
            week_dates.append(d.strftime('%Y-%m-%d'))
            # 曜日名と、DBの曜日ID(0=月, 1=火...)を保存
            week_labels.append({"name": jp_days[d.weekday()], "idx": d.weekday()})
        d += timedelta(days=1)

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # --- POST処理（保存） ---
            if request.method == 'POST' and session.get('role') in ['admin', 'teacher']:
                date, day, period, subject = request.form.get('date'), request.form.get('day'), request.form.get('period'), request.form.get('subject')
                is_changed = True if request.form.get('is_changed') == 'true' else False
                if is_changed:
                    cur.execute('INSERT INTO timetable (date, period, subject, is_changed) VALUES (%s, %s, %s, True) ON CONFLICT (date, period) DO UPDATE SET subject = EXCLUDED.subject, is_changed = True', (date, period, subject))
                else:
                    cur.execute('DELETE FROM timetable WHERE date = %s AND period = %s', (date, period))
                    cur.execute('INSERT INTO timetable (day_of_week, period, subject, is_changed) VALUES (%s, %s, %s, False) ON CONFLICT (day_of_week, period) DO UPDATE SET subject = EXCLUDED.subject, is_changed = False', (day, period, subject))
                conn.commit()
                return redirect(url_for('timetable'))

            # 1. テンプレ（黒）の取得
            cur.execute("SELECT * FROM timetable WHERE day_of_week IS NOT NULL")
            table = {}
            for r in cur.fetchall():
                table[(int(r['day_of_week']), int(r['period']))] = {'subject': r['subject']}

            # 2. 変更分（赤）の取得
            cur.execute("SELECT * FROM timetable WHERE date::text = ANY(%s)", (week_dates,))
            changed_data = {}
            for r in cur.fetchall():
                d_str = r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date'])
                changed_data[(d_str, int(r['period']))] = {'subject': r['subject']}

    # 💡 重要：week_labels を HTML に渡す
    return render_template('timetable.html', 
                           table=table, 
                           changed_data=changed_data, 
                           week_dates=week_dates, 
                           week_labels=week_labels, 
                           days_names=[l['name'] for l in week_labels], 
                           periods=range(1, 7), 
                           role=session.get('role'))


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

@app.route('/schedule', methods=['GET', 'POST'])
def schedule():
    if 'username' not in session: return redirect(url_for('login'))
    
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # POST: 予定表PDFのアップロード（管理者のみ）
            if request.method == 'POST' and session.get('role') in ['admin', 'teacher']:
                file = request.files.get('file')
                if file and file.filename != '':
                    try:
                        # 'latest_schedule' という名前（Public ID）で上書き保存する設定
                        res = cloudinary.uploader.upload(
                            file, 
                            public_id="latest_schedule", 
                            overwrite=True, 
                            resource_type="auto"
                        )
                        file_url = res.get('secure_url')
                        # DBにURLを保存（なければ作成、あれば更新）
                        cur.execute('''
                            INSERT INTO tasks ("user", content, is_notice, file_path, created_at)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                        ''', (session['username'], "【最新】週・月間予定表", True, file_url, get_now_jst()))
                        # ※今回はシンプルに特定のPublic IDでCloudinaryから呼ぶ形にします
                        conn.commit()
                    except Exception as e:
                        print(f"Schedule Upload Error: {e}")
                return redirect(url_for('schedule'))

            # GET: 表示用URLの取得（CloudinaryのURLを直接生成）
            # 固定のIDでアップロードしているので、URLも推測可能
            schedule_url = cloudinary.CloudinaryImage("latest_schedule").build_url(resource_type="image")
            # PDFの場合は resource_type="raw" や "auto" の対応が必要なため、
            # 安全に secure_url を取得するロジックにしましょう

    return render_template('schedule.html', role=session.get('role'))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
