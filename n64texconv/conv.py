import mathutils
import sys, os, re
from PIL import Image
from pprint import pprint
from exoquant import ExoQuant

U8 = 1
U16 = 2
U32 = 4

RGBA16 = 'RGBA16'
RGBA32 = 'RGBA32'
IA4 = 'IA4'
IA8 = 'IA8'
IA16 = 'IA16'
CI4 = 'CI4'
CI8 = 'CI8'
FORMATS = [RGBA16, RGBA32, IA4, IA8, IA16, CI4, CI8]
SIZES = ['U8', 'U16', 'U32']
SIZE_DEF = {
    '1': 'u8',
    '2': 'u16',
    '4': 'u32'
}

clamp32 = lambda x : (int(x) & 0x1F)
scale5_8 = lambda x: (int((x * 0xFF) / 0x1F))
packu8 = lambda vals: ((vals[0] << 4) | vals[1])
u8 = lambda x : (x & 0xFF)

def chunks(n, iterable):
    items = []
    for item in iterable:
        items.append(item)
        if len(items) >= n:
            yield items
            items = []
    if len(items) > 0:
        yield items

def bchunks(n, bytes_arr):
    items = bytearray()
    for item in bytes_arr:
        items.append(item)
        if len(items) >= n:
            yield items
            items = bytearray()
    if len(items) > 0:
        while len(items) < n:
            items.append(0)
        yield items

def get_ia(color):
    intensity = mathutils.Color(color[0:3]).v
    alpha = color[3] if len(color) > 3 else 1
    return (intensity, alpha)

def get_ia4_val(color):
    intensity, alpha = get_ia(color)
    return ((int(intensity * 0x7) & 0x7) << 1) | (1 if alpha > 0.5 else 0)

def pack_ia4(colors):
    for col in colors:
        color2 = col[1] if col[1] else 0
        yield packu8([col[0], color2])

def get_ia8_val(color):
    intensity, alpha = get_ia(color)
    return ((int(intensity * 0xF) & 0xF) << 4) | (int(alpha * 0xF) & 0xF)

def get_ia16_val(color):
    intensity, alpha = get_ia(color)
    return [int(intensity), int(alpha)]

def to5551(t, lst=False):
    r = clamp32((t[0] / 255) * 31)
    g = clamp32((t[1] / 255) * 31)
    b = clamp32((t[2] / 255) * 31)
    a = 0
    if len(t) == 4:
        if t[3] == 255:
            a = 1
    if lst:
        return [r, g, b, a]
    return ((r << 11)) | (g << 6) | (b << 1) | a

def un5551(t):
    return [
        scale5_8(t[0]),
        scale5_8(t[1]),
        scale5_8(t[2]),
        0 if t[3] == 0 else 255
    ]

def to8888(t):
    return (u8(t[0]) << 24) | (u8(t[1]) << 16) | (u8(t[2]) << 8) | u8(t[3])

def to_byte_list(siz, img_data, fmt=False):
    arr = [c for c in bchunks(siz, bytes(img_data))]
    if fmt:
        int_arr = [int.from_bytes(c, 'big') for c in arr]
        if siz is U8:
            return [f'{b:#04X}' for b in int_arr]
        if siz is U16:
            return [f'{b:#06X}' for b in int_arr]
        if siz is U32:
            return [f'{b:#010X}' for b in int_arr]
    return arr

def to_byte_list_dec(func):
    def wrapper(self, *args, **kwargs):
        siz = self.siz
        fmt = bool(kwargs.get('fmt', True))
        return to_byte_list(
            siz,
            func(self, *args, **kwargs),
            fmt=fmt)
    return wrapper


class N64Texture(object):
    siz = None
    def __init__(self, img, siz=U16):
        self._img = img
        self.siz = siz

    def iter_tex(self, func=None):
        width, height = self._img.size
        for y in range(height):
            for x in range(width):
                pixel = self._img.getpixel((x, y))
                yield func(pixel) if func else pixel

    @to_byte_list_dec
    def to_RGBA16(self, fmt=True):
        return [
            val
            for vals in self.iter_tex(to5551)
            for val in [vals >> 8, vals & 0xFF]
        ]

    @to_byte_list_dec
    def to_RGBA32(self, fmt=True):
        return [
            val
            for vals in self.iter_tex()
            for val in vals
        ]
    
    @to_byte_list_dec
    def to_IA4(self, fmt=True):
        return [val for val in pack_ia4(chunks(2, self.iter_tex(get_ia4_val)))]
    
    @to_byte_list_dec
    def to_IA8(self, fmt=True):
        return [val for val in self.iter_tex(get_ia8_val)]
    
    @to_byte_list_dec
    def to_IA16(self, fmt=True):
        return [
            val
            for vals in self.iter_tex(get_ia16_val)
            for val in vals
        ]

    def to_CI(self, col_depth, mode=RGBA16):
        # Compress colors to RGBA16 for a more accurate palette result
        img_data = bytearray([
            v for vals in self.iter_tex()
            for v in un5551(to5551(vals, lst=True))
        ])

        exq = ExoQuant()
        exq.feed(img_data)
        exq.quantize(col_depth)
        rgba32_palette = exq.get_palette(col_depth)

        width, height = self._img.size
        index_data = exq.map_image_ordered(width, height, img_data)

        # Convert the palette colors back to RGBA16
        pal_5551 = [
            to5551([v[0], v[1], v[2], int(v[3])])
            for v in chunks(4, rgba32_palette)]

        pal = to_byte_list(
            U16,
            [   
                val
                for vals in pal_5551
                for val in [vals >> 8, vals & 0xFF]
            ],
            fmt=True
        )
        # CI4 indexes are 2 indexes per byte
        index_data = index_data if col_depth == 0x100 else [packu8(c) for c in chunks(2, index_data)]
        idxs = to_byte_list(U8, index_data, fmt=True)
        return (pal, idxs)
    
    def to_CI4(self, mode=RGBA16):
        return self.to_CI(0x10, mode=mode)

    def to_CI8(self, mode=RGBA16):
        return self.to_CI(0x100, mode=mode)


def to_c_def(var, data, size):
    per_line = 16 / size
    lines = []
    lines.append(f'// size = {len(data)}')
    lines.append(f'{SIZE_DEF[str(size)]} {var}[] = {"{"}')
    for vals in chunks(per_line, data):
        vals_str = ', '.join(vals)
        lines.append(f'\t{vals_str},')
    lines.append('};\n')
    return '\n'.join(lines)
