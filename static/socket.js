// WebSocket（Socket.IO）に接続
const socket = io();

// 接続確認（デバッグ用）
socket.on("connect", () => {
    console.log("WebSocket connected:", socket.id);
});
