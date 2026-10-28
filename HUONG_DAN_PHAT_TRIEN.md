# Hướng dẫn phát triển Wisio

Người chỉ sử dụng robot xem [hướng dẫn sử dụng](HUONG_DAN_SU_DUNG.md). Không cần build để dùng `firmware_bin/`.

## Cấu trúc

| Đường dẫn | Vai trò |
| --- | --- |
| `bridge/bridge.py`, `PromptWisio.md` | Gemini Live, hội thoại và prompt giáo viên |
| `bridge/music.py` | Audius/YouTube, giải mã và phát nhạc |
| `bridge/motivational_quotes.py` | Châm ngôn có nguồn |
| `bridge/test_*.py` | Kiểm thử, không cần chạy khi sử dụng bình thường |
| `firmware/main/` | Mã nguồn thiết bị, board, audio, màn hình, giao thức |
| `firmware/main/overrides/` | Override dependency do dự án quản lý |
| `firmware/scripts/` | Build, tạo assets và kiểm thử host |
| `firmware_bin/manifest.json` | Offset, kích thước, SHA-256 và cấu hình bộ binary |
| `VERIFICATION.md` | Phạm vi đã kiểm tra và phần cần thử thật |

Một số module ảnh cũ vẫn là dependency import/compatibility của bridge/test. Chúng không được gọi để hiện ảnh trong hội thoại. Đã bỏ nút/hướng dẫn cấu hình ảnh khỏi gói người dùng; không xóa module đang còn import tùy tiện.

## Build firmware

Đọc `firmware/AGENTS.md` trước khi sửa. Bản Freenove đi kèm đã build bằng **ESP-IDF 5.5.3, ESP-Clang 19.1.2**. Những kết quả tương thích IDF 6/board khác trong tài liệu là lịch sử riêng; không thay SDK/board của bộ binary này.

Trong ESP-IDF Terminal, chuyển vào `firmware/`:

```text
python scripts/build.py freenove-esp32s3-display-2.8-lcd --name freenove-esp32s3-display-2.8-lcd --language vi-VN --wake-word hey-wisio
```

Đặt toolchain theo môi trường ESP-IDF đã cài; binary dự án tên `wisio.bin`. Profile wake tạo đúng model MultiNet5 Q8, ngưỡng 40% và 10 biến thể phát âm. Nếu đổi cấu hình một project đã có, dùng `python scripts/configure_wisio_wake.py --build-dir build`, rồi build/nạp cả assets.

Chọn đúng board trước khi nạp. Giữ nguyên GPIO; không sửa tay `sdkconfig`, build output, component đã tải hoặc header ngôn ngữ sinh tự động. Xem thêm `firmware/docs/custom-board.md` và `firmware/main/audio/README.md`.

## Kiểm thử

Firmware host tests từ thư mục `firmware/`:

```text
python -m unittest discover -s scripts/tests -q
```

Cần C++ compiler chạy được trên host; lỗi `Illegal System DLL Relocation`/WinError 623 là lỗi bộ công cụ Windows, không phải kết quả test logic. Build target và kiểm thử trên board thật vẫn cần thực hiện sau khi đổi audio/protocol.

Bridge: kích hoạt môi trường đã cài ở `bridge/.venv`, chuyển vào `bridge/`, rồi:

```text
python -m unittest test_wake_barge_in test_wake_response test_voice_only test_bridge test_music test_music_atomic_start test_music_audio -q
```

Khi thử nghiệm, đặt `WISIO_MEMORY_FILE` vào file riêng để không ghi vào hồ sơ người dùng. Một số test cũ liên quan ảnh mô tả phiên bản lịch sử; không coi chúng là yêu cầu bật lại ảnh.

## Đóng gói và dữ liệu riêng

Chạy `python verify_package.py` ở thư mục gói để đối chiếu checksum và manifest binary. Gói dùng hằng ngày chỉ chứa runtime/firmware, không chứa build tree, vendor, `.venv`, log, bản thu âm, key hoặc file ký ức. Cài dependencies bằng `SETUP_BRIDGE.cmd`.

Không tự nạp hoặc gửi dữ liệu từ test sang API thật. Kết quả build/mock không chứng minh độ chính xác nhận wake hoặc âm thanh loa thật. Giữ nguyên giấy phép và thông báo bên thứ ba.
