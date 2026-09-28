# SỔ TAY HƯỚNG DẪN CÀI ĐẶT & VẬN HÀNH ROBOT AI WISIO

Tài liệu này cung cấp hướng dẫn toàn diện từ A đến Z dành cho các kỹ sư, giáo viên và phụ huynh khi triển khai Robot AI Wisio (EchoCore Ecosystem).

---

## MỤC LỤC
1. [Chuẩn Bị Phần Cứng & Kết Nối Mạch](#1-chuẩn-bị-phần-cứng--kết-nối-mạch)
2. [Cài Đặt Môi Trường & Nạp Firmware](#2-cài-đặt-môi-trường--nạp-firmware)
3. [Cấu Hình Mạng Wi-Fi Cho Robot](#3-cấu-hình-mạng-wi-fi-cho-robot)
4. [Thiết Lập & Khởi Động Bridge Server](#4-thiết-lập--khởi-động-bridge-server)
5. [Hướng Dẫn Tương Tác & Các Câu Lệnh Tiêu Biểu](#5-hướng-dẫn-tương-tác--các-câu-lệnh-tiêu-biểu)
6. [Xử Lý Sự Cố Thường Gặp (Troubleshooting)](#6-xử-lý-sự-cố-thường-gặp-troubleshooting)

---

## 1. Chuẩn Bị Phần Cứng & Kết Nối Mạch

### Danh sách thiết bị:
- **Bo mạch chính:** Freenove ESP32-S3 All-in-One tích hợp màn hình 2.8" LCD cảm ứng (hoặc màn thường kèm nút bấm).
- **Phụ kiện:**
  - Cảm biến chạm TTP223 nối chân Wake-up (hoặc dùng nút BOOT trên bo mạch).
  - Pin Li-Po / Polymer 3.7V dung lượng 5.000mAh - 10.000mAh.
  - Loa và micro tích hợp trên bo mạch.
  - Cáp kết nối máy tính USB Type-C truyền dữ liệu tốt.

---

## 2. Cài Đặt Môi Trường & Nạp Firmware

### Cách 1: Nạp Bằng VS Code (Khuyên dùng)
1. Cài đặt **Visual Studio Code** và cài extension chính thức **ESP-IDF** (Espressif).
2. Mở thư mục `firmware/` trong VS Code.
3. Ở thanh công cụ màu xanh dưới đáy màn hình VS Code:
   - Click chọn **Target**: Chọn `ESP32-S3`.
   - Click chọn **Port**: Chọn cổng COM của bo mạch (ví dụ `COM3`, `COM4`...).
   - Click chọn **Flash Method**: Chọn `UART`.
4. Nhấn nút biểu tượng tia sét ⚡ (**Build, Flash and Monitor**).
5. Chờ quá trình biên dịch và nạp đạt `100% (Hash of data verified.)`. Bo mạch sẽ tự khởi động lại.

### Cách 2: Nạp Bằng Dòng Lệnh (ESP-IDF Terminal)
1. Mở cửa sổ **ESP-IDF 5.5 PowerShell**.
2. Di chuyển vào thư mục:
   ```powershell
   cd firmware
   ```
3. Chạy lệnh biên dịch và nạp:
   ```powershell
   python scripts/build.py freenove-esp32s3-display-2.8-lcd
   idf.py -p COMx flash monitor
   ```
   *(Thay `COMx` bằng cổng COM thực tế)*.

### Khi VS Code mở nhiều Terminal hoặc bo reset liên tục

1. Đóng tất cả terminal có tên **ESP-IDF Monitor**. Monitor giữ cổng COM nên trình nạp không thể mở cổng.
2. Cắm bo trực tiếp vào cổng USB máy tính bằng cáp Type-C ngắn, có truyền dữ liệu. Dòng `Brownout detector was triggered` nghĩa là nguồn 5 V/cáp đang bị sụt áp.
3. Tại thư mục gốc, chạy `FLASH_WISIO_COM5.cmd`. Script đóng các tiến trình Monitor còn sót, build và chỉ nạp firmware ở tốc độ ổn định 115200; script không tự mở Monitor mới.
4. Nếu bo không tự vào chế độ nạp: giữ **BOOT**, bấm **RESET** một lần, thả **BOOT**, rồi chạy lại script.

---

## 3. Cấu Hình Mạng Wi-Fi Cho Robot

1. Sau khi nạp firmware, robot khởi động lên. Nếu chưa có Wi-Fi đã lưu, robot sẽ tự động phát mạng Access Point để cấu hình.
2. Mở điện thoại hoặc laptop, vào mục cài đặt Wi-Fi và tìm mạng:
   ```text
   Wisio-Setup (hoặc EchoCore-WiFi)
   ```
3. Bấm kết nối vào mạng Wi-Fi này. Trang giao diện cấu hình siêu cute sẽ tự động mở lên trên trình duyệt.
   *(Nếu không tự mở, hãy truy cập địa chỉ `http://192.168.4.1`)*.
4. Trên giao diện cấu hình:
   - **Mục 1 (Chọn mạng):** Chọn Wi-Fi gia đình bạn muốn kết nối (danh sách hiển thị kèm cột sóng 3 vạch và nhãn Mạnh/Tốt/Yếu).
   - **Mục 2 (Mật khẩu):** Điền mật khẩu mạng Wi-Fi (có icon con mắt bật/tắt xem mật khẩu).
   - **Mục 3 (Email phụ huynh):** Nhập email của ba mẹ để nhận báo cáo học tập và cảnh báo an toàn của bé.
5. Bấm nút **Kết Nối Wisio! 🚀** -> Robot sẽ lưu thông số vào bộ nhớ Flash NVS, kết nối mạng và chuyển sang trạng thái sẵn sàng.

---

## 4. Thiết Lập & Khởi Động Bridge Server

Bridge Server là cầu nối thông minh giữa Robot Wisio và trí tuệ nhân tạo Google Gemini Live trên máy tính.

### Chuẩn bị:
- Máy tính chạy Windows 10/11 có cài sẵn **Python 3.11 - 3.14**.
- Kết nối máy tính vào **cùng mạng Wi-Fi** với Robot Wisio.
- Lấy miễn phí một mã **Google Gemini API Key** từ [Google AI Studio](https://aistudio.google.com/app/apikey).

### Khởi động Server:
1. Mở thư mục `bridge/`.
2. Kích đúp vào file `start_bridge.cmd`.
3. Khi cửa sổ đen hiện ra:
   - Nhập hoặc dán mã Gemini API Key bạn vừa copy.
   - Nhấn **Enter**.
4. Cửa sổ console sẽ hiện dòng chữ:
   ```text
   Gemini API key verified
   OTA URL: http://<IP>:8003/xiaozhi/ota/
   Xiaozhi WebSocket: ws://<IP>:8000/xiaozhi/v1/
   Keep this window open while using Freenove.
   ```
5. Bật công tắc Robot Wisio. Sau khoảng 2-3 giây, màn hình console sẽ báo:
   ```text
   Wisio connected; protocol v1
   Gemini Live connected (gemini-3.8-live; voice: Zephyr)
   ```
   Robot sẽ cất tiếng chào bé bằng giọng chú thỏ dễ thương!

---

## 5. Hướng Dẫn Tương Tác & Các Câu Lệnh Tiêu Biểu

### 🎨 Học Từ Vựng Trực Quan (Tự Động Hiện Ảnh):
Chỉ cần bé hoặc phụ huynh hỏi về một đồ vật hoặc học từ vựng (hỗ trợ cả tiếng Việt và tiếng Anh):
- *"Wisio ơi, con voi trông như thế nào?"* hoặc *"Dạy bé từ con voi đi!"*
  $\rightarrow$ Wisio: *"Con voi tiếng Anh là Elephant! E-L-E-P-H-A-N-T!"* $\rightarrow$ **Màn hình LCD ngay lập tức hiện bức ảnh chú voi cực nét!**
- *"Con mèo tiếng Anh là gì?"*
  $\rightarrow$ Wisio: *"Con mèo tiếng Anh là Cat! Bé phát âm theo mình nha: Cat!"* $\rightarrow$ **Màn hình hiện ảnh chú mèo siêu đáng yêu!**
- *"Dạy bé từ quả táo đi!"*
  $\rightarrow$ Wisio dạy từ *Apple* và màn hình hiện quả táo đỏ tươi!
- *"Mặt trời, cầu vồng, máy bay, xe ô tô tiếng Anh đọc sao?"*
  $\rightarrow$ Wisio giảng giải và tự động minh họa hình ảnh trực quan trên màn hình.

### 🎵 Nghe Nhạc Thiếu Nhi & Giải Trí (Kèm Ảnh Bìa & Thông Báo):
- *"Wisio ơi mở bài Baby Shark nha!"*
- *"Phát bài Simp Gái 808 của Low G đi Wisio!"*
- *"Mở bài Chú voi con ở Bản Đôn đi!"*
- **Trải nghiệm thông minh:**
  1. Ngay khi nhận lệnh, màn hình hiển thị biểu tượng tìm kiếm.
  2. Khi tìm thấy bài hát, Wisio cất giọng thông báo thân thiện: *"Wisio tìm thấy bài [Tên bài] rồi nè, chúng mình cùng nghe nhé!"*.
  3. Màn hình robot hiển thị **ảnh bìa / thumbnail** của bài hát kèm tiêu đề và ca sĩ.
  4. Nhạc tự động phát mượt mà qua loa.
  5. Khi muốn dừng, chỉ cần nhấn nút BOOT hoặc chạm vào màn hình cảm ứng!
  6. Sau khi bài hát kết thúc tự nhiên, Wisio sẽ nhẹ nhàng hỏi bé có muốn nghe tiếp không.

### 🧠 Trò Chuyện & Ghi Nhớ Thói Quen Của Bé:
- *"Bé tên là Bo, bé 6 tuổi, bé thích màu xanh lá!"*
  $\rightarrow$ Wisio sẽ tự động lưu vào bộ nhớ lâu dài: ngày mai khi bật lại, Wisio sẽ chào bé Bo và nhắc đến màu xanh lá yêu thích của bé!
- Nhận biết cảm xúc: Khi bé buồn khóc hoặc mệt mỏi sau giờ học, Wisio biết hạ giọng êm ái để vỗ về, an ủi bé.

---

## 6. Xử Lý Sự Cố Thường Gặp (Troubleshooting)

| Tình Huống | Nguyên Nhân Có Thể | Cách Khắc Phục |
| :--- | :--- | :--- |
| **Console báo "API key not valid"** | API Key Google sao chép bị thừa khoảng trắng hoặc chưa kích hoạt | Lấy lại key mới tại Google AI Studio và dán lại chính xác. |
| **Robot không kết nối được tới Bridge** | Máy tính và Robot khác dải mạng Wi-Fi hoặc tường lửa Windows chặn cổng 8000 | Kiểm tra xem máy tính và robot đã cùng bắt 1 mạng Wi-Fi chưa; cho phép Python giao tiếp qua Windows Defender Firewall (Private Network). |
| **Màn hình không hiện ảnh** | Mất kết nối Internet hoặc từ khóa quá trừu tượng | Đảm bảo máy tính có kết nối Internet; Wisio hỗ trợ hơn 200+ chủ đề danh từ trực quan quen thuộc của bé. |
| **Muốn đổi mạng Wi-Fi khác** | Robot đã lưu cấu hình mạng cũ | Nhấn giữ nút BOOT trên bo mạch trong 5 giây để xóa cấu hình và đưa robot về lại trang Captive Portal. |
