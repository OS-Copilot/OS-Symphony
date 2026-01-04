import io
from PIL import Image

def compress_image_data_pillow(image_data, quality=85):
    """
    使用 Pillow 在内存中压缩图片数据。
    支持 PNG (无损/有损) 和 JPEG (有损)。
    
    Args:
        image_data (bytes): 原始图片二进制数据
        quality (int): 
            - 对于 JPEG: 1-100，推荐 85。
            - 对于 PNG: 该参数会被忽略，PNG 默认使用 optimize=True 进行无损优化。
            
    Returns:
        bytes: 压缩后的二进制数据
    """
    try:
        # 1. 将二进制数据转换为 Pillow 图片对象
        # io.BytesIO 将 bytes 包装成类似文件的对象
        img_input_buffer = io.BytesIO(image_data)
        img = Image.open(img_input_buffer)
        
        # 2. 准备一个输出缓冲区
        img_output_buffer = io.BytesIO()
        
        # 获取图片格式 (如 'PNG', 'JPEG')，如果无法识别则默认为 PNG
        img_format = img.format if img.format else 'PNG'
        
        # 3. 保存图片到输出缓冲区，开启优化
        # optimize=True: 开启额外的压缩算法 (对 PNG 和 JPEG 都有效)
        # quality=quality: 仅对 JPEG 有效，控制压缩质量
        img.save(img_output_buffer, format=img_format, optimize=True, quality=quality)
        
        # 4. 获取压缩后的 bytes
        compressed_data = img_output_buffer.getvalue()
        
        # 打印对比 (可选)
        print(f"[{img_format}] 压缩: {len(image_data)/1024:.2f}KB -> {len(compressed_data)/1024:.2f}KB")
        
        return compressed_data

    except Exception as e:
        print(f"Pillow 压缩失败，返回原数据: {e}")
        return image_data
