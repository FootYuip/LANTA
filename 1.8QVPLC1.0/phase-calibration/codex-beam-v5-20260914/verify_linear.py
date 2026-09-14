"""Offline math/source checks only; not an ST compiler or an import script."""
from pathlib import Path
import math,re,json,hashlib,unittest,importlib.util
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('reference',ROOT.parent/'check_reference.py')
ref=importlib.util.module_from_spec(spec); spec.loader.exec_module(ref)
class Checks(unittest.TestCase):
    def test_linear_examples(self):
        for current,volts in [(1,.25),(3,.75)]:
            self.assertEqual(current/volts,4)
        self.assertEqual(.25*3,.75)
    def test_rotation_unequal_output_gains_projection(self):
        for azgain,elgain in [(1,3),(60,60),(.2,80),(90,.5)]:
            for elev in (10,35.9,60,80):
                cosine=math.cos(math.radians(elev)); radius=.05
                mech=[(0,0)]*12+[(0,radius)]*12+[(radius/cosine,0)]*12+[(0,0)]*12
                pts=[(a*cosine,e) for a,e in mech]
                for phase in (-170,-90,-35,0,47,90,170):
                    c,s=math.cos(math.radians(phase)),math.sin(math.radians(phase))
                    data=[(azgain*(-2*c*x+4*s*y+.01),elgain*(-2*s*x-4*c*y-.02)) for x,y in pts]
                    normalized=[(u/azgain,v/elgain) for u,v in data]
                    got=ref.fit(pts,normalized)
                    self.assertAlmostEqual((got-phase+180)%360-180,0,places=8)
                    # Independent axis column norms of normalized measurements.
                    oa,oe=normalized[0]; ua,ue=normalized[24]; va,ve=normalized[12]
                    sa=math.hypot(ua-oa,ue-oe)/radius
                    se=math.hypot(va-oa,ve-oe)/radius
                    newa=azgain*(5/(sa*azgain)); newe=elgain*(5/(se*elgain))
                    self.assertAlmostEqual(newa*2*.2,1)
                    self.assertAlmostEqual(newe*4*.2,1)
    def test_interface_and_guards(self):
        code=(ROOT/'PRG_PhaseCalibration.st').read_text(encoding='utf-8')
        self.assertNotIn('LN(',code); self.assertNotIn('EXP(',code)
        for token in ('GVL_PhaseCal.iGainUnit:=0','GVL_PhaseCal.iGainOrder:=2','normUa:=ua/gainAz; normUe:=ue/gainEl','gainAz>=1E-6 AND gainEl>=1E-6','lrSuggestedGainAz:=currentGainAz*factorAz','lrSuggestedGainEl:=currentGainEl*factorEl'):
            self.assertIn(token,code)
        g=(ROOT/'GVL_PhaseCalSimple.st').read_text(encoding='utf-8')
        for n in ('lrBeamWidthDeg','lrAzGain','lrElGain','lrPhaseDeg'): self.assertIn(n+' : LREAL',g)
        self.assertNotIn('GainDb',g)
    def test_copy_and_baselines(self):
        code=(ROOT/'PRG_PhaseCalibration.st').read_text(encoding='utf-8')
        dec=(ROOT/'复制代码/PRG_PhaseCalibration.declaration.txt').read_text(encoding='utf-8')
        impl=(ROOT/'复制代码/PRG_PhaseCalibration.implementation.txt').read_text(encoding='utf-8')
        self.assertEqual(re.sub(r'\s+','',code),re.sub(r'\s+','',dec+impl+'END_PROGRAM'))
        self.assertEqual((ROOT/'GVL_PhaseCalSimple.st').read_bytes(),(ROOT/'复制代码/GVL_PhaseCalSimple.declaration.txt').read_bytes())
        for name,digest in json.loads((ROOT/'baseline_sha256.json').read_text()).items():
            self.assertEqual(hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest(),digest)
        cleaned=re.sub(r'\(\*.*?\*\)|"[^"]*"','',code,flags=re.S)
        self.assertEqual(len(re.findall(r'\bIF\b',cleaned)),len(re.findall(r'\bEND_IF\b',cleaned)))
if __name__=='__main__': unittest.main(verbosity=2)
