"""Select recorded page intervals by QR and add notebook procedure captions."""
import argparse
import json
import subprocess
from pathlib import Path

import zxingcpp
from PIL import Image, ImageDraw, ImageFont


def index_videos(directory):
    manifest = json.loads((directory / 'recording.json').read_text())
    known = {segment['qr']: segment for segment in manifest['segments']}
    ranges = {}
    for video in manifest['videos']:
        command = ['ffmpeg', '-v', 'error', '-i', str(directory / video['file']),
                   '-vf', 'crop=176:24:iw-176:ih-24,format=gray',
                   '-f', 'rawvideo', '-']
        with subprocess.Popen(command, stdout=subprocess.PIPE) as process:
            frame_index = 0
            previous_token = 0
            while frame := process.stdout.read(176 * 24):
                if len(frame) != 176 * 24:
                    raise ValueError('Incomplete decoded video frame')
                image = Image.frombytes('L', (176, 24), frame)
                for qr in zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.Code128):
                    if len(qr.text) != 20 or not qr.text.isdecimal():
                        continue
                    packed = f'{int(qr.text):016x}'
                    payload = f'{packed[:8]}:{packed[8:12]}:{packed[12:]}'
                    if not payload.startswith(manifest['run'] + ':'):
                        continue
                    segment = known[payload]
                    token = segment['token']
                    if segment['page'] != video['page'] or token < previous_token:
                        raise ValueError(f'Unexpected QR/page order: {segment}, {video}')
                    previous_token = token
                    if token not in ranges:
                        ranges[token] = {'file': video['file'], 'start_frame': frame_index}
                    ranges[token]['end_frame'] = frame_index + 1
                frame_index += 1
            if process.wait() != 0:
                raise RuntimeError(f'Video decoding failed: {video["file"]}')
    missing = [segment['token'] for segment in manifest['segments'] if segment['token'] not in ranges]
    if missing:
        raise ValueError(f'No recorded frames for segment(s): {missing}')
    # Keep navigation frames between the first and last occurrence of one QR.
    index = {'segments': manifest['segments'], 'ranges': ranges}
    (directory / 'video-index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2))
    return manifest, ranges


def ffmpeg(*args):
    subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True)


def encode(*args):
    ffmpeg(*args[:-1], '-an', '-pix_fmt', 'yuv420p', '-c:v', 'libvpx-vp9',
           '-deadline', 'realtime', '-cpu-used', '8', '-crf', '30', '-b:v', '0', args[-1])


def wrap(text, font, width):
    lines = ['']
    for char in text:
        if char == '\n' or font.getlength(lines[-1] + char) > width:
            lines.append('' if char == '\n' else char)
        else:
            lines[-1] += char
    return '\n'.join(lines)


def transition(directory, previous, following, token):
    outgoing = directory / f'fade-out-{token}.png'
    incoming = directory / f'fade-in-{token}.png'
    ffmpeg('-sseof', '-0.04', '-i', previous, '-frames:v', '1', outgoing)
    ffmpeg('-i', following, '-frames:v', '1', incoming)
    output = directory / f'fade-{token}.webm'
    filters = ('[0:v]trim=duration=0.24,setpts=PTS-STARTPTS,fade=t=out:st=0:d=0.24[a];'
               '[1:v]trim=duration=0.24,setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.24[b];'
               '[a][b]concat=n=2:v=1:a=0')
    encode('-loop', '1', '-framerate', '25', '-i', outgoing,
           '-loop', '1', '-framerate', '25', '-i', incoming,
           '-filter_complex', filters, output)
    return output


def render(directory, font_path):
    manifest, ranges = index_videos(directory)
    cells = {cell['index']: cell for cell in manifest['cells']}
    font = ImageFont.truetype(str(font_path), 24)
    if not manifest['segments']:
        raise ValueError('Notebook has no recorded browser interactions')
    title = Image.new('RGB', (1280, 870), '#101820')
    title_font = ImageFont.truetype(str(font_path), 48)
    headings = '\n'.join(dict.fromkeys(cell['scenario'] for cell in manifest['cells']))
    ImageDraw.Draw(title).multiline_text((640, 435), wrap(headings, title_font, 1120),
                                        font=title_font, fill='white', spacing=20,
                                        anchor='mm', align='center')
    title_image = directory / 'title.png'
    title.save(title_image)
    intro = directory / 'title.webm'
    encode('-loop', '1', '-framerate', '25', '-i', title_image, '-t', '2', intro)
    parts = [intro]
    previous_page = None
    for segment in manifest['segments']:
        token = segment['token']
        cell = cells[segment['cell']]
        clip = ranges[token]
        panel = Image.new('RGB', (1280, 150), '#101820')
        text = f"{cell['step']}. {cell['title']}"
        ImageDraw.Draw(panel).multiline_text((20, 10), wrap(text, font, 1240),
                                            font=font, fill='white', spacing=6)
        caption = directory / f'caption-{token}.png'
        panel.save(caption)
        part = directory / f'part-{token}.webm'
        filters = (f"[0:v]trim=start_frame={clip['start_frame']}:end_frame={clip['end_frame']},"
                   'setpts=PTS-STARTPTS,pad=1280:870:0:0:black[v];'
                   '[v][1:v]overlay=0:720:shortest=1')
        encode('-i', directory / clip['file'], '-loop', '1', '-i', caption,
               '-filter_complex', filters, part)
        if previous_page is None or previous_page != segment['page']:
            # Fade still boundary frames; do not obscure any original action frames.
            parts.append(transition(directory, parts[-1], part, token))
        parts.append(part)
        previous_page = segment['page']
    listing = directory / 'video-parts.txt'
    listing.write_text(''.join(f"file '{part.name}'\n" for part in parts))
    output = directory / 'report.webm'
    ffmpeg('-f', 'concat', '-safe', '0', '-i', listing, '-c', 'copy', output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--font', type=Path, required=True)
    args = parser.parse_args()
    render(args.directory, args.font)
