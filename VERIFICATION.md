# Kiểm tra bản Wisio 10/10/2026

- Bridge: **374 tests, OK**, 76.934 giây. Bao gồm prompt/endpoint Wisio, tìm và xác minh ảnh, hủy/prefetch/cache, âm thanh, kết nối và nguồn nhạc Audius/YouTube.
- Firmware: **95 host tests, OK**, 24.468 giây. Các định danh cấu hình Wisio và tương thích cấu hình cũ đã được kiểm tra.
- Bộ build container: **10 tests, OK**, 1.708 giây; đường dẫn artifact dùng `wisio.bin`.
- Smoke test từ thư mục đóng gói: **29 tests, OK**, 9.313 giây; công cụ kiểm tra cài đặt tải được Opus trong gói. Các dependency Python/FFmpeg dùng môi trường kiểm tra hiện có, được cài riêng bằng `setup_bridge.cmd` khi người dùng cài gói.
- Script nạp: **1 test, OK**; không tự mở lại monitor sau khi nạp.
- Firmware Freenove: build bằng ESP-IDF 5.5.3 / ESP-Clang 19.1.2. Tên project trong app description là `wisio`. Binary đã qua kiểm tra kích thước phân vùng; offset/SHA-256 ghi tại `firmware_bin/manifest.json`.
- Nội dung gói và năm binary được kiểm tra SHA-256 bằng `verify_package.py`; ZIP được mở lại và kiểm tra CRC sau khi tạo.
- Giữ nguyên MIT copyright, giấy phép Opus và định danh registry/model bên thứ ba. Không đổi lịch sử Git.
- Không đóng gói key, file DPAPI secret, email cấu hình, `wisio_memory.json`, môi trường `.venv`, bản ghi âm, log hay cache cá nhân.

Đây là xác nhận kiểm tra trên máy và build. Chưa nạp bản đổi tên này lên robot trong lượt làm việc này; chưa xác nhận màn hình, loa, wake word hoặc sạc trên phần cứng thực tế. Các test có mô phỏng không thay thế kiểm tra robot.
