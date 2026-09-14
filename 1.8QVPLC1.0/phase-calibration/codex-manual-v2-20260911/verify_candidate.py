"""Offline independent reference checks, NOT a CODESYS/ST execution or import script."""
from pathlib import Path
import math, unittest, hashlib, json, re
ROOT=Path(__file__).parent

def fit(points, outputs):
    n=len(points)
    mx,my=[sum(p[i] for p in points)/n for i in (0,1)]
    xx=sum((x-mx)**2 for x,y in points); yy=sum((y-my)**2 for x,y in points)
    xy=sum((x-mx)*(y-my) for x,y in points); det=xx*yy-xy*xy
    if n<30 or xx<=1e-12 or yy<=1e-12 or det<=.01*xx*yy: raise ValueError('samples/geometry')
    rows=[]
    for j in (0,1):
        avg=sum(v[j] for v in outputs)/n
        xu=sum((x-mx)*(v[j]-avg) for (x,y),v in zip(points,outputs))
        yu=sum((y-my)*(v[j]-avg) for (x,y),v in zip(points,outputs))
        rows.append(((xu*yy-yu*xy)/det,(yu*xx-xu*xy)/det))
    (aa,ae),(ea,ee)=rows
    if aa*ee-ae*ea<=0: raise ValueError('polarity')
    ga,ge=math.hypot(aa,ea),math.hypot(ae,ee)
    angle=math.degrees(math.atan2(-ea/ga+ae/ge,-aa/ga-ee/ge))
    orth=abs(90-math.degrees(math.acos(max(-1,min(1,(aa*ae+ea*ee)/(ga*ge))))))
    return angle,ga,ge,orth

class Checks(unittest.TestCase):
    def test_both_gain_orders_phase_gain_and_projection(self):
        # Unequal widths/gains; stationary three-point scan; offsets included.
        for order in (1,2):
            for elev in (5,30,60,80):
                for phi in (-179,-90,-35,0,45,90,179):
                    ba,be=.3,.2; ca,ce=2.5,.7; sa,se=8.,13.
                    a=.2*ba/math.cos(math.radians(elev)); e=.2*be
                    mechanical=[(0,0)]*12+[(0,e)]*12+[(a,0)]*12+[(0,0)]*12
                    points=[(x*math.cos(math.radians(elev)),y) for x,y in mechanical]
                    c,s=math.cos(math.radians(phi)),math.sin(math.radians(phi))
                    outputs=[]
                    for x,y in points:
                        if order==1: u,v=-c*sa*ca*x+s*se*ce*y,-s*sa*ca*x-c*se*ce*y
                        else: u,v=ca*(-c*sa*x+s*se*y),ce*(-s*sa*x-c*se*y)
                        u+=.13; v-=.21
                        outputs.append((u/ca,v/ce) if order==2 else (u,v))
                    angle,ga,ge,orth=fit(points,outputs)
                    self.assertAlmostEqual((angle-phi+180)%360-180,0,places=8)
                    self.assertAlmostEqual(orth,0,places=8)
                    if order==2: ga*=ca; ge*=ce
                    fa,fe=(5/ba)/ga,(5/be)/ge
                    self.assertAlmostEqual(sa*ca*fa*.2*ba,1)
                    self.assertAlmostEqual(se*ce*fe*.2*be,1)
                    self.assertAlmostEqual(10**((20*math.log10(ca)+20*math.log10(fa))/20),ca*fa)
    def test_sampling_budget_and_low_rate_rejection(self):
        # Conservative discard: 0.25 seconds for stable+delay, 0.6 second dwell.
        for period, expected in ((.02,True),(.05,False),(.1,False)):
            count=sum(1 for k in range(1,60) if k*.01>=.25 and k%round(period/.01)==0)
            valid=count>=5 and 4*count>=30
            self.assertEqual(valid,expected)
        self.assertAlmostEqual(3*1.1+4*.6,5.7)
    def test_reject_insufficient_and_single_axis(self):
        for pts in ([(0,0)]*40,[(i*.001,0) for i in range(40)],[(0,0),(0,.1),(.1,0)]*5):
            with self.assertRaises(ValueError): fit(pts,[(-x,-y) for x,y in pts])
    def test_reflection_and_orthogonality(self):
        pts=[(0,0),(0,.1),(.1,0)]*12
        with self.assertRaises(ValueError): fit(pts,[(-x,y) for x,y in pts])
        self.assertGreater(fit(pts,[(-x-.3*y,-y) for x,y in pts])[3],3)
    def test_trajectory_peak_bounds(self):
        # Bounds used by candidate for each axis, including diagonal segment.
        velocity=[]; acceleration=[]
        for k in range(10001):
            u=k/10000
            velocity.append(30*u*u*(1-u)**2)
            acceleration.append(abs(60*u-180*u*u+120*u*u*u))
        self.assertLessEqual(max(velocity),1.875+1e-12)
        self.assertLessEqual(max(acceleration),5.774)
    def test_split_sources_and_original_hashes(self):
        for name,digest in json.loads((ROOT/'来源校验.json').read_text(encoding='utf-8')).items():
            self.assertEqual(hashlib.sha256((ROOT.parent/(name+'.st')).read_bytes()).hexdigest(),digest)
            code=(ROOT/(name+'.st')).read_text(encoding='utf-8')
            dec=(ROOT/'复制代码'/(name+'.declaration.txt')).read_text(encoding='utf-8')
            if name.startswith('GVL'): self.assertEqual(code,dec)
            else:
                impl=(ROOT/'复制代码'/(name+'.implementation.txt')).read_text(encoding='utf-8')
                terminal='END_PROGRAM' if name.startswith('PRG') else 'END_FUNCTION_BLOCK'
                self.assertEqual(re.sub(r'\s+','',code),re.sub(r'\s+','',dec+impl+terminal))
        self.assertEqual((ROOT/'FB_PhaseFit.st').read_bytes(),(ROOT.parent/'FB_PhaseFit.st').read_bytes())
    def test_st_configuration_and_stationary_gates(self):
        code=(ROOT/'PRG_PhaseCalibration.st').read_text(encoding='utf-8')
        for token in ('(az-centerAz)*cosEl','stableElapsed>=rxDelay+stableTime','newRx AND sampleTime>=interval','centerCount<5 OR elCount<5 OR azCount<5 OR returnCount<5','NOT configOK','gainOrder=2','fit.lrOrthErrorDeg<=orthLimit'):
            self.assertIn(token,code)
        path=(ROOT/'FB_PhaseTriangle.st').read_text(encoding='utf-8')
        self.assertIn('30: toAz:=azAmplitude; toEl:=0;',path)
        self.assertIn('xCollect:=FALSE; (* stationary samples only *)',path)

if __name__=='__main__': unittest.main(verbosity=2)
