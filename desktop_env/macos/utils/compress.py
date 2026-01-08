import io
from PIL import Image

def compress_image_data_pillow(image_data, quality=85):
    """
    Compress image data in memory using Pillow.
    Supports PNG (lossless/lossy) and JPEG (lossy).
    
    Args:
        image_data (bytes): Raw image binary data.
        quality (int): 
            - For JPEG: 1-100, 85 is recommended.
            - For PNG: This parameter is ignored; PNG uses optimize=True for lossless optimization by default.
            
    Returns:
        bytes: Compressed binary data.
    """
    try:
        # 1. Convert binary data to a Pillow Image object
        # io.BytesIO wraps bytes into a file-like object
        img_input_buffer = io.BytesIO(image_data)
        img = Image.open(img_input_buffer)
        
        # 2. Prepare an output buffer
        img_output_buffer = io.BytesIO()
        
        # Get image format (e.g., 'PNG', 'JPEG'), default to PNG if unrecognizable
        img_format = img.format if img.format else 'PNG'
        
        # 3. Save the image to the output buffer with optimization enabled
        # optimize=True: Enables extra compression algorithms (effective for both PNG and JPEG)
        # quality=quality: Only effective for JPEG, controls compression quality
        img.save(img_output_buffer, format=img_format, optimize=True, quality=quality)
        
        # 4. Retrieve the compressed bytes
        compressed_data = img_output_buffer.getvalue()
        
        # Print comparison (Optional)
        print(f"[{img_format}] Compress: {len(image_data)/1024:.2f}KB -> {len(compressed_data)/1024:.2f}KB")
        
        return compressed_data

    except Exception as e:
        print(f"Pillow fails to compress, return the original data: {e}")
        return image_data
