"""Arma el video final con FFmpeg: imágenes con movimiento (Ken Burns),
narración, subtítulos estilo TikTok y música de fondo opcional."""
import random
import subprocess
from pathlib import Path

MOVIMIENTOS = [
    # (zoom, x, y)  — f = total de frames
    ("min(1+0.15*on/{f},1.15)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),          # acercar
    ("1.15-0.15*on/{f}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),                 # alejar
    ("1.12", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(1-on/{f})"),                       # subir
    ("1.12", "(iw-iw/zoom)*on/{f}", "ih/2-(ih/zoom/2)"),                           # derecha
]


def _run(cmd: list[str], cwd: Path | None = None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"FFmpeg falló:\n{' '.join(cmd)}\n{r.stderr[-2000:]}")


def duracion(ruta: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def segmento(imagen: Path, audio: Path, destino: Path, cfg_video: dict, idx: int) -> float:
    """Clip de una escena. Devuelve su duración."""
    w, h, fps = cfg_video["ancho"], cfg_video["alto"], cfg_video["fps"]
    dur = duracion(audio) + 0.25
    frames = int(dur * fps) + 1
    z, x, y = (s.format(f=frames) for s in MOVIMIENTOS[idx % len(MOVIMIENTOS)])
    vf = (
        f"[0:v]scale={w*2}:{h*2}:force_original_aspect_ratio=increase,crop={w*2}:{h*2},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},"
        f"format=yuv420p[v];[1:a]apad,aresample=44100[a]"
    )
    _run([
        "ffmpeg", "-y", "-i", str(imagen), "-i", str(audio), "-filter_complex", vf,
        "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(fps),
        "-c:a", "aac", "-b:a", "160k", "-ac", "2", str(destino),
    ])
    return dur


def _ts(s: float) -> str:
    h, rem = divmod(max(s, 0), 3600)
    m, sec = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{sec:05.2f}"


def subtitulos_ass(palabras: list[tuple[float, float, str]], destino: Path, w: int, h: int, por_linea: int = 3):
    """Subtítulos grandes, en mayúsculas, de pocas palabras a la vez."""
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TT,DejaVu Sans,84,&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,80,80,560,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lineas = []
    for i in range(0, len(palabras), por_linea):
        grupo = palabras[i:i + por_linea]
        ini = grupo[0][0]
        fin = palabras[i + por_linea][0] if i + por_linea < len(palabras) else grupo[-1][1] + 0.3
        texto = " ".join(p[2] for p in grupo).upper().replace("{", "").replace("}", "")
        lineas.append(f"Dialogue: 0,{_ts(ini)},{_ts(fin)},TT,,0,0,0,,{{\\fad(60,0)}}{texto}")
    destino.write_text(cab + "\n".join(lineas) + "\n", encoding="utf-8")


def montar(trabajo: Path, escenas: list[dict], cfg: dict, carpeta_musica: Path) -> Path:
    """escenas: [{'imagen': Path, 'audio': Path, 'palabras': [...]}, ...]"""
    v = cfg["video"]
    segmentos, palabras, t = [], [], 0.0
    for i, e in enumerate(escenas):
        seg = trabajo / f"seg_{i:02d}.mp4"
        dur = segmento(e["imagen"], e["audio"], seg, v, i)
        palabras += [(a + t, b + t, txt) for a, b, txt in e["palabras"]]
        t += dur
        segmentos.append(seg)

    lista = trabajo / "lista.txt"
    lista.write_text("".join(f"file '{s.name}'\n" for s in segmentos))
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "lista.txt", "-c", "copy", "unido.mp4"], cwd=trabajo)

    subtitulos_ass(palabras, trabajo / "subs.ass", v["ancho"], v["alto"])

    musicas = sorted(carpeta_musica.glob("*.mp3")) if carpeta_musica.exists() else []
    final = trabajo / "final.mp4"
    cmd = ["ffmpeg", "-y", "-i", "unido.mp4"]
    if musicas:
        cmd += ["-stream_loop", "-1", "-i", str(random.choice(musicas).resolve())]
        fc = (f"[0:v]ass=subs.ass[v];[1:a]volume={v['volumen_musica']}[m];"
              f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]")
        cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", "ass=subs.ass", "-map", "0:v", "-map", "0:a"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "final.mp4"]
    _run(cmd, cwd=trabajo)
    return final
