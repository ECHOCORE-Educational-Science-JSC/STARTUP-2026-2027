# Kiểm tra bản 28/10/2026

- Freenove ESP32-S3, ESP-IDF 5.5.3/ESP-Clang 19.1.2: build thành công, app 0x3bded0 byte; phân vùng app 0x3f0000 byte.
- Bản khôi phục âm thanh: tắt tăng giọng PCM và khử vọng phần mềm mới trên Freenove; quay lại mono, khóa wake khi nói/nhạc.
- Đợt trước có 126 test firmware qua; 50 test bridge/hội thoại/wake qua; 39 test nhạc qua. Ba test DSP/wake có log riêng, đã nằm trong bộ firmware, không cộng lặp.
- Test wake qua WebSocket giả lập, ngắt câu đang phát và ngắt lúc hàng đợi drain. Không dùng Gemini API thật trong các test này.
- Assets đã đối chiếu: mn5q8_en, threshold 0.40, 10 cách phát âm. Binary có SHA-256 và offset trong firmware_bin/manifest.json.
- Gói sử dụng được kiểm checksum, ZIP CRC, import dependency, Opus/FFmpeg và đối chiếu với binary đã build. Không chứa key, ký ức, bản ghi âm hoặc môi trường Python riêng.

Chưa nạp hoặc thử mic/loa trên robot thật trong lượt phát hành này. Bản mới đã bị người dùng báo rè/ngắt; bản khôi phục này cần nghe lại trên robot thật, chưa tuyên bố đã hết lỗi; chưa khẳng định nhận wake chính xác 100%. Các board khác không được build lại trong lượt này. Kết quả IDF 6 cũ trong tài liệu kỹ thuật không phải kết quả bản vá này.

## Kiểm tra bản khôi phục âm thanh

Build mới thành công: app 0x3bded0 byte. Lượt host chạy 127 test: 126 qua, một test compiler timeout; chép lại đúng test đó cùng hai test mic/đường loa chạy riêng thì cả 3 qua. Test mới đối chiếu class codec thực: mono 1 kênh, không playback reference, hệ số giọng 1.0 và PCM loa không bị biến đổi. Không coi lần chạy timeout là một lượt full-suite sạch. Bridge không đổi so với nguồn đã chạy 91 test ở bước chuẩn bị đăng. Cần người dùng nạp lại và nghe trên thiết bị để xác nhận hết rè/ngắt.
