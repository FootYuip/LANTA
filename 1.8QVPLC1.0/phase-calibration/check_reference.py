"""Independent math reference checks; does not compile or execute ST."""
import math
import unittest


def trajectory(radius=.05):
    side = radius / math.sqrt(2)
    vertices = [(0, 0), (0, side), (side, side), (0, 0)]
    points = []
    for start, end in zip(vertices, vertices[1:]):
        for k in range(101):
            u = k / 100
            blend = u**3 * (10 - 15*u + 6*u*u)
            points.append(tuple(a+(b-a)*blend for a, b in zip(start, end)))
    return points


def fit(points, outputs):
    n = len(points)
    mx, my = (sum(p[i] for p in points)/n for i in (0, 1))
    xx = sum((x-mx)**2 for x, y in points)
    yy = sum((y-my)**2 for x, y in points)
    xy = sum((x-mx)*(y-my) for x, y in points)
    det = xx*yy-xy*xy
    if xx <= 1e-12 or yy <= 1e-12 or det <= .01*xx*yy:
        raise ValueError('Degenerate excitation')
    rows = []
    for channel in (0, 1):
        mean = sum(e[channel] for e in outputs)/n
        xu = sum((p[0]-mx)*(e[channel]-mean) for p, e in zip(points, outputs))
        yu = sum((p[1]-my)*(e[channel]-mean) for p, e in zip(points, outputs))
        rows.append(((xu*yy-yu*xy)/det, (yu*xx-xu*xy)/det))
    (aa, ae), (ea, ee) = rows
    if aa*ee-ae*ea <= 0:
        raise ValueError('Reflection cannot be fixed by common rotation')
    ga, ge = math.hypot(aa, ea), math.hypot(ae, ee)
    return math.degrees(math.atan2(-ea/ga+ae/ge, -aa/ga-ee/ge))


class ReferenceTests(unittest.TestCase):
    def test_radius_and_endpoints(self):
        pts = trajectory()
        self.assertLessEqual(max(math.hypot(*p) for p in pts), .05+1e-12)
        self.assertEqual(pts[0], (0, 0))
        self.assertEqual(pts[-1], (0, 0))

    def test_all_quadrants_offsets_unequal_gains(self):
        pts = trajectory()
        for deg in [-179, -100, -90, -30, 0, 40, 90, 140, 179, 180]:
            phi = math.radians(deg)
            c, s = math.cos(phi), math.sin(phi)
            out = [(-12*c*x+7*s*y+.2, -12*s*x-7*c*y-.1) for x, y in pts]
            measured = fit(pts, out)
            self.assertAlmostEqual((measured-deg+180) % 360-180, 0, places=8)
            for direction in [-1, 1]:
                correction = -measured/direction
                final = (350+correction) % 360
                self.assertTrue(0 <= final < 360)
                self.assertAlmostEqual((deg+direction*correction+180) % 360-180, 0, places=8)

    def test_single_axis_rejected(self):
        pts = [(i*.001, 0) for i in range(100)]
        with self.assertRaises(ValueError):
            fit(pts, [(-x, 0) for x, y in pts])

    def test_one_axis_inverted_rejected(self):
        pts = trajectory()
        with self.assertRaises(ValueError):
            fit(pts, [(-x, y) for x, y in pts])


if __name__ == '__main__':
    unittest.main()
