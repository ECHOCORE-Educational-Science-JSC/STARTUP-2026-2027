# HƯỚNG DẪN KHỞI CHẠY VÀ SỬ DỤNG BRIDGE SERVER CHO BÉ WISIO

Tài liệu này hướng dẫn cách chạy **Xiaozhi Gemini Live Bridge** trên máy tính để kết nối Robot Wisio (ESP32-S3) với trí tuệ nhân tạo Google Gemini Live, phục vụ tính năng đàm thoại giọng nói song ngữ và hiển thị hình ảnh bài học trực quan trên màn hình LCD.

---

## 1. Tổng Quan Kiến Trúc

- **Robot Wisio (Phần cứng ESP32-S3 LCD 2.8"):** Thu âm thanh từ micro, gửi luồng âm thanh Opus qua mạng Wi-Fi tới máy tính, nhận âm thanh giọng nói và hình ảnh từ máy tính để hiển thị lên màn hình.
- **Bridge Server (Máy tính chạy Python):**
  - Kết nối trực tiếp 2 chiều (Bidirectional WebSocket) với **Google Gemini Live**.
  - Xử lý giọng nói siêu tốc (độ trễ dưới 1 giây), biểu cảm và cử chỉ của Wisio.
  - **Bộ hiển thị hình ảnh học tập (`show_learning_image`):** Khi bé học từ vựng (ví dụ con mèo, quả táo, con chó, thanh long...), Bridge tự động tìm kiếm hình ảnh giáo dục chuẩn xác trên Wikipedia, dùng thư viện đồ họa Pillow thu nhỏ và tối ưu bảng màu cho màn hình LCD 320x240, xác minh độ an toàn và chất lượng bằng AI Gemini 2.0 Flash, sau đó truyền trực tiếp xuống màn hình robot.
  - **Phát nhạc (`play_song`):** Tìm và phát các bài hát thiếu nhi, nhạc tiếng Anh trực tiếp qua loa robot.
  - **Trí nhớ dài hạn (`remember_user_fact`):** Ghi nhớ tên, tuổi, sở thích của bé qua nhiều lần khởi động.

---

## 2. Cách Khởi Động Bridge Server

### Cách 1: Chạy Bằng File Thực Thi Tự Động (Khuyên dùng)
1. Mở thư mục `xiaozhi-gemini-live`.
2. Kích đúp vào file:
   ```text
   start_bridge.cmd
   ```
3. Màn hình console hiện ra yêu cầu nhập API Key:
   ```text
   Paste Google AI Studio Gemini API key only (hidden):
   ```
4. Copy API Key của bạn từ [Google AI Studio](https://aistudio.google.com/app/apikey), click chuột phải vào cửa sổ console để dán (lưu ý ký tự sẽ ẩn để bảo mật), rồi nhấn **Enter**.
5. Server sẽ kiểm tra tính hợp lệ của key và hiển thị:
   ```text
   Gemini API key verified
   OTA URL: http://<IP-MÁY-TÍNH>:8003/xiaozhi/ota/
   Xiaozhi WebSocket: ws://<IP-MÁY-TÍNH>:8000/xiaozhi/v1/
   Keep this window open while using Freenove.
   ```

### Cách 2: Chạy Bằng Dòng Lệnh (Terminal)
Nếu bạn muốn chạy trong môi trường ảo `.venv`:
```powershell
cd c:\Users\daole\Documents\Codex\2026-09-18\gi-t-i-mu-n-x-2\xiaozhi-gemini-live
.venv\Scripts\python.exe bridge.py
```

---

## 3. Kết Nối Robot Với Máy Tính

1. Đảm bảo **Máy tính** và **Robot Wisio** cùng kết nối chung một mạng Wi-Fi (hoặc phát Wi-Fi từ điện thoại cho cả 2 cùng bắt).
2. Bật công tắc nguồn Robot Wisio.
3. Robot sẽ tự động phát hiện Bridge Server trên mạng nội bộ qua giao thức UDP Discovery và kết nối vào WebSocket.
4. Màn hình console sẽ báo:
   ```text
   Wisio connected; protocol v1
   Gemini Live connected (gemini-3.8-live; voice: Zephyr)
   ```
5. Wisio sẽ cất tiếng chào bé bằng giọng chú thỏ dễ thương: *"Chào bé, mình là Wisio đây! Hôm nay bé muốn học tiếng Anh hay trò chuyện cùng mình nè?"*.

---

## 4. Trải Nghiệm Các Tính Năng Độc Đáo

### 🎨 Học Từ Vựng Có Hình Minh Họa Rõ Nét 100%:
- Bé hoặc phụ huynh chỉ cần nói:
  - *"Wisio ơi, con mèo tiếng Anh là gì?"*
  - *"Dạy bé từ quả táo đi Wisio!"*
  - *"Wisio cho bé xem con chó trông như thế nào?"*
  - *"Quả thanh long tiếng Anh nói sao?"*
- Wisio sẽ phát âm chuẩn, giải thích nghĩa, và **ngay lập tức hiển thị bức ảnh rõ nét của đồ vật/con vật đó trên màn hình LCD 2.8"**, đồng thời đặt câu hỏi tương tác để bé nhớ lâu hơn!

### 🎵 Nghe Nhạc Thiếu Nhi:
- Nói: *"Wisio ơi mở bài Chú voi con ở Bản Đôn nha!"* hoặc *"Mở bài Baby Shark đi!"*.
- Robot sẽ tải bài hát và phát trực tiếp qua loa.

### 💖 Tâm Sự & Học Tập Thông Minh:
- Wisio nhận biết cảm xúc (vui, buồn, mệt mỏi) để an ủi, vỗ về bé.
- Tự động ghi nhớ những điều bé thích để nhắc lại trong những ngày tiếp theo.
