# Wisio — Robot học tiếng Anh

Firmware ESP32-S3 và bridge Gemini Live chạy trên máy tính cho robot Wisio của EchoCore. Bản phân phối ngày 10/10/2026 dành cho board **Freenove ESP32-S3 Display 2.8 LCD, flash 16 MB, PSRAM 8 MB**.

## Cài đặt và sử dụng

1. Giải nén toàn bộ gói, giữ nguyên cấu trúc thư mục. Cài Python 3.11–3.14 trên Windows nếu máy chưa có.
2. Chạy `bridge/setup_bridge.cmd` để cài các thư viện. Lần cài đầu cần Internet; gói không chứa môi trường Python của người phát triển.
3. Chạy `FLASH_FIRMWARE.cmd`, chọn đúng cổng COM và **Full Flash** khi cài bản này lần đầu. Đóng Serial Monitor trước khi nạp. Firmware đã build nằm trong `firmware_bin/`; không cần tự build để sử dụng.
4. Chạy `START_BRIDGE.cmd`, nhập Gemini API key vào ô nhập ẩn. Giữ cửa sổ bridge mở.
5. Kết nối robot và máy tính vào cùng mạng Wi-Fi. Robot tìm bridge qua UDP 8004. Nếu không tìm được, nhập URL được bridge in ra trong trang cấu hình Wi-Fi của robot: `http://<IP-máy-tính>:8003/wisio/ota/`.
6. Muốn bật Google Images: đăng ký SerpApi tại https://serpapi.com/, lấy key rồi chạy `bridge/CONFIGURE_GOOGLE_IMAGES.cmd`. Chạy `bridge/CHECK_GOOGLE_IMAGES.cmd` để kiểm tra. Key được lưu riêng trên máy Windows bằng DPAPI; không gửi key cho người khác.

Bridge dùng HTTP 8003, WebSocket 8000 và UDP 8004. Cho phép Python qua Windows Firewall trên mạng riêng. Hai phiên bản firmware và bridge trong gói phải được dùng cùng nhau; bản này sử dụng namespace `/wisio/`.

## Các phần trong gói

| Thư mục/file | Nội dung |
| --- | --- |
| `bridge/` | Bridge, prompt giáo viên, tìm ảnh, cache/prefetch, âm nhạc và các bài kiểm tra |
| `firmware/` | Mã nguồn ESP-IDF, driver, cấu hình board và kiểm tra trên máy |
| `firmware_bin/` | Năm binary đã build, offset nạp và SHA-256 |
| `FLASH_FIRMWARE.cmd` | Bộ nạp firmware tương tác |
| `START_BRIDGE.cmd` | Khởi động bridge |
| `verify_package.py` | Kiểm tra checksum của toàn bộ gói; không nạp hoặc kết nối robot |
| `VERIFICATION.md` | Kết quả kiểm tra và giới hạn xác nhận |
| `THIRD_PARTY_NOTICES.md` | Nguồn gốc, giấy phép và định danh dependency cần giữ |

## Hành vi hiện tại

- Giáo viên tiếng Anh cho trẻ 6–14 tuổi, điều chỉnh bài học theo trình độ, khích lệ và sửa lỗi ngữ pháp; hồ sơ học tập lưu cục bộ ở bridge.
- Minh họa chủ đề bằng Google Images/SerpApi; Gemini kiểm tra **pixel thực tế** trước khi hiển thị. Có cache và tìm trước ảnh. Không hiển thị kết quả chỉ vì trùng từ khóa. Mạng/quota/xác minh có thể lỗi; robot tiếp tục giải thích bằng lời khi không có ảnh phù hợp.
- Nhạc: **Audius ưu tiên, YouTube dự phòng**. Chỉ báo sẵn sàng sau khi gửi được gói âm thanh đầu tiên; tên bài, bìa và thanh tiến trình được cập nhật cùng màn hình nhạc. Nguồn nhạc vẫn có thể giới hạn vùng hoặc ngừng cung cấp bài.
- Màn hình ngang quay 180°. Đổi âm lượng bằng lời nói.
- Board Freenove hiện **không có GPIO báo sạc được nối/cấu hình**. Không suy đoán “đang sạc” từ điện áp pin để tắt robot. Cắm USB-C không tự chứng minh pin đang sạc; chức năng tự dừng khi sạc cần tín hiệu phần cứng được xác định trước.

Không có key, email phụ huynh, hồ sơ người học, cache ảnh hay bản ghi âm cá nhân trong gói. Chúng được tạo riêng trên máy người dùng khi cấu hình/sử dụng.

## Build từ mã nguồn

Bản binary đi kèm được build bằng ESP-IDF **5.5.3 / ESP-Clang 19.1.2**. Xem `firmware/AGENTS.md`, `firmware/docs/custom-board.md` và `firmware/docs/esp-idf-6-migration.md` khi build board khác. Không nạp binary Freenove vào board khác.

Trong ESP-IDF Terminal, chuyển vào `firmware/`, rồi chạy:

```text
python scripts/build.py freenove-esp32s3-display-2.8-lcd --name freenove-esp32s3-display-2.8-lcd --language vi-VN --wake-word hey-wisio
```

`hey-wisio` dùng bộ nhận diện tùy biến trên ESP32-S3; chất lượng wake word cần kiểm tra trên robot thực tế. File ứng dụng sau build tên `wisio.bin`. Không đổi tên các package registry hoặc model ESP-SR; xem thông báo bên thứ ba.

## Giấy phép

Giữ nguyên giấy phép MIT và thông báo bản quyền của nền tảng firmware tại `LICENSE` và `firmware/LICENSE`. Các thư viện đi kèm có giấy phép riêng; xem `THIRD_PARTY_NOTICES.md` và `bridge/licenses/`.
