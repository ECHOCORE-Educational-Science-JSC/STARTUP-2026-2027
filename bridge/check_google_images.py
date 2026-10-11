"""Local end-to-end probe: diagnose vision first, then export the exact robot PNG."""
import getpass
import io
import json
import os
from pathlib import Path
import time

import google_image_search
import learning_image


def main() -> int:
    print(google_image_search.configuration_status())
    try:
        if not google_image_search.get_api_key():
            print('Chạy CONFIGURE_GOOGLE_IMAGES.cmd trước. Không gửi key vào chat.')
            return 1
        key = os.getenv('GEMINI_API_KEY', '').strip() or getpass.getpass('Nhập Gemini API key (ẩn): ').strip()
        from PIL import Image, ImageDraw
        image = Image.new('RGB', (320, 240), 'white')
        ImageDraw.Draw(image).ellipse((105, 65, 215, 175), fill='red')
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        learning_image.verify_image_subject(
            buffer.getvalue(), 'one red circle centered on a white background, simple illustration',
            'red circle', key)
        print('[IMAGE CHECK] Gemini đọc ảnh và trả đủ sáu tiêu chí: OK')
        query = input('Mô tả ảnh cần tìm (Enter = nghêu hấp sả trong tô, ảnh chụp): ').strip()
        query = query or 'nghêu hấp sả trong tô, ảnh chụp'
        word = input('Tên chủ thể (Enter = dùng mô tả trên): ').strip() or query
        # Explicit Google mode avoids a silent fallback during this probe.
        os.environ['WISIO_IMAGE_SOURCE'] = 'google'
        started = time.monotonic()
        result = learning_image.prepare_learning_image(query, key, word)
        directory = Path(__file__).with_name('test-tmp')
        directory.mkdir(exist_ok=True)
        path = directory / 'google-image-preview.png'
        path.write_bytes(result['png'])
        record = {k: v for k, v in result.items() if k != 'png'}
        record.update(query=query, word=word, seconds=round(time.monotonic() - started, 3))
        path.with_suffix('.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[IMAGE CHECK] Ảnh đã xác minh, {record["seconds"]} giây. Mở file: {path}')
        print('Kiểm tra ảnh đúng chủ thể, màu, số lượng, kiểu ảnh và còn đủ chủ thể trong khung ngang.')
        return 0
    except (learning_image.LearningImageError, google_image_search.GoogleImageSearchError) as exc:
        print('[IMAGE CHECK] ' + str(exc))
        return 1
    except (KeyboardInterrupt, EOFError):
        print('Đã hủy kiểm tra.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
