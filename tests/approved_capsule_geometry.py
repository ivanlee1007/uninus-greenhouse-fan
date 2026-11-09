"""Apply only the approved capsule visual delta to historical geometry hosts.

Frozen original fixture bytes/hashes remain unchanged. Classification and native
control safety are tested against production separately, not by this adapter.
"""
from pathlib import Path
import hashlib

FIXTURE = Path(__file__).parent / 'fixtures/approved-threshold-capsules-v2.html'
APPROVED_SHA256 = '669da04b73891cc3f63170753d6b057a17e78dbaf05cbf25521a514644d55ac8'
RESPONSIVE_RULE = '@container uninus-fan-card (max-width:370px){.layout-2 .live-line strong{padding-inline:1px}.layout-2 .live-line strong::before{margin-right:2px}}@container uninus-fan-card (max-width:330px){.layout-2:not(.readings-right) .live-status{grid-template-columns:1fr;gap:4px}}'


def apply_capsule_geometry(page, card_expression='card'):
    """Use immutable approved styles, never read CSS from the candidate."""
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == APPROVED_SHA256
    text = FIXTURE.read_text(encoding='utf-8')
    css = text.split('const demoStyle=`<style data-demo-design>\n', 1)[1].split('\n</style>`;', 1)[0]
    # Only the fixture adapter's explicit card expression is executable input.
    page.evaluate('''({css,responsive})=>{const c=''' + card_expression + r''';
      const root=c.shadowRoot;root.querySelectorAll('[data-v2-geometry]').forEach(n=>n.remove());
      const style=document.createElement('style');style.dataset.v2Geometry='true';style.textContent=css+'\n.card{container-name:demo-card uninus-fan-card}\n'+responsive;root.append(style);
      // Historical fixtures predate low classes. Add the visual class only on
      // valid, automatic, bound readings; no thresholds or runtime are written.
      for(const article of root.querySelectorAll('.fan-item')){
        const id=article.querySelector('[data-fan]')?.dataset.fan;
        const mode=c.snapshot?.control_mode==='manual'?'manual':c.snapshot?.runtime?.[id]?.mode||'auto';
        for(const [i,line] of [...article.querySelectorAll('.live-line')].entries()){
          const kind=i===0?'temperature':'humidity',entity=c.hass?.states?.[line.title],raw=entity?.state;
          const valid=['number','string'].includes(typeof raw)&&String(raw).trim()!==''&&Number.isFinite(Number(raw))&&entity.attributes?.unit_of_measurement===(i===0?'°C':'%')&&(!entity.attributes?.device_class||entity.attributes.device_class===kind);
          const limit=c.snapshot?.policy?.[kind+'_off'];
          line.classList.toggle('threshold-low',mode==='auto'&&valid&&Number.isFinite(limit)&&Number(raw)<limit);
        }
      }
    }''', {'css':css,'responsive':RESPONSIVE_RULE})
