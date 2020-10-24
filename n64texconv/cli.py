import sys, re
from conv import *

def main():
    n_args = len(sys.argv)
    if n_args > 1:

        img_path = sys.argv[1]
        if img_path.lower() in ['help', '-h', '--help']:
            print('command <img path> <format> <output size>')
            print('\nFormats:')
            print(', '.join(FORMATS))
            print('\nOutput sizes:')
            print(', '.join(SIZES))
            exit(0)

        output_fmt = 'RGBA16'
        if n_args > 2:
            output_fmt = sys.argv[2].upper()
            if output_fmt not in FORMATS:
                print(f'Choose from the following formats:')
                print(', '.join(FORMATS))
                exit(1)

        siz = U8
        if n_args > 3:
            size_arg = sys.argv[3].upper()
            if size_arg not in SIZES:
                print(f'Choose from the following sizes:')
                print(', '.join(SIZES))
                exit(1)
            if output_fmt in [CI4, CI8]:
                print('Output sizes for CI4 and CI8 are fixed')
                print('Pallet data is U16')
                print('Index data is U8')
                input('press enter to continue or ctrl C to exit')
            if size_arg == 'U8':
                siz = U8
            elif size_arg == 'U16':
                siz = U16
            else:
                siz = U32

        print(f'Creating {output_fmt} texture from {img_path}')
        with Image.open(img_path) as img:
            n64_img = N64Texture(img, siz=siz)
            palette, indexes, data = None, None, None

            if output_fmt == CI4:
                palette, indexes = n64_img.to_CI4()
            elif output_fmt == CI8:
                palette, indexes = n64_img.to_CI8()
            elif output_fmt == RGBA16:
                data = n64_img.to_RGBA16()
            elif output_fmt == RGBA32:
                data = n64_img.to_RGBA32()
            elif output_fmt == IA4:
                data = n64_img.to_IA4()
            elif output_fmt == IA8:
                data = n64_img.to_IA8()
            elif output_fmt == IA16:
                data = n64_img.to_IA16()

            tex_name, _ = os.path.splitext(os.path.split(img_path)[-1])
            tex_name = f'{tex_name}_{output_fmt}'
            tex_name = re.sub(' ', '_', tex_name)
            tex_name = re.sub('[^0-9a-zA-Z\_]+', '', tex_name)
            file_data = ''
            if palette:
                pal_C = to_c_def(f'{tex_name}_pal', palette, U16)
                idxs_C = to_c_def(f'{tex_name}_indexes', indexes, U8)
                file_data = '\n'.join([pal_C, idxs_C])
            else:
                file_data = to_c_def(tex_name, data, siz)
            
            output_fn = (f'{tex_name}.inc.c')
            new_fn = input(f'Enter filename or press enter to use {output_fn}: ')
            if new_fn:
                output_fn = new_fn
            with open(output_fn, 'w') as fp:
                fp.write(file_data)
            print(f'Success! Data written to {output_fn}')

if __name__ == "__main__":
    main()
