"""Check that the shipped inspection mesh matches its profile and is closed."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent.parent


class CollisionPreviewTests(unittest.TestCase):
    def test_preview_is_closed_and_matches_its_profile(self):
        metadata=json.loads((HERE/"arena_collision_preview.json").read_text())
        self.assertEqual(metadata["profile_sha256"],hashlib.sha256((HERE/"arena_profile.json").read_bytes()).hexdigest())
        vertices=[];faces=[]
        for line in (HERE/"arena_collision_preview.obj").read_text().splitlines():
            fields=line.split()
            if fields and fields[0]=="v":vertices.append(tuple(map(float,fields[1:])))
            elif fields and fields[0]=="f":faces.append(tuple(map(int,fields[1:])))
        self.assertEqual(len(vertices),metadata["vertices"])
        self.assertEqual(len(faces),metadata["triangles"])
        edges=Counter()
        for a,b,c in faces:
            self.assertTrue(1<=min(a,b,c)<=max(a,b,c)<=len(vertices))
            self.assertEqual(len({a,b,c}),3)
            for x,y in ((a,b),(b,c),(c,a)):edges[tuple(sorted((x,y)))]+=1
        self.assertEqual(set(edges.values()),{2},"Collision preview has an open edge")
        self.assertEqual(len(vertices)-len(edges)+len(faces),2)
        self.assertAlmostEqual(max(v[2] for v in vertices),2048)
        self.assertGreater(max(v[1] for v in vertices),5900,"Net interiors were omitted")
        self.assertIn("not a model input",metadata["purpose"])
