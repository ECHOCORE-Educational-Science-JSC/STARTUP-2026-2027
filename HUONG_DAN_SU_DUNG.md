# SỔ TAY HƯỚNG DẪN CÀI ĐẶT & VẬN HÀNH ROBOT AI WISIO
### Hệ Sinh Thái EchoCore - Educational Science JSC
*Phiên bản: 2.0 (Cập nhật tháng 09/2026 - Tích hợp Gemini 2.0 / 3.8 Live, Music Player V2 & Giao Diện Cấu Hình Cute)*

---

## 📦 1. TỔNG QUAN GÓI PHẦN MỀM (DISTRIBUTION PACKAGE)

Thư mục này đã được đóng gói trọn vẹn để bất kỳ thành viên nào trong đội ngũ cũng có thể triển khai Robot Wisio ngay lập tức mà không cần cài đặt phức tạp:

| Thư Mục / Tập Tin | Ý Nghĩa & Vai Trò |
| :--- | :--- |
| **`FLASH_FIRMWARE.cmd`** | **Công cụ nạp Firmware 1-Click:** Tự động dò tìm cổng COM và nạp firmware vào ESP32-S3 trong vài giây. |
| **`START_BRIDGE.cmd`** | **Khởi động Bridge Server 1-Click:** Tự động tạo môi trường ảo Python và khởi chạy server kết nối Gemini Live. |
| **`firmware_bin/`** | Chứa toàn bộ các file binary đã biên dịch sẵn (`xiaozhi.bin`, `bootloader.bin`, `assets`, `partition-table`). |
| **`bridge/`** | Toàn bộ mã nguồn máy chủ Bridge (xử lý âm thanh 24kHz, AI Gemini Live, tìm kiếm nhạc, tải ảnh từ vựng trực quan). |
| **`firmware/`** | Toàn bộ mã nguồn C/C++ firmware ESP-IDF (dành cho lập trình viên muốn tinh chỉnh, thêm tính năng hoặc tùy biến bo mạch). |
| **`HUONG_DAN_SU_DUNG.md`** | Tài liệu hướng dẫn này. |

---

## 🛠️ 2. CHUẨN BỊ PHẦN CỨNG

1. **Bo mạch chính:** Freenove ESP32-S3 tích hợp màn hình LCD 2.8" (320x240) có loa và micro.
2. **Cáp kết nối:** Cáp USB Type-C có chức năng truyền dữ liệu (Data Cable).
3. **Nguồn cấp:** Cổng USB máy tính hoặc củ sạc 5V-2A ổn định.

---

## ⚡ 3. HƯỚNG DẪN NẠP FIRMWARE CHO ROBOT

### 👉 Cách 1: Nạp Nhanh Bằng Công Cụ Tự Động (Khuyên dùng - 10 Giây)
Không cần cài đặt ESP-IDF hay CMake nặng nề:
1. Cắm cáp USB nối bo mạch Wisio với máy tính.
2. Kích đúp vào file **`FLASH_FIRMWARE.cmd`** ở thư mục gốc.
3. Màn hình console xuất hiện danh sách cổng COM:
   - Nhấn **Enter** để chọn cổng COM khuyến nghị (hoặc gõ số thứ tự cổng).
   - Chọn chế độ nạp:
     - **[1] Nạp cập nhật nhanh (App Only - ~10s):** *(Mặc định)* Nạp bản firmware mới nhất, giữ nguyên Wi-Fi đã cấu hình và bộ nhớ tranh ảnh/âm thanh.
     - **[2] Nạp toàn bộ (Full Flash - ~30s):** Nạp sạch sẽ từ đầu gồm bootloader, phân vùng, assets và firmware (khuyên dùng khi bo mới xuất xưởng).
4. Chờ thanh phần trăm chạy đến `100% (Hash of data verified.)`. Robot sẽ tự động khởi động lại!

> [!TIP]
> **Nếu máy tính không nhận cổng hoặc báo lỗi kết nối:**
> - Nhấn giữ nút **BOOT** trên bo mạch, bấm nút **RESET** một lần, rồi thả nút **BOOT**.
> - Đảm bảo đã đóng mọi cửa sổ Serial Monitor (như trên Arduino IDE hoặc VS Code).
> - Sau đó chạy lại `FLASH_FIRMWARE.cmd`.

### 👉 Cách 2: Tự Biên Dịch Từ Mã Nguồn (Dành cho Dev Firmware)
1. Cài đặt **ESP-IDF v5.5.x** hoặc **v6.0.2**.
2. Mở thư mục `firmware/` trong VS Code hoặc Terminal ESP-IDF.
3. Chạy lệnh:
   ```powershell
   python scripts/build.py freenove-esp32s3-display-2.8-lcd
   idf.py -p COMx flash
   ```

---

## 📶 4. CẤU HÌNH MẠNG WI-FI CHO ROBOT (PORTAL SIÊU CUTE)

1. Khi bật nguồn lần đầu (hoặc khi chưa lưu Wi-Fi), robot sẽ phát ra mạng Wi-Fi cấu hình:
   ```text
   Wisio-Setup (hoặc EchoCore-WiFi)
   ```
2. Mở điện thoại hoặc laptop, kết nối vào mạng Wi-Fi trên.
3. Trình duyệt sẽ tự động mở trang cấu hình giao diện chú thỏ Wisio dễ thương *(nếu không tự mở, hãy gõ địa chỉ `http://192.168.4.1`)*:
   - **Bước 1:** Chọn tên Wi-Fi nhà bạn từ danh sách quét sẵn (có vạch sóng trực quan).
   - **Bước 2:** Điền mật khẩu Wi-Fi (có mắt bật/tắt hiển thị mật khẩu).
   - **Bước 3:** Điền email ba mẹ để nhận báo cáo học tập định kỳ và cảnh báo an toàn bảo vệ bé.
4. Bấm nút **Kết Nối Wisio! 🚀** $\rightarrow$ Robot sẽ lưu vào bộ nhớ Flash và kết nối mạng ngay lập tức.

---

## 🚀 5. THIẾT LẬP & KHỞI CHẠY BRIDGE SERVER

Bridge Server đóng vai trò não bộ, chuyển đổi âm thanh thời gian thực giữa Robot Wisio và Google Gemini AI.

### Điều kiện tiên quyết:
- Máy tính chạy Windows 10/11 có kết nối **cùng mạng Wi-Fi** với Robot Wisio.
- Máy tính đã cài sẵn **Python** (phiên bản từ 3.11 đến 3.14). Nếu chưa có, tải tại [python.org](https://www.python.org/downloads/) *(nhớ tích chọn "Add python.exe to PATH")*.
- Một mã **Google Gemini API Key** miễn phí từ [Google AI Studio](https://aistudio.google.com/app/apikey).

### Các bước khởi động:
1. Kích đúp vào file **`START_BRIDGE.cmd`** tại thư mục gốc.
2. Nếu là lần đầu chạy:
   - Script sẽ tự động tạo môi trường ảo Python `.venv` và tải các thư viện cần thiết (`websockets`, `yt-dlp`, `imageio-ffmpeg`, `pillow`...).
   - Bạn chỉ cần dán mã **Gemini API Key** khi cửa sổ nhắc hỏi rồi nhấn **Enter**.
   - *(Hoặc bạn có thể tạo sẵn file `.env` trong thư mục `bridge/` với nội dung `GEMINI_API_KEY=AIzaSy...`)*.
3. Khi Server sẵn sàng, màn hình sẽ thông báo:
   ```text
   Gemini API key verified
   OTA URL: http://<IP_MÁY_TÍNH>:8003/xiaozhi/ota/
   Xiaozhi WebSocket: ws://<IP_MÁY_TÍNH>:8000/xiaozhi/v1/
   Keep this window open while using Freenove.
   ```
4. Bật công tắc Robot Wisio lên: Trong vòng 2-3 giây, màn hình Console sẽ hiện:
   ```text
   Wisio connected; protocol v1
   Gemini Live connected (gemini-3.8-live; voice: Zephyr)
   ```
   Robot Wisio sẽ cất giọng chú thỏ chào bé bằng tiếng Việt thân thương!

---

## 🌟 6. TRẢI NGHIỆM CÁC TÍNH NĂNG NỔI BẬT

### 🎵 1. Phát Nhạc Thông Minh & Giao Diện Player Hiện Đại (Music Player V2):
- **Câu lệnh mẫu:**
  - *"Wisio ơi, mở bài Nơi này có anh đi!"*
  - *"Bật bài Baby Shark vui nhộn nha!"*
  - *"Mở bài Chú voi con ở Bản Đôn đi Wisio!"*
- **Trải nghiệm mới:**
  - **Thông báo ngay lập tức:** Wisio nhận diện bài hát và cất giọng thông báo chuẩn xác: *"Wisio tìm thấy bài [Tên bài hát] rồi nè, chúng mình cùng nghe nhé!"*.
  - **Màn hình LCD sang trọng:** Hiển thị trọn vẹn **ảnh bìa Thumbnail** của bài hát.
  - **Không còn lỗi mất chữ tiếng Việt:** Tiêu đề bài hát hiển thị sạch sẽ, chuẩn chữ hoa/thường, không bao giờ bị nuốt chữ hay lỗi font.
  - **Thanh tiến trình đồng màu thông minh:** Vạch tiến trình chạy mượt mà sát mép dưới, **tự động đổi màu theo màu chủ đạo của ảnh bìa**.
  - **Thời gian to, rõ nét ở giữa:** Hiển thị trực quan thời lượng phát $\mathbf{00:16\ /\ 04:28}$.
  - **Dừng nhạc linh hoạt:** Bé có thể ra lệnh *"Wisio dừng nhạc lại"*, hoặc chạm vào màn hình cảm ứng, hoặc bấm nút BOOT để tạm dừng.

### 🎨 2. Thẻ Học Từ Vựng Trực Quan (Tự Động Minh Họa Tranh Ảnh):
- Khi bé học tiếng Anh hoặc hỏi về một sự vật:
  - *"Con voi tiếng Anh là gì vậy Wisio?"*
  - *"Dạy bé từ quả táo đi!"*
  - *"Con hổ, máy bay, xe cứu hỏa đọc sao?"*
- **Trải nghiệm:** Wisio phát âm chuẩn bản ngữ, hướng dẫn bé đánh vần, đồng thời **màn hình LCD lập tức hiện bức ảnh minh họa sắc nét** giúp bé ghi nhớ sâu bằng thị giác.

### 🧠 3. Ghi Nhớ Cá Nhân Hóa & Cảnh Báo An Toàn:
- **Ghi nhớ sở thích:** *"Bé tên là An, bé 5 tuổi, bé thích màu vàng!"* $\rightarrow$ Wisio tự lưu lại và ngày mai sẽ gọi đúng tên bé, nhắc về đồ chơi màu vàng bé thích.
- **Hộp thư an toàn phụ huynh:** Khi bé có biểu hiện lo lắng hoặc nhắc đến các tình huống nguy hiểm, hệ thống sẽ tự động gửi email cảnh báo ấm áp đến hòm thư của ba mẹ.

---

## ❓ 7. XỬ LÝ SỰ CỐ THƯỜNG GẶP (FAQ & TROUBLESHOOTING)

| Vấn Đề | Nguyên Nhân | Cách Xử Lý |
| :--- | :--- | :--- |
| **Không mở được cổng COM khi nạp** | Có phần mềm khác đang giữ cổng (VS Code Serial Monitor, PuTTY...) | Đóng tất cả terminal Serial Monitor, rút cáp USB ra cắm lại và chạy lại `FLASH_FIRMWARE.cmd`. |
| **Lỗi "Brownout detector was triggered"** | Cáp USB quá dài, chất lượng kém hoặc cổng USB máy tính bị sụt nguồn | Đổi sang cáp Type-C ngắn có chống nhiễu, cắm vào cổng USB 3.0 (màu xanh) phía sau thùng máy hoặc dùng nguồn phụ 5V-2A. |
| **Robot không kết nối được tới Bridge** | Máy tính và robot đang bắt 2 mạng Wi-Fi khác nhau hoặc Firewall chặn | Đảm bảo cả hai kết nối cùng một tên Wi-Fi (băng tần 2.4GHz). Bật cho phép Python trong Windows Defender Firewall (Private Network). |
| **Muốn đổi sang mạng Wi-Fi khác** | Robot đang lưu cấu hình Wi-Fi cũ | Nhấn giữ nút **BOOT** trên bo mạch trong 5 giây cho đến khi robot phát lại Wi-Fi `Wisio-Setup`. |
| **Báo lỗi "API Key not valid"** | Nhập sai mã Gemini API Key | Kiểm tra và copy lại API Key từ Google AI Studio, dán lại vào console hoặc cập nhật trong file `bridge/.env`. |

---

Chúc toàn bộ đội ngũ và các bé có những giờ phút học tập, giải trí tràn đầy niềm vui cùng **Robot AI Wisio**! 🚀✨
