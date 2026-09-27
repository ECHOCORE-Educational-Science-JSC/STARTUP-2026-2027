# Cài Wisio bridge trên Windows

Bộ này dành cho **Freenove ESP32-S3 Display 2.8 inch**. Máy Windows và robot phải
ở cùng mạng Wi-Fi; máy cần bật bridge khi robot trò chuyện hoặc phát nhạc.

## Cài lần đầu

1. Cài Python 3.11–3.14 từ python.org và bật `Add Python to PATH`.
2. Nhấp đúp `setup_bridge.cmd` để cài các thành phần cần thiết.
3. Nhấp đúp `start_bridge.cmd`, dán Google AI Studio Gemini API key khi được hỏi.
4. Cho phép bridge qua Windows Firewall trên **Private networks**.

Bridge phát tín hiệu tìm kiếm nội bộ qua cổng UDP 8004. Firmware mới tự nhận địa
chỉ máy tính, nên trang Wi-Fi không cần ô OTA URL. Nếu đổi router hoặc IP máy
tính, chỉ cần mở bridge trước rồi khởi động lại robot.

## Cảnh báo cho phụ huynh

1. Bật Xác minh 2 bước cho Gmail dùng để gửi.
2. Tại `https://myaccount.google.com/apppasswords`, tạo mật khẩu ứng dụng tên
   `Wisio Bridge`.
3. Chạy `CONFIGURE_GMAIL_ALERTS.cmd`, nhập Gmail gửi và mã ứng dụng 16 ký tự.
4. Khởi động lại `start_bridge.cmd`.

Địa chỉ nhận được phụ huynh nhập trên trang cấu hình Wi-Fi. Bí mật gửi mail được
DPAPI của Windows mã hóa và chỉ tài khoản Windows đã tạo mới giải mã được.

## Sử dụng

- Wisio gọi người nghe là “bé”, dùng giờ Việt Nam và giữ một giọng nhất quán.
- Nói “Wisio nhớ rằng…” để lưu thông tin trong `wisio_memory.json`; dữ liệu còn
  sau khi tắt robot. Nói “hãy quên…” để xóa.
- Nói “dạy bé tiếng Anh” để học A1–B2 theo kiểu tương tác.
- Nói “phát bài …” để tìm đúng bài và phát qua loa robot. BOOT hoặc chạm màn hình
  sẽ dừng nhạc và mở lại micro.
- Nhấn `Ctrl+C` để dừng bridge.

## Xử lý nhanh

- Không thấy **Wisio**: giữ BOOT hoặc chạm giữ màn hình hơn 3 giây.
- Robot không tìm thấy bridge: xác nhận cùng Wi-Fi và cho phép Python/bridge trên
  Private networks trong Windows Firewall, đặc biệt UDP 8004 và TCP 8000/8003.
- Không có `Gemini Live connected`: kiểm tra Gemini API key và Internet.
- Không phát nhạc: chạy lại `setup_bridge.cmd` rồi khởi động bridge.
- Chẩn đoán mic/loa: chạy `start_bridge_diagnostic.cmd`.

Bridge chỉ phục vụ mạng LAN. Không mở các cổng 8000, 8003 hoặc 8004 trên router
ra Internet.

