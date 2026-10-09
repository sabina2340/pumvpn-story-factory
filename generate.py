#!/usr/bin/env python3
"""Local 9:16 story video batch generator. First invocation downloads Piper/Whisper models."""
import argparse
import json
import math
import random
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def run(args, *, input_text=None):
    print(' $', ' '.join(map(str,args)), flush=True)
    subprocess.run([str(a) for a in args], input=input_text, text=input_text is not None, check=True)

def probe_seconds(path):
    p = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nokey=1:noprint_wrappers=1',str(path)],capture_output=True,text=True,check=True)
    return float(p.stdout.strip())

def escape_ass(value):
    return value.replace('\\','').replace('{','(').replace('}',')').replace('\n',' ')

def ass_time(seconds):
    cs=round(max(0,seconds)*100)
    h, rem=divmod(cs,360000)
    m,rem=divmod(rem,6000)
    s,cc=divmod(rem,100)
    return f'{h}:{m:02}:{s:02}.{cc:02}'

def subtitles_for(audio, text, model):
    from faster_whisper import WhisperModel
    model=model or WhisperModel(CONFIG['whisper_model'],device=CONFIG['whisper_device'],compute_type=CONFIG['whisper_compute_type'])
    segments,_=model.transcribe(str(audio),language='ru',word_timestamps=True,beam_size=3)
    words=[(float(w.start),float(w.end),w.word.strip()) for s in segments for w in (s.words or []) if w.word.strip() and w.start is not None and w.end is not None]
    if not words:
        raise RuntimeError('Whisper did not return word timestamps for audio')
    groups=[]
    cur=[]
    for word in words:
        if cur and (len(cur)>=5 or word[1]-cur[0][0]>2.25 or (len(cur)>=3 and cur[-1][2].endswith(('.','!','?')))):
            groups.append(cur);cur=[]
        cur.append(word)
    if cur:groups.append(cur)
    return [(grp[0][0],grp[-1][1],' '.join(x[2] for x in grp)) for grp in groups],model

def write_ass(path, groups, voice_duration, total_duration, cfg):
    size=int(cfg['subtitle_font_size'])
    # ASS coordinates are 1080x1920. Bottom subtitles stay clear of TikTok UI.
    head=("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\nScaledBorderAndShadow: yes\n"
          "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
          f"Style: Caption,{cfg['font']},{size},&H00FFFFFF,&H0000FFFF,&HDD101018,&H90000000,-1,0,0,0,100,100,1,0,1,5,2,2,100,100,400,1\n"
          f"Style: Brand,{cfg['font']},106,&H0000FFFFFF,&H0000FFFFFF,&HDD101018,&H90000000,-1,0,0,0,100,100,0,0,1,6,3,5,80,80,0,1\n"
          f"Style: Adline,{cfg['font']},43,&H00FFFFFF,&H00FFFFFF,&HCC101018,&H90000000,0,0,0,0,100,100,0,0,1,3,1,5,90,90,0,1\n"
          "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines=[head]
    for start,end,words in groups:
        if end<=start:continue
        lines.append(f'Dialogue: 0,{ass_time(start)},{ass_time(min(end+0.12,voice_duration))},Caption,,0,0,0,,{escape_ass(words)}\n')
    if cfg['advert_enabled']:
        start=max(0,total_duration-cfg['advert_duration'])
        lines.append(f'Dialogue: 1,{ass_time(start)},{ass_time(total_duration)},Brand,,0,0,0,,{escape_ass(cfg["brand"])}\n')
        # ASS position in centre-ish lower area
        lines.append(f'Dialogue: 1,{ass_time(start+0.12)},{ass_time(total_duration)},Adline,,0,0,0,,{{\\pos(540,1110)}}{escape_ass(cfg["brand_line"])}\n')
    path.write_text(''.join(lines),encoding='utf-8-sig')

def ffmpeg_ass_path(path):
    # Resolve absolute paths & escape filter special chars including Windows drive colon.
    return str(path.resolve()).replace('\\','/').replace(':','\\:').replace("'", "\\'").replace(',','\\,').replace('[','\\[').replace(']','\\]')

def render(audio, ass, output, seconds, background, music, cfg):
    w,h,fps=int(cfg['output_width']),int(cfg['output_height']),int(cfg['fps'])
    cmd=['ffmpeg','-hide_banner','-loglevel','warning','-y']
    if background:
        cmd+=['-stream_loop','-1','-i',str(background)]
        base=f'[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},format=yuv420p'
    else:
        cmd+=['-f','lavfi','-i',f'color=c=0x141b2b:s={w}x{h}:r={fps}']
        base='[0:v]noise=alls=12:allf=t+u,format=yuv420p'
    cmd+=['-i',str(audio)]
    if music:cmd+=['-stream_loop','-1','-i',str(music)]
    # Darkening during branding ending + captions burned into video.
    adstart=max(0,seconds-cfg['advert_duration'])
    fade_expr=(f",drawbox=x=0:y=0:w=iw:h=ih:color=black@0.83:t=fill:enable='between(t,{adstart:.3f},{seconds:.3f})'" if cfg['advert_enabled'] else '')
    fc=base+fade_expr+f",ass=filename='{ffmpeg_ass_path(ass)}'[v];"
    if music:
        fc+=f'[1:a]apad=whole_dur={seconds:.3f},atrim=duration={seconds:.3f}[speech];'
        fc+=f'[2:a]volume={float(cfg["background_music_volume"]):.3f},atrim=duration={seconds:.3f}[music];'
        fc+='[speech][music]amix=inputs=2:duration=first:dropout_transition=0[a]'
    else:
        fc+=f'[1:a]apad=whole_dur={seconds:.3f},atrim=duration={seconds:.3f}[a]'
    cmd+=['-filter_complex',fc,'-map','[v]','-map','[a]','-t',f'{seconds:.3f}', '-c:v','libx264','-preset',cfg['preset'],'-crf',str(cfg['crf']),'-pix_fmt','yuv420p','-r',str(fps),'-c:a','aac','-b:a','160k','-movflags','+faststart',str(output)]
    run(cmd)

def has_audio(path):
    result=subprocess.run(['ffprobe','-v','error','-select_streams','a','-show_entries','stream=index','-of','csv=p=0',str(path)],capture_output=True,text=True,check=True)
    return bool(result.stdout.strip())

def insert_midroll(story_video, advert_video, final_video, story_seconds, cfg):
    """Pause the story at halfway, play the supplied ad, resume story/audio/subtitles."""
    w,h,fps=int(cfg['output_width']),int(cfg['output_height']),int(cfg['fps'])
    mid=story_seconds/2
    ad_seconds=float(cfg.get('advert_duration',3))
    # Advert duration can be shorter than requested: repeat final frame and pad sound.
    cmd=['ffmpeg','-hide_banner','-loglevel','warning','-y','-i',str(story_video),'-i',str(advert_video)]
    audio_source='[1:a]'
    if not has_audio(advert_video):
        cmd+=['-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000']
        audio_source='[2:a]'
    filters=[
        f'[0:v]trim=start=0:end={mid:.3f},setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},format=yuv420p[v0]',
        f'[0:a]atrim=start=0:end={mid:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a0]',
        f'[1:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},tpad=stop_mode=clone:stop_duration={ad_seconds:.3f},trim=duration={ad_seconds:.3f},setpts=PTS-STARTPTS,format=yuv420p[v1]',
        f'{audio_source}aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={ad_seconds:.3f},asetpts=PTS-STARTPTS[a1]',
        f'[0:v]trim=start={mid:.3f},setpts=PTS-STARTPTS,scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={fps},format=yuv420p[v2]',
        f'[0:a]atrim=start={mid:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a2]',
        '[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[v][a]'
    ]
    cmd+=['-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-c:v','libx264','-preset',cfg['preset'],'-crf',str(cfg['crf']),'-pix_fmt','yuv420p','-c:a','aac','-b:a','160k','-movflags','+faststart',str(final_video)]
    run(cmd)

def speak(text, wav, cfg):
    provider=cfg.get('tts_provider','edge')
    if provider=='edge':
        mp3=wav.with_suffix('.tts.mp3')
        run([sys.executable,'-m','edge_tts','--voice',cfg.get('edge_voice','ru-RU-SvetlanaNeural'),'--text',text,'--write-media',str(mp3)])
        run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(mp3),'-ar','24000','-ac','1',str(wav)])
        mp3.unlink(missing_ok=True)
    elif provider=='piper':
        run([sys.executable,'-m','piper','--data-dir',str(ROOT/'voices'),'-m',cfg['voice'],'-f',str(wav),'--',text])
    else:
        raise ValueError('tts_provider must be edge or piper')

def choose_assets(folder, extensions):
    if not folder.exists():return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in extensions)

def main():
    global CONFIG
    ap=argparse.ArgumentParser(description='Render 5 Russian story videos locally')
    ap.add_argument('--limit',type=int,default=5)
    ap.add_argument('--start',type=int,default=1,help='1-based first story')
    ap.add_argument('--skip-whisper',action='store_true',help='Fast subtitle timing approximation; Whisper recommended')
    args=ap.parse_args()
    for cmd in ('ffmpeg','ffprobe'):
        if not shutil.which(cmd):sys.exit(f'ERROR: {cmd} not found in PATH')
    CONFIG=json.loads((ROOT/'config.json').read_text(encoding='utf8'))
    if CONFIG['output_width'] !=1080 or CONFIG['output_height']!=1920:
        sys.exit('This MVP requires 1080x1920 because ASS uses that coordinate system')
    stories=json.loads((ROOT/'stories.json').read_text(encoding='utf8'))
    selected=stories[max(0,args.start-1):max(0,args.start-1)+args.limit]
    if not selected:sys.exit('No stories selected')
    outdir=ROOT/'output';outdir.mkdir(exist_ok=True)
    backgrounds=choose_assets(ROOT/'assets/backgrounds',{'.mp4','.mov','.mkv','.webm','.jpg','.jpeg','.png'})
    # Audio/video files are supported; for stills FFmpeg -stream_loop -1 works as well.
    musics=choose_assets(ROOT/'assets/music',{'.mp3','.wav','.m4a','.ogg'})
    advert=ROOT/'assets'/'advert'/'pumvpn.mp4'
    use_midroll=CONFIG.get('advert_enabled',False) and advert.exists()
    if CONFIG.get('advert_enabled',False) and not advert.exists():
        print('WARNING: assets/advert/pumvpn.mp4 missing; using old text-only end card.',flush=True)
    whisper=None
    for i,story in enumerate(selected):
        stem=re.sub(r'[^A-Za-z0-9_-]','_',story['id'])
        wav=outdir/f'{stem}.wav';ass=outdir/f'{stem}.ass';video=outdir/f'{stem}.mp4'
        print(f'\n[{i+1}/{len(selected)}] {story["title"]}',flush=True)
        # Piper CLI documented: python -m piper -m MODEL -f FILE -- TEXT
        speak(story['text'],wav,CONFIG)
        voice_duration=probe_seconds(wav)
        if args.skip_whisper:
            tokens=story['text'].split()
            total_weight=sum(max(1,len(s)) for s in tokens)
            cur=0;groups=[]
            for k in range(0,len(tokens),5):
                chunk=tokens[k:k+5]; start=voice_duration*cur/total_weight
                cur+=sum(max(1,len(s)) for s in chunk)
                groups.append((start,voice_duration*cur/total_weight,' '.join(chunk)))
        else:
            groups,whisper=subtitles_for(wav,story['text'],whisper)
        total=voice_duration+(CONFIG['advert_duration'] if CONFIG['advert_enabled'] and not use_midroll else 0)
        render_config=dict(CONFIG)
        if use_midroll: render_config['advert_enabled']=False
        write_ass(ass,groups,voice_duration,total,render_config)
        bg=backgrounds[i%len(backgrounds)] if backgrounds else None
        music=musics[i%len(musics)] if musics else None
        if use_midroll:
            base=outdir/f'{stem}.story.mp4'
            render(wav,ass,base,voice_duration,bg,music,render_config)
            insert_midroll(base,advert,video,voice_duration,CONFIG)
            base.unlink(missing_ok=True)
        else:
            render(wav,ass,video,total,bg,music,render_config)
        print(f'CREATED {video.name} ({total:.1f}s; bg={bg.name if bg else "generated dark"})',flush=True)
    print('\nDONE:',outdir)

if __name__=='__main__':
    try: main()
    except subprocess.CalledProcessError as e:sys.exit(f'External program failed (exit code {e.returncode}): {e.cmd}')
