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
    const name = prompt("参加したいグループ名を入力してください");
    if (!name) return;
    window.location.href = `/chat?group=${encodeURIComponent(name)}`;
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

// 5秒ごとに未読数更新
setInterval(updateUnread, 5000);
updateUnread();
