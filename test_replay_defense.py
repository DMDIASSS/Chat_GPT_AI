"""Unit tests for logic which doesn't require the Windows RocketSim install."""
import unittest
from types import SimpleNamespace
import numpy as np
import replay_defense as m


class ReplayDefenseTests(unittest.TestCase):
    def test_prioritizes_high_shot_save_replays(self):
        inp=[dict(path='a',shots=2,saves=1,stats_known=True),
             dict(path='b',shots=4,saves=5,stats_known=True),
             dict(path='c',shots=0,saves=0,stats_known=False),
             dict(path='d',shots=10,saves=1,stats_known=True)]
        self.assertEqual([i['path'] for i in m.rank_replays(inp)],['d','b','a','c'])

    def test_extracts_scores_from_player_stats(self):
        p={'players':[{'stats':{'shots':3,'saves':5}},{'shots':2,'saves':1}]}
        self.assertEqual(m.player_statistics(p),(5,6,True))
        self.assertEqual(m.player_statistics({'players':[{'name':'test'}]}),(0,0,False))

    def test_shot_trajectory_filters_own_goal_wrong_direction(self):
        pos=np.array([0,3500,300])
        self.assertTrue(m.toward_opposing_net(pos,np.array([0,1900,0]),False))
        self.assertFalse(m.toward_opposing_net(pos,np.array([0,-1900,0]),False))
        self.assertFalse(m.toward_opposing_net(pos,np.array([0,1900,0]),True))

    def test_events_identifies_attack_and_defending_team(self):
        class Rows:
            def __init__(self,values):self.loc=self;self.values=values
            def __getitem__(self,key):return self.values[key]
        p=SimpleNamespace(metadata={'players':[{'unique_id':'11','is_orange':False},
                {'unique_id':'22','is_orange':True}]},
            analyzer={'hits':[{'frame_number':14,'player_unique_id':'11','is_shot':True},
                              {'frame_number':50,'player_unique_id':'22','is_shot':True}]},
            ball_df=Rows({14:{'pos_x':0,'pos_y':0,'pos_z':150,'vel_x':0,'vel_y':1200,'vel_z':0},
                          50:{'pos_x':0,'pos_y':1000,'pos_z':150,'vel_x':0,'vel_y':-1500,'vel_z':0}}),
            game_df=Rows({14:{'time':6.0},50:{'time':10.0}}))
        ev=m.events_from_replay(p,12)
        self.assertEqual([x['defender_orange'] for x in ev],[True,False])
        self.assertEqual(len(ev),2)

    def test_tagged_save_belongs_to_the_defender_not_the_shooter(self):
        self.assertTrue(m.is_marked_save({'is_save':True}))
        self.assertFalse(m.is_marked_shot({'is_save':True}))
        self.assertTrue(m.is_marked_shot({'is_shot':True}))

    def test_nearest_timestamp_does_not_reach_into_future(self):
        self.assertEqual(m.latest_index([1,2,3],2.3),1)
        self.assertEqual(m.latest_index([1,2,3],1.1),0)

    def test_sources_only_include_replays(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as folder:
            p=Path(folder);(p/'a.replay').write_bytes(b'x');(p/'b.txt').write_text('x')
            self.assertEqual([x.name for x in m.replay_sources(p)],['a.replay'])


if __name__=='__main__':unittest.main(verbosity=2)
