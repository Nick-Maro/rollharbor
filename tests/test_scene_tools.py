"""Movement must update the board, budget and continuity together, only once."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from engine import CampaignError, StateStore
from tools.scene_tools import SceneOps
from test_engine import fixture


class SceneToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dnd-scene-tools-')
        self.root = Path(self.temp.name)
        fixture(self.root)
        self.store = StateStore(self.root)
        state, actor = self.store.choose_character('ranger', 'Ada')
        self.actor = actor
        flags = {'tactical_scene': {'id':'test_scene','location_id':state['location_id'],
                    'grid':{'columns':10,'rows':10,'cell_m':1.5,'confirmed':True},
                    'tokens':[{'id':actor['id'],'entity_id':actor['id'],'name':'Ada','x':1,'y':1,'confirmed':True},
                              {'id':'guard','entity_id':'guard','name':'Guardia','x':4,'y':1,'confirmed':True}]},
                 'table_scene':{'location_id':state['location_id'],'distances':[{'a':actor['id'],'b':'guard','metres':4.5}]}}
        state, _ = self.store.commit({'flags':flags,'combat':{'active':True,'round':1,'turn_index':0,'participants':[
            {'id':actor['id'],'name':'Ada','initiative':20,'hp':actor['hp'],'max_hp':actor['max_hp'],'ac':actor['ac'],'conditions':[]},
            {'id':'guard','name':'Guardia','initiative':10,'conditions':[]}]}},state['revision'])
        self.private={'creatures':[{'id':'guard','name':'Private name','hp':10,'max_hp':10,'ac':14}],
                      'turn_usage':{'actor_id':actor['id'],'action_used':False,'bonus_action_used':False},
                      'positions':{'Ada_Guardia_m':4.5},'pending_reactions':[],'timers':[]}
        self.private_path=self.root/'master/COMBATTIMENTO.json'
        self.private_path.write_text(json.dumps(self.private),encoding='utf-8')
        self.tool=SceneOps(self.root)
        self.plan={'actor':'Ada','x':2,'y':1,'cost_m':1.5,'mode':'walk',
                   'reactions_checked':True,'terrain_checked':True,'obstacles_checked':True}

    def tearDown(self):
        self.temp.cleanup()

    def run_move(self,plan=None,ident='move'):
        return self.tool.move(plan or self.plan,ident,self.store.read()['revision'])

    def test_move_updates_budget_board_and_distances_without_hp_changes(self):
        before=self.store.read()
        result=self.run_move()
        after=self.store.read()
        self.assertEqual(after['party'],before['party'])
        self.assertEqual(after['combat'],before['combat'])
        self.assertEqual(after['flags']['tactical_scene']['tokens'][0]['x'],2)
        self.assertEqual(after['flags']['table_scene']['distances'][0]['metres'],3)
        private=json.loads(self.private_path.read_text())
        self.assertEqual(private['positions']['Ada_Guardia_m'],3)
        self.assertEqual(private['turn_usage']['movement_used_m'],1.5)
        self.assertEqual(result['rolls'],[])
        self.assertIn('timings_ms',result)

    def test_idempotent_retry_does_not_move_or_charge_twice(self):
        revision=self.store.read()['revision']
        self.run_move()
        after=self.store.read()
        replay=self.tool.move(self.plan,'move',revision)
        self.assertTrue(replay['already_applied'])
        self.assertEqual(self.store.read(),after)

    def test_missing_checks_and_insufficient_budget_fail_without_effects(self):
        for change in ({'reactions_checked':False},{'cost_m':.5},{'cost_m':99},{'x':4}):
            with self.subTest(change=change):
                before=self.store.state_path.read_bytes()
                with self.assertRaises(CampaignError): self.run_move({**self.plan,**change})
                self.assertEqual(self.store.state_path.read_bytes(),before)

    def test_dash_uses_action_and_only_adds_its_speed_once(self):
        result=self.run_move({**self.plan,'x':8,'cost_m':10.5,'mode':'dash'})
        private=json.loads(self.private_path.read_text())
        self.assertTrue(private['turn_usage']['action_used'])
        self.assertEqual(private['turn_usage']['action_kind'],'dash')
        self.assertEqual(result['remaining_m'],self.actor['speed']*2-10.5)
        with self.assertRaises(CampaignError): self.run_move({**self.plan,'mode':'dash'},ident='second_dash')

    def test_grapple_blocks_movement_and_private_identity_stays_private(self):
        state=self.store.read()
        character=copy.deepcopy(state['character']); character['conditions']=['Afferrato']
        combat=copy.deepcopy(state['combat']);combat['participants'][0]['conditions']=['Afferrato']
        self.store.commit({'party':[character],'combat':combat},state['revision'])
        with self.assertRaises(CampaignError): self.run_move()
        self.assertNotIn('Private name',json.dumps(self.store.read()))


if __name__=='__main__':
    unittest.main()
