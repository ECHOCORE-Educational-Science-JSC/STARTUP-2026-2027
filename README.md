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
├── bridge/                         # Máy chủ trung gian Bridge Python kết nối Gemini Live
│   ├── bridge.py                   # Server chính quản lý luồng WebSocket âm thanh & sự kiện
│   ├── learning_image.py           # Bộ tải, tối ưu ảnh Pillow 320x240 & kiểm duyệt Gemini 2.0
│   ├── music.py                    # Tìm kiếm và phát nhạc trực tiếp trên loa robot
│   ├── guardian_alert.py           # Bộ lọc giám sát an toàn cho bé và gửi email phụ huynh
│   ├── Promptxiaozhi.md            # Bộ kịch bản tính cách & nghiệp vụ giáo dục chuẩn Wisio
│   ├── requirements.txt            # Danh sách thư viện Python cần thiết
│   ├── setup_bridge.cmd            # Script tự động tạo môi trường ảo và cài đặt thư viện
│   └── start_bridge.cmd            # Khởi động server nhanh chỉ bằng 1 cú đúp chuột
│
├── Wisio_Wifi_Portal_Package/      # Gói độc lập tiện gửi kèm hướng dẫn chi tiết
│   ├── 1_GiaoDien_Wifi_Portal/     # Mã nguồn HTML giao diện cấu hình Wi-Fi kẹo ngọt
│   ├── 2_HuongDan_Nap_Firmware/    # Hướng dẫn nạp firmware từng bước
│   └── 3_HuongDan_Chay_Bridge_Server/ # Hướng dẫn chạy máy chủ Bridge
│
├── HUONG_DAN_SU_DUNG.md            # Sổ tay hướng dẫn chi tiết từ A-Z
└── README.md                       # Tài liệu tổng quan này
```

---

## ✨ Các Tính Năng Nổi Bật

### 1. Học Tiếng Anh Trực Quan Với Hình Ảnh Minh Họa 100%
- Khi bé học từ mới hoặc hỏi nghĩa từ vựng (ví dụ: *con mèo*, *quả táo*, *con chó*, *thanh long*...), robot **chủ động gọi lệnh `show_learning_image`** và hiển thị bức ảnh rõ nét tương ứng ngay trên màn hình LCD 2.8".
- Ảnh được nén bằng thư viện đồ họa **Pillow (PIL)** với nền xanh đậm `#07152e` đồng bộ thẩm mỹ, dung lượng tối ưu dưới 100 KB giúp nạp tức thì trong vòng 50ms mà không làm nặng vi điều khiển.
- Kiểm duyệt nội dung nghiêm ngặt bằng **Gemini 2.0 Flash** đảm bảo ảnh an toàn và phù hợp tuyệt đối cho trẻ em.

### 2. Giao Diện Cấu Hình Wi-Fi (Captive Portal) "Cute Vibe"
- Thiết kế bo tròn với bộ font chữ `Quicksand`, `Comfortaa`, `Nunito` thân thiện.
- Các huy hiệu bước học tập 1, 2, 3 dạng viên kẹo pastel nổi bật.
- Nút kết nối 3D Claymorphic bóng bẩy, đàn hồi êm ái khi bấm.
- Nền vũ trụ sao lung linh (Starry Nebula) kết hợp lưới sàn Cyberpunk neon nhẹ nhàng, không gây đơn điệu.
- Đã tinh chỉnh loại bỏ icon thừa, sửa lỗi thanh sóng và khuyết logo.

### 3. Đàm Thoại Giọng Nói Siêu Tốc (Gemini Live Audio)
- Độ trễ phản hồi dưới 1 giây qua giao thức WebSocket Bidi Audio.
- Giọng đọc Zephyr ấm áp, tự nhiên, phát âm tiếng Anh chuẩn bản ngữ và nói tiếng Việt đáng yêu.

### 4. Phát Nhạc & Trí Nhớ Bền Vững
- Phát nhạc thiếu nhi, bài hát học tiếng Anh theo tên yêu cầu.
- Ghi nhớ tên, tuổi, bài hát yêu thích, thói quen của bé qua nhiều lần tắt/bật nguồn.

---

## 🚀 Hướng Dẫn Bắt Đầu Nhanh

### Bước 1: Nạp Firmware Vào Bo Mạch ESP32-S3
1. Mở thư mục `firmware/` trong **VS Code** (đã cài extension **ESP-IDF** v5.5.x hoặc v6.0.x).
2. Kết nối bo mạch vào máy tính qua cáp USB Type-C, chọn đúng cổng COM và Target `ESP32-S3`.
3. Bấm nút **Build, Flash and Monitor** trên thanh trạng thái VS Code (hoặc nhấn `Ctrl + E`, bấm `F`).

### Bước 2: Cấu Hình Wi-Fi Cho Robot
1. Khởi động robot, robot sẽ phát Wi-Fi có tên dạng `Wisio-Setup` hoặc `EchoCore-WiFi`.
2. Dùng điện thoại/máy tính kết nối vào Wi-Fi này, trang cấu hình cực cute sẽ tự động bật lên (hoặc vào `http://192.168.4.1`).
3. Chọn Wi-Fi gia đình, nhập mật khẩu và email phụ huynh -> Bấm **Kết Nối Wisio!**.

### Bước 3: Chạy Bridge Server Trên Máy Tính
1. Mở thư mục `bridge/`.
2. Kích đúp vào file `start_bridge.cmd` (script sẽ tự tạo môi trường ảo Python và cài đặt thư viện ở lần đầu chạy).
3. Dán **Google Gemini API Key** (lấy miễn phí tại [Google AI Studio](https://aistudio.google.com/app/apikey)) vào màn hình console và nhấn **Enter**.
4. Bật công tắc Robot Wisio. Robot sẽ tự động tìm thấy Bridge Server qua mạng Wi-Fi nội bộ và bắt đầu đàm thoại cùng bé!

---

📖 *Để xem hướng dẫn chi tiết từng bước cho phụ huynh và đồng nghiệp, vui lòng xem [HUONG_DAN_SU_DUNG.md](file:///c:/Users/daole/Documents/Codex/2026-09-18/gi-t-i-mu-n-x-2/temp_remote_repo/HUONG_DAN_SU_DUNG.md).*
