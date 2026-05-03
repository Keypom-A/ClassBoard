// static/chat.js

document.addEventListener("DOMContentLoaded", () => {

    // ===== テーマ適用 =====
    if (localStorage.getItem('theme') === 'dark') {
        document.documentElement.classList.add('dark-theme');
    }

    // ===== メニュー開閉 =====
    window.toggleMenu = function () {
        document.getElementById('sidebar').classList.toggle('open');
        document.getElementById('overlay').classList.toggle('open');
    };

    // ===== 初期スクロール =====
    const chatDisplay = document.getElementById('chatDisplay');
    if (chatDisplay) {
        chatDisplay.scrollTop = chatDisplay.scrollHeight;
    }

    // ===== グループ作成 =====
    window.createGroup = function () {
        const name = prompt("新しいグループの合言葉を決めてください");
        if (name) location.href = "/chat?group=" + encodeURIComponent(name);
    };

    // ===== グループ参加 =====
    window.joinGroup = function () {
        const name = prompt("参加するグループの合言葉を入力してください");
        if (name) location.href = "/chat?group=" + encodeURIComponent(name);
    };
    
    async function refreshMessages() {
    const url = window.location.href;
    const res = await fetch(url);
    const html = await res.text();

    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    const newDisplay = doc.getElementById("chatDisplay");

    if (newDisplay) {
        document.getElementById("chatDisplay").innerHTML = newDisplay.innerHTML;

        // 自動スクロール
        const chatDisplay = document.getElementById('chatDisplay');
        chatDisplay.scrollTop = chatDisplay.scrollHeight;
    }
}


    
   let lastUnreadCount = 0;  // ← 追加

   // ===== 未読バッジ更新 =====
    async function updateUnreadBadges() {
        const res = await fetch("/api/unread_count");
        const data = await res.json();

        let totalUnread = 0;

        document.querySelectorAll(".chat-link").forEach(link => {
            const rx = link.dataset.rx;
            const badge = link.querySelector(".badge-notify");
            if (!badge) return;

            const count = data.unread[rx] || 0;
            totalUnread += count;

            badge.style.display = count > 0 ? "inline-flex" : "none";
            if (count > 0) badge.textContent = count;
        });

        // ★ 新着メッセージが来たらメッセージ欄を更新
        if (totalUnread > lastUnreadCount) {
            refreshMessages();
        }
        
        lastUnreadCount = totalUnread;  // ← ここで更新
    }

    setInterval(updateUnreadBadges, 3000);
    updateUnreadBadges();

});
