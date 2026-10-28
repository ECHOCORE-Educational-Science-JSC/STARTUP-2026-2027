# Wisio — Robot học tiếng Anh

Bản ngày **28/10/2026** cho **Freenove ESP32-S3 Display 2.8 LCD — flash 16 MB, PSRAM 8 MB**. Bridge chạy trên máy tính Windows; robot và máy tính dùng cùng Wi-Fi.

**Đồng nghiệp chỉ cần [tải gói sử dụng](https://github.com/ECHOCORE-Educational-Science-JSC/STARTUP-2026-2027/raw/refs/heads/main/distributions/WISIO_2026-10-28.zip), giải nén rồi làm 3 bước:**

| Thứ tự | File cần chạy | Khi nào |
| --- | --- | --- |
| 1 | `SETUP_BRIDGE.cmd` | Lần đầu trên mỗi máy; cần Python 3.11–3.14 và Internet |
| 2 | `FLASH_FIRMWARE.cmd` | Nạp bản mới; đóng Serial Monitor, chọn đúng COM |
| 3 | `START_BRIDGE.cmd` | Mỗi lần sử dụng; nhập Gemini API key vào ô nhập ẩn |

Sau đó cấu hình Wi-Fi cho robot và giữ cửa sổ bridge mở. Không cần cài ESP-IDF hoặc tự build để dùng binary có sẵn.

- [Hướng dẫn đầy đủ và xử lý lỗi](HUONG_DAN_SU_DUNG.md)
- [Hướng dẫn cho người sửa mã nguồn](HUONG_DAN_PHAT_TRIEN.md)
- [Những gì đã kiểm tra](VERIFICATION.md)

## Bản này có gì?

Trò chuyện và dạy tiếng Anh cho trẻ 6–14 tuổi; hỏi han khi yên lặng, lưu ký ức/tiến bộ cục bộ trên máy tính; phát nhạc từ Audius và YouTube dự phòng. Ảnh minh họa bài học đã tắt; bìa nhạc vẫn giữ.

Bản khôi phục âm thanh đã tắt tăng giọng PCM và khử vọng phần mềm mới sau báo cáo rè/ngắt đoạn. “Hey Wisio” hoạt động khi chờ; tạm khóa wake trong lúc nói/nhạc. Đèn xanh khi nghe, vàng khi nói. Màn hình đảo 180°. Không theo dõi pin hoặc tự tắt màn hình theo trạng thái sạc.

Build và kiểm thử tự động đã qua; **độ chính xác wake và khử vọng vẫn cần thử trên robot thật**. API Gemini và nguồn nhạc có quota/giới hạn riêng; không cam kết miễn phí hoặc luôn có mọi bài hát.

## Dành cho người phát triển

`bridge/` chứa nguồn Python và test; `firmware/` chứa nguồn ESP-IDF; `firmware_bin/` là bộ binary khớp bản này. Gói tải ở trên chỉ chứa phần cần chạy/nạp, không chứa mã firmware, test, gói cũ hoặc môi trường Python của người phát triển.

Giữ giấy phép và nguồn gốc tại [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), `firmware/LICENSE` và `bridge/licenses/`.
