"""Package the existing Spearmint mark as a multi-resolution Windows icon."""
from pathlib import Path
from PIL import Image, ImageDraw
root=Path(__file__).resolve().parents[1]
canvas=Image.new('RGBA',(256,256))
ImageDraw.Draw(canvas).rounded_rectangle((0,0,255,255),radius=48,fill='#16856b')
mark=Image.open(root/'static/spearmint-logo.png').convert('RGBA')
mark.thumbnail((224,224),Image.Resampling.LANCZOS)
canvas.alpha_composite(mark,((256-mark.width)//2,(256-mark.height)//2))
canvas.save(root/'desktop/spearmint.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
