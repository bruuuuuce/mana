from pathlib import Path
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from PIL import Image, ImageChops

b = Path('docs/reports/TRANSACTION-01-VIS-01-F01')
r = ET.parse(b / 'before.svg').getroot()
assert len(r.findall('.//{*}clipPath')) == 0
original = next(t for t in r.findall('.//{*}text') if 'RESUME' in (t.text or ''))
metrics = []
for filename, selected in [('before.svg', ['MIXED / RESUME_REQUIRES_COMPLETION']),
                           ('after.svg', ['MIXED / RESUME_REQUIRES_', 'COMPLETION',
                                          'CONDITIONAL / R6 / evidence.json'])]:
    root = ET.parse(b / filename).getroot()
    for t in root.findall('.//{*}text'):
        if t.text not in selected:
            continue
        attrs = dict(t.attrib)
        t.set('x', '10'); t.set('y', '30')
        pngs = []
        for adjusted in [True, False]:
            if not adjusted:
                t.attrib.pop('textLength'); t.attrib.pop('lengthAdjust')
            svg = ET.Element('svg', {'xmlns': 'http://www.w3.org/2000/svg',
                                     'width': '400', 'height': '50'})
            svg.append(t)
            svgfile = Path('/private/tmp/mana-vis-f01/probe.svg')
            pngfile = svgfile.with_suffix('.png')
            ET.ElementTree(svg).write(svgfile)
            subprocess.run(['rsvg-convert', '--background-color=white', str(svgfile),
                            '-o', str(pngfile)], check=True)
            pngs.append(pngfile.read_bytes())
            if adjusted:
                im = Image.open(pngfile).convert('RGB')
                ink = ImageChops.difference(im, Image.new('RGB', im.size, 'white')).getbbox()
        metrics.append({'file': filename, 'text': t.text, 'attributes': attrs,
                        'relativeInkBBoxAtBaseline0': [ink[0]-10, ink[1]-30, ink[2]-10, ink[3]-30],
                        'inkRightInDiagram': float(attrs['x']) + ink[2]-10,
                        'viewportWidth': root.attrib['width'],
                        'textLengthRemovalPixelIdentical': pngs[0] == pngs[1]})
result = {'librsvg': subprocess.check_output(['rsvg-convert', '--version']).decode(),
          'beforeSHA256': hashlib.sha256((b/'before.svg').read_bytes()).hexdigest(),
          'clipPaths': 0, 'textMetrics': metrics,
          'pangoProbeFont': json.loads((b/'pango.json').read_text())['output']['lines'][0]['runs'][0]['font'],
          'pangoProbeLogicalWidth': json.loads((b/'pango.json').read_text())['output']['width']/1024,
          'browserAttempt': 'cua.getBrowser(file:///private/tmp/mana-vis-f01/generated/C/mixed-replacement.svg): No browser is available'}
(b / 'diagnosis.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
