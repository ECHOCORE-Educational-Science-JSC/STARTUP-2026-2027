# 🌟 DỰ ÁN ROBOT AI WISIO (ECHOCORE STARTUP 2026 - 2027)

> **Robot AI Giáo Dục & Bạn Đồng Hành Thông Minh Dạy Tiếng Anh Giao Tiếp (A1 - B2) Cho Trẻ Em**

Dự án phát triển bởi **ECHOCORE Educational Science JSC**. Robot sử dụng vi điều khiển **ESP32-S3 All-in-One 2.8" LCD** kết hợp trí tuệ nhân tạo **Google Gemini Live Audio**, mang đến trải nghiệm học tiếng Anh "vừa học vừa chơi", minh họa từ vựng bằng hình ảnh trực quan trên màn hình, phát nhạc thiếu nhi và trò chuyện thấu cảm như một người bạn thân thiết của bé.

---

## 📋 Danh Sách Linh Kiện Phần Cứng (BOM)

| Linh Kiện | Mô Tả & Ứng Dụng | Link Tham Khảo |
| :--- | :--- | :--- |
| **Bo mạch ESP32-S3 All-in-One 2.8" LCD** | Mạch tích hợp ESP32-S3 (8MB Flash, 8MB PSRAM), màn hình cảm ứng LCD 2.8", loa, micro | [Shopee](https://s.shopee.vn/4fui1g65qI) |
| **Cảm biến chạm TTP223** | Nút cảm ứng điện dung làm nút đánh thức (Wake button) | [Shopee](https://vn.shp.ee/mf5uxw1e) |
| **Công tắc gạt 5mm** | Bật/tắt nguồn robot | [Shopee](https://s.shopee.vn/5q6fPt8M1R) |
| **Pin Polymer 10.000mAh (JST 2.0)** | Cung cấp nguồn điện di động cho robot hoạt động cả ngày | [Shopee](https://s.shopee.vn/903hBiiUQm) |
| **Jack Type-C Female 4-pin** | Cổng sạc và kết nối nạp firmware tiện lợi | [Shopee](https://vn.shp.ee/EWsXiLnR) |

---

## 📁 Cấu Trúc Mã Nguồn Trong Kho Lưu Trữ

```text
STARTUP-2026-2027/
│
├── FLASH_FIRMWARE.cmd              # Công cụ nạp firmware 1-click thông minh (tự nhận cổng COM)
├── START_BRIDGE.cmd                # Khởi động nhanh Bridge Server 1-click
├── flash_firmware.py               # Script Python tự động nạp firmware qua esptool
│
├── firmware_bin/                   # Các file binary firmware đã biên dịch sẵn (nạp được ngay)
│   ├── xiaozhi.bin                 # Bản build mới nhất (Music Player V2, sửa font chữ tiếng Việt)
│   ├── bootloader.bin              # Bootloader ESP32-S3
│   ├── partition-table.bin         # Bảng phân vùng Flash 16MB
│   ├── ota_data_initial.bin        # Dữ liệu phân vùng OTA
│   └── generated_assets.bin        # Tài nguyên âm thanh & đồ họa nạp vào Flash
│
├── bridge/                         # Máy chủ trung gian Bridge Python kết nối Gemini Live
│   ├── bridge.py                   # Server chính quản lý luồng WebSocket âm thanh & sự kiện
│   ├── learning_image.py           # Bộ tải, tối ưu ảnh Pillow 320x240 & kiểm duyệt Gemini 2.0
│   ├── music.py                    # Tìm kiếm & phát nhạc trực tiếp (chuẩn hóa tên bài, font fallback)
│   ├── guardian_alert.py           # Bộ lọc giám sát an toàn cho bé và gửi email phụ huynh
│   ├── Promptxiaozhi.md            # Bộ kịch bản tính cách & nghiệp vụ giáo dục chuẩn Wisio
│   ├── requirements.txt            # Danh sách thư viện Python cần thiết
│   ├── setup_bridge.cmd            # Script tự động tạo môi trường ảo và cài đặt thư viện
│   └── start_bridge.cmd            # Khởi động server nhanh
│
├── firmware/                       # Toàn bộ mã nguồn Firmware ESP-IDF cho ESP32-S3
│   ├── main/                       # Logic ứng dụng, âm thanh, hiển thị LCD, Wi-Fi portal
│   │   ├── overrides/              # Giao diện cấu hình Wi-Fi cute (wifi_configuration.html)
│   │   ├── display/                # Trình điều khiển màn hình LCD ST7789 & giải mã LVGL/PNG
│   │   ├── audio/                  # Xử lý âm thanh, micro, I2S và Opus codec
│   │   └── protocols/              # Giao thức truyền dữ liệu WebSocket 2 chiều
│   ├── partitions/                 # Bảng phân vùng Flash 8MB / 16MB
│   ├── scripts/                    # Bộ công cụ build tự động và kiểm thử
│   ├── CMakeLists.txt              # Cấu hình biên dịch CMake
│   └── sdkconfig.defaults          # Cấu hình chuẩn ESP-IDF cho bo mạch Freenove 2.8"
│
├── HUONG_DAN_SU_DUNG.md            # Sổ tay hướng dẫn chi tiết từ A-Z cho từng thành viên
└── README.md                       # Tài liệu tổng quan này
```

---

## ✨ Các Tính Năng Nổi Bật

### 1. Học Tiếng Anh Trực Quan Với Hình Ảnh Minh Họa 100%
- Khi bé học từ mới hoặc hỏi nghĩa từ vựng (ví dụ: *con mèo*, *quả táo*, *con chó*, *thanh long*...), robot **chủ động gọi lệnh `show_learning_image`** và hiển thị bức ảnh rõ nét tương ứng ngay trên màn hình LCD 2.8".
- Ảnh được nén bằng thư viện đồ họa **Pillow (PIL)** với nền xanh đậm `#07152e` đồng bộ thẩm mỹ, dung lượng tối ưu dưới 100 KB giúp nạp tức thì trong vòng 50ms mà không làm nặng vi điều khiển.
- Kiểm duyệt nội dung nghiêm ngặt bằng **Gemini 2.0 Flash** đảm bảo ảnh an toàn và phù hợp tuyệt đối cho trẻ em.

### 2. Phát Nhạc Thông Minh & Music Player V2 (Đổi Màu Theo Ảnh Bìa)
- **Chuẩn hóa tên bài hát:** Tự động loại bỏ các tag rác YouTube (`Official MV`, `Audio`, `4K`...), chuẩn hóa tên bài dạng Title Case sạch sẽ.
- **Sửa triệt để lỗi nuốt chữ:** Ánh xạ thông minh các ký tự có dấu thiếu trong font LCD (`Ơ` -> `O`, `Ư` -> `U`, `Đ` -> `D`...), không còn hiện tượng rớt chữ (như `NI NÀY CÓ ANH`).
- **Thanh Player tinh tế:** Thiết kế 1 thanh duy nhất sát đáy màn hình; vạch tiến trình tự động biến đổi màu theo ảnh bìa video; hiển thị to rõ thời gian phát `00:16 / 04:28`.

### 3. Giao Diện Cấu Hình Wi-Fi (Captive Portal) "Cute Vibe"
- Thiết kế bo tròn với bộ font chữ `Quicksand`, `Comfortaa`, `Nunito` thân thiện.
- Các huy hiệu bước học tập 1, 2, 3 dạng viên kẹo pastel nổi bật.
- Nút kết nối 3D Claymorphic bóng bẩy, đàn hồi êm ái khi bấm.

### 4. Đàm Thoại Giọng Nói Siêu Tốc (Gemini Live Audio)
- Độ trễ phản hồi dưới 1 giây qua giao thức WebSocket Bidi Audio.
- Giọng đọc Zephyr ấm áp, tự nhiên, phát âm tiếng Anh chuẩn bản ngữ và nói tiếng Việt đáng yêu.

---

## 🚀 Hướng Dẫn Bắt Đầu Nhanh (Dành Cho Thành Viên Nhóm)

### Bước 1: Nạp Firmware Trong 10 Giây
1. Cắm cáp USB nối bo mạch Wisio với máy tính.
2. Chạy file **`FLASH_FIRMWARE.cmd`** tại thư mục gốc.
3. Chọn cổng COM và chọn chế độ `[1]` để nạp nhanh.

### Bước 2: Cấu Hình Wi-Fi Cho Robot
1. Bật nguồn robot, dùng điện thoại/laptop kết nối vào Wi-Fi `Wisio-Setup`.
2. Trình duyệt tự động mở trang cấu hình -> Chọn Wi-Fi gia đình và bấm **Kết Nối Wisio!**.

### Bước 3: Chạy Bridge Server
1. Chạy file **`START_BRIDGE.cmd`** tại thư mục gốc.
2. Nhập **Gemini API Key** (lấy miễn phí tại [Google AI Studio](https://aistudio.google.com/app/apikey)).
3. Bật công tắc Robot Wisio và bắt đầu trò chuyện, học tiếng Anh cùng bé!

---

📖 *Để xem hướng dẫn chi tiết từng bước cho phụ huynh và đồng nghiệp, vui lòng xem [HUONG_DAN_SU_DUNG.md](file:///c:/Users/daole/Documents/Codex/2026-09-18/gi-t-i-mu-n-x-2/temp_remote_repo/HUONG_DAN_SU_DUNG.md).*
