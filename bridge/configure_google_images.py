"""Run locally; validate a hidden SerpApi key before saving Windows DPAPI ciphertext."""
import getpass
import google_image_search


def main() -> int:
    print('Đăng ký tại https://serpapi.com/users/sign_up rồi lấy API key trong dashboard.')
    print('Key SerpApi khác key Gemini. Không gửi key vào chat.')
    try:
        key = getpass.getpass('Nhập SerpApi API key (ẩn): ').strip()
        if not key:
            print('Không nhập key; cấu hình hiện tại được giữ nguyên.')
            return 1
        # One real search checks account access before changing existing configuration.
        candidates = google_image_search.search_images('mèo cam ảnh chụp', key, timeout=8)
        google_image_search.save_api_key(key)
        print(f'Đã lưu key mã hóa cho tài khoản Windows này. Google trả {len(candidates)} ứng viên.')
        print('Khởi động lại start_bridge.cmd. Chạy CHECK_GOOGLE_IMAGES.cmd để kiểm tra Gemini và xem ảnh.')
        return 0
    except google_image_search.GoogleImageSearchError as exc:
        print('Chưa lưu key: ' + str(exc))
        return 1
    except (KeyboardInterrupt, EOFError):
        print('Đã hủy; không thay đổi key.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
