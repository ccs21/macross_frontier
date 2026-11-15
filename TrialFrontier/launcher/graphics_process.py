"""Preserve the game's uncompressed BGRA DDS format without recompression."""
import struct

def encode(original,image):
    height,width=struct.unpack_from('<II',original,12)
    pixel_format=struct.unpack_from('<8I',original,76)
    if (original[:4]!=b'DDS ' or image.size!=(width,height) or
        pixel_format!=(32,65,0,32,0xff0000,0xff00,0xff,0xff000000) or
        len(original)!=128+width*height*4):
        raise ValueError('Unsupported UI DDS layout; original texture retained')
    return original[:128]+image.convert('RGBA').tobytes('raw','BGRA')
