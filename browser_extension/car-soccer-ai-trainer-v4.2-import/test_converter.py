import io, unittest, zipfile
import torch
from model_import_server import LAYOUT,pack_state,convert

class ConverterTests(unittest.TestCase):
    def state(self):return {i['tensor']:torch.zeros(i['shape']) for i in LAYOUT}
    def checkpoint(self,state):
        stream=io.BytesIO();torch.save({'actor':state},stream);return stream.getvalue()
    def test_full_raw_and_export_zip_share_weights(self):
        state=self.state();expected=pack_state(state)
        self.assertEqual(len(expected),1776128)
        self.assertEqual(convert(self.checkpoint(state)),expected)
        raw=io.BytesIO();torch.save(state,raw);self.assertEqual(convert(raw.getvalue()),expected)
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('Learned/nexto-model.pt',self.checkpoint(state))
            z.writestr('Scripted/nexto-model.pt',self.checkpoint(state))
        self.assertEqual(convert(archive.getvalue()),expected)
    def test_wrong_shape_even_same_element_count_is_rejected(self):
        state=self.state();key=LAYOUT[0]['tensor'];state[key]=state[key].flatten()
        with self.assertRaisesRegex(ValueError,'shape'):pack_state(state)
    def test_nan_rejected(self):
        state=self.state();state[LAYOUT[0]['tensor']].flatten()[0]=float('nan')
        with self.assertRaisesRegex(ValueError,'nonfinite'):pack_state(state)
    def test_distinct_actors_in_zip_require_explicit_selection(self):
        a=self.state();b=self.state();b[LAYOUT[0]['tensor']].flatten()[0]=1
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('a.pt',self.checkpoint(a));z.writestr('b.pt',self.checkpoint(b))
        with self.assertRaisesRegex(ValueError,'different actors'):convert(stream.getvalue())
    def test_incompatible_architecture_rejected(self):
        with self.assertRaisesRegex(ValueError,'architecture'):pack_state({'wrong':torch.zeros(2)})

if __name__=='__main__':
    torch.set_num_threads(2);unittest.main()
