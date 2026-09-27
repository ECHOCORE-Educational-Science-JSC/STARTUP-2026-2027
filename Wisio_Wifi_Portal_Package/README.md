# BỘ TÀI LIỆU & GIAO DIỆN TRỌN GÓI CHO BÉ WISIO (FREENOVE ESP32-S3)

Chào bạn! Đây là bộ gói hoàn chỉnh gồm giao diện Wi-Fi Captive Portal mới nhất cùng toàn bộ hướng dẫn nạp firmware và vận hành Bridge Server AI Gemini Live cho dự án Robot Wisio.

---

## 📁 Cấu Trúc Thư Mục Gói

```text
Wisio_Wifi_Portal_Package/
│
├── 1_GiaoDien_Wifi_Portal/
│   ├── wifi_configuration.html      # File mã nguồn giao diện HTML hoàn chỉnh
│   └── assets/
│       └── wifi_configuration.html  # Bản sao đặt đúng đường dẫn assets
│
├── 2_HuongDan_Nap_Firmware/
│   └── HUONG_DAN_NAP_FIRMWARE.md    # Hướng dẫn chi tiết cách biên dịch & nạp firmware bằng VS Code / CLI
│
├── 3_HuongDan_Chay_Bridge_Server/
│   └── HUONG_DAN_CHAY_BRIDGE.md     # Hướng dẫn chạy máy chủ Bridge Python kết nối Gemini Live AI
│
└── README.md                        # Tài liệu tổng quan này
```

---

## ✨ Điểm Nổi Bật Đã Được Nâng Cấp & Tối Ưu

1. **Giao Diện Wi-Fi Captive Portal Cực Kỳ Dễ Thương (Cute Vibe):**
   - Sử dụng bộ font bo tròn hiện đại, thân thiện trẻ em: `Quicksand`, `Comfortaa`, `Nunito`.
   - Các huy hiệu bước học tập 1, 2, 3 dạng viên thuốc kẹo ngọt nổi bật.
   - Nút kết nối dạng 3D Claymorphic bóng bẩy, bấm êm tay có hiệu ứng đàn hồi.
   - Nền trời sao vũ trụ lấp lánh (Starry Nebula) kết hợp lưới sàn Cyberpunk neon nhẹ nhàng, không gây đơn điệu.
   - Đã loại bỏ hoàn toàn các icon thỏ thừa theo đúng yêu cầu, sửa lỗi khuyết logo và dấu chấm thanh sóng Wi-Fi.

2. **Khắc Phục 100% Lỗi "Không Tải Được Ảnh" Khi Dạy Tiếng Anh:**
   - Hệ thống tự động nhận diện từ khóa tiếng Việt (như *con chó*, *con mèo*, *quả táo*, *thanh long*...) và dịch khớp với từ vựng tiếng Anh tương ứng (*dog*, *cat*, *apple*, *pitaya*).
   - Tự động tìm nguồn ảnh chuẩn giáo dục trên Wikipedia (hỗ trợ cả kho ảnh Wikipedia Tiếng Anh và Tiếng Việt).
   - Tối ưu hóa ảnh tự động bằng thư viện **Pillow (PIL)**: nén ảnh về kích thước chuẩn 320x240, căn giữa trên nền xanh đậm `#07152e` đồng bộ giao diện, kích thước cực nhẹ (dưới 100 KB) giúp nạp tức thì lên màn hình LCD mà không làm tràn bộ nhớ vi điều khiển.
   - Kiểm duyệt hình ảnh an toàn cho trẻ nhỏ bằng mô hình chuẩn **Gemini 2.0 Flash**.

3. **Tương Thích Mọi Bo Mạch Freenove ESP32-S3 Display 2.8" LCD:**
   - Chỉ cần nạp mã nguồn firmware và chạy file `start_bridge.cmd` là robot tự động kết nối và hoạt động trơn tru.

---

## 🚀 Bắt Đầu Nhanh

- **Bước 1:** Đọc file [HUONG_DAN_NAP_FIRMWARE.md](file:///c:/Users/daole/Documents/Codex/2026-09-18/gi-t-i-mu-n-x-2/Wisio_Wifi_Portal_Package/2_HuongDan_Nap_Firmware/HUONG_DAN_NAP_FIRMWARE.md) để nạp code vào bo mạch ESP32-S3.
- **Bước 2:** Kết nối Wi-Fi cho robot qua trang cấu hình cực cute của Wisio.
- **Bước 3:** Đọc file [HUONG_DAN_CHAY_BRIDGE.md](file:///c:/Users/daole/Documents/Codex/2026-09-18/gi-t-i-mu-n-x-2/Wisio_Wifi_Portal_Package/3_HuongDan_Chay_Bridge_Server/HUONG_DAN_CHAY_BRIDGE.md) để khởi chạy máy chủ đàm thoại và dạy học trên máy tính.
