# Wisio firmware

Nguồn ESP-IDF cho robot Wisio. Bản phát hành 28/10/2026 dùng **Freenove ESP32-S3 Display 2.8 LCD — flash 16 MB, PSRAM 8 MB**, ESP-IDF 5.5.3/ESP-Clang 19.1.2.

Người sử dụng chỉ cần bộ binary đã build và ba bước cài/nạp/chạy tại README của gói phát hành. Nguồn này dành cho người sửa firmware; đọc [AGENTS.md](AGENTS.md), [hướng dẫn board](docs/custom-board.md) và [kiến trúc audio](main/audio/README.md) trước khi thay đổi.

```text
python scripts/build.py freenove-esp32s3-display-2.8-lcd --name freenove-esp32s3-display-2.8-lcd --language vi-VN --wake-word hey-wisio
```

Giữ nguyên GPIO, giấy phép [LICENSE](LICENSE), tên dependency/model thật và notice bên thứ ba. Không sửa tay build output hoặc sdkconfig. Khi thay model wake phải nạp app và assets khớp nhau.

Bản hiện tại dùng nguồn USB, không theo dõi pin/sạc; màn hình đảo 180°, đèn xanh khi nghe, vàng khi nói. Đã tắt tăng giọng PCM và tham chiếu loa phần mềm mới sau báo cáo rè/ngắt đoạn; phục hồi đường mic/loa mono. Wake khi đang nói tạm khóa. Build/test host không thay thế thử mic, loa, nhận wake và nguồn điện trên thiết bị thật.
