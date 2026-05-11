// ================================
//  chat.js（ClassBoard ページ遷移型 完全版）
// ================================

// ================================
// グループ作成
// ================================
function createGroup() {
    const name = prompt("作成するグループ名を入力してください");
    if (!name) return;
    window.location.href = `/chat?group=${encodeURIComponent(name)}`;
}

// ================================
// グループ参加
// ================================
function joinGroup() {
    const name = prompt("グループ名を入力してください");
    if (!name) return;

    fetch("/api/join_group", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group: name })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            window.location.href = `/chat?group=${name}`;
        } else {
            alert("参加に失敗しました");
        }
    });
}

// ================================
// スマホメニュー開閉
// ================================
function toggleMenu() {
    document.querySelector(".sidebar").classList.toggle("open");
    document.querySelector(".overlay").classList.toggle("open");
}

// ================================
// メッセージ削除
// ================================
document.addEventListener("click", function (e) {
    if (e.target.classList.contains("delete-btn")) {
        const id = e.target.dataset.id;

        if (!confirm("このメッセージを削除しますか？")) return;

        fetch("/api/delete_message", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                location.reload();
            } else {
                alert("削除に失敗しました");
            }
        });
    }
});

// ================================
// グループ作成（重複定義修正済）
// ================================
function createGroup() {
    const name = prompt("作成するグループ名を入力してください");
    if (!name) return;

    fetch("/api/create_group", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group: name })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            window.location.href = `/chat?group=${name}`;
        } else {
            alert("作成に失敗しました");
        }
    });
}

// ================================
// グループ退出
// ================================
function leaveGroup(group) {
    if (!confirm(`${group} から退出しますか？`)) return;

    fetch("/api/leave_group", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            window.location.href = "/chat";
        } else {
            alert("退出に失敗しました");
        }
    });
}

// ================================
// メンバー一覧開閉
// ================================
function toggleMembers() {
    const list = document.getElementById("member-list");
    if (list.style.display === "none") {
        list.style.display = "block";
    } else {
        list.style.display = "none";
    }
}

// ================================
// メンバー一覧更新
// ================================
function updateMembers() {
    const list = document.getElementById("member-list");
    if (!list) return;

    fetch("/members?group=" + currentGroup)
        .then(res => res.json())
        .then(data => {
            list.innerHTML = "";

            data.forEach(m => {
                const username = m[0];
                const online = m[1];

                const dot = online === 1
                    ? '<span class="online-dot"></span>'
                    : '<span class="offline-dot"></span>';

                list.innerHTML += `
                    <div class="member-item" onclick="location.href='/chat?user=${username}'">
                        ${dot}
                        ${username}
                    </div>
                `;
            });
        });
}

// ================================
// 未読バッジ更新
// ================================
function updateUnread() {
    fetch("/api/unread_count")
        .then(res => res.json())
        .then(data => {

            // 全体チャット
            const allBadge = document.querySelector('[href="/chat"] .badge-notify');
            if (allBadge) {
                if (data.unread_all > 0) {
                    allBadge.style.display = "inline-block";
                    allBadge.textContent = data.unread_all;
                } else {
                    allBadge.style.display = "none";
                }
            }

            // グループ
            for (const g in data.unread_group) {
                const el = document.querySelector(`[href="/chat?group=${g}"] .badge-notify`);
                if (el) {
                    if (data.unread_group[g] > 0) {
                        el.style.display = "inline-block";
                        el.textContent = data.unread_group[g];
                    } else {
                        el.style.display = "none";
                    }
                }
            }

            // DM
            for (const u in data.unread_dm) {
                const el = document.querySelector(`[href="/chat?user=${u}"] .badge-notify`);
                if (el) {
                    if (data.unread_dm[u] > 0) {
                        el.style.display = "inline-block";
                        el.textContent = data.unread_dm[u];
                    } else {
                        el.style.display = "none";
                    }
                }
            }
        });
}

// ================================
// ★★★ WebSocket 接続（重要）★★★
// ================================
const socket = io({
    transports: ["websocket"]
});

socket.on("connect", () => {
    console.log("WebSocket connected:", socket.id);

    socket.emit("join_room", {
        group: currentGroup,
        partner: currentPartner
    });
});

// ================================
// ★★★ WebSocket 受信処理（STEP4）★★★
// ================================
socket.on("chat_message", (msg) => {
    console.log("受信:", msg);

    const display = document.querySelector(".chat-display");
    if (!display) return;

    const row = document.createElement("div");
    row.classList.add("msg-row");

    // 自分のメッセージ
    if (msg.username === username) {
        row.innerHTML = `
            <div class="message my-msg">
                <div class="user-name">
                    ${msg.username}
                    <span class="msg-time">${msg.created_at}</span>
                </div>
                <div class="msg-text">${msg.text}</div>
            </div>
        `;
    }
    // 他人のメッセージ
    else {
        row.innerHTML = `
            <div class="message other-msg">
                <div class="user-name">
                    ${msg.username}
                    <span class="msg-time">${msg.created_at}</span>
                </div>
                <div class="msg-text">${msg.text}</div>
            </div>
        `;
    }

    display.appendChild(row);

    // 自動スクロール
    display.scrollTop = display.scrollHeight;
});


// ================================
// ★★★ WebSocket 送信処理（STEP3 完成）★★★
// ================================
document.getElementById("chat-form").addEventListener("submit", function(e) {
    e.preventDefault();

    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text) return;

    socket.emit("chat_message", {
        text: text,
        group: currentGroup,
        partner: currentPartner,
    });

    input.value = "";
});


// ================================
// 未読数更新
// ================================
setInterval(updateUnread, 5000);
updateUnread();
