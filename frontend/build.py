"""Reproducible, dependency-free build for the integrated Electron frontend."""
from pathlib import Path
import shutil
root=Path(__file__).resolve().parent
src=root/'src'; dist=root/'dist'
dist.mkdir(exist_ok=True);(dist/'assets').mkdir(exist_ok=True)
shutil.copy2(src/'index.html',dist/'index.html')
for name in ('main.js','chart.js','style.css','gold.css','market-pulse.css','swing-confluence.css','decision.js','decision.css','terminal.js','terminal.css','dynamic.css','motion.js','research-sources.js','wolf.js','wolf.css','brand.css','formation-panel.js','formation-panel.css'): shutil.copy2(src/name,dist/'assets'/name)
for image in (src/'assets').glob('*.png'): shutil.copy2(image,dist/'assets'/image.name)
print('Built integrated frontend:',dist)
