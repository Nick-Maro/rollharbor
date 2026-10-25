"""Cartography geometry and disclosure tests, with no game-state mutations."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import importlib.util

if importlib.util.find_spec("shapely") is None:
    raise unittest.SkipTest("Optional map tools require Shapely; core gameplay does not.")

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.dungeon_maps import MapError, _geometry, example_plan, export, render_svg, validate


def fixture():
    return {'id':'private-map-id','title':'PRIVATE_TITLE_CANARY',
            'grid':{'columns':24,'rows':16,'cell_m':1.5},
            'rooms':[{'id':'known','name':'Sala conosciuta','x':1,'y':1,'width':6,'height':5},
                     {'id':'unknown','name':'SECRET_ROOM_NAME','x':14,'y':2,'width':7,'height':5},
                     {'id':'secret','name':'HIDDEN_ROOM_NAME','x':15,'y':10,'width':5,'height':4,'hidden':True}],
            'corridors':[],
            'doors':[{'id':'secret-door','x':17,'y':10,'kind':'secret'}],
            'props':[{'id':'known-table','type':'table','room_id':'known','x':2,'y':3,'width':2,'height':1},
                     {'id':'unseen-prop','type':'altar','room_id':'unknown','x':16,'y':3,'width':2,'height':1}],
            'labels':[{'id':'unknown-label','room_id':'unknown','x':17,'y':3,'text':'UNSEEN_LABEL_CANARY'},
                      {'id':'hidden-label','room_id':'secret','x':17,'y':12,'text':'SECRET_LABEL_CANARY','hidden':True},
                      {'id':'dm-label','room_id':'known','x':3,'y':2,'text':'DM_LABEL_CANARY','dm_only':True}],
            'source':{'note':'SOURCE_CANARY'}}


class DungeonMapsTests(unittest.TestCase):
    def test_player_file_contains_no_private_labels_or_source(self):
        svg,metadata=render_svg(fixture(),audience='players',reveal=['known'])
        ET.fromstring(svg)
        for canary in ('PRIVATE_TITLE_CANARY','SECRET_ROOM_NAME','HIDDEN_ROOM_NAME',
                       'UNSEEN_LABEL_CANARY','SECRET_LABEL_CANARY','DM_LABEL_CANARY','SOURCE_CANARY','private-map-id'):
            self.assertNotIn(canary,svg+json.dumps(metadata))
        self.assertEqual(metadata['visible_floor_area'],30)
        self.assertNotIn('source',metadata)

    def test_changing_unseen_geometry_does_not_change_player_svg(self):
        plan=fixture()
        first=render_svg(plan,audience='players',reveal=['known'])[0]
        plan['rooms'][1].update(x=10,y=8,width=11,height=7,floor='cobblestone')
        plan['labels'][0]['text']='ANOTHER_PRIVATE_LABEL'
        second=render_svg(plan,audience='players',reveal=['known'])[0]
        self.assertEqual(first,second)

    def test_reveal_all_keeps_hidden_rooms_and_secret_doors_private(self):
        plan=fixture()
        _,metadata=render_svg(plan,audience='players',reveal_all=True)
        self.assertEqual(metadata['visible_floor_area'],65)
        svg,_=render_svg(plan,audience='players',reveal_all=True)
        self.assertNotIn('SECRET_LABEL_CANARY',svg)
        _,revealed=render_svg(plan,audience='players',reveal_all=True,reveal_secrets=True)
        self.assertEqual(revealed['visible_floor_area'],85)

    def test_fog_frontier_does_not_create_a_fake_wall(self):
        plan=validate({'grid':{'columns':12,'rows':8,'cell_m':1.5},
                       'rooms':[{'id':'hall','x':1,'y':1,'width':9,'height':6}]})
        visible,_,walls,_=_geometry(plan,'players',set(),False,False,[[2,2],[2,3]])
        self.assertEqual(visible.area,2)
        self.assertTrue(walls.is_empty,'The interior edge of a revealed cell became a wall.')

    def test_empty_disclosure_is_blank_and_not_a_full_map(self):
        svg,metadata=render_svg(fixture(),audience='players')
        self.assertEqual(metadata['visible_floor_area'],0)
        self.assertNotIn('SECRET',svg)
        ET.fromstring(svg)

    def test_open_town_has_paving_without_perimeter_walls(self):
        plan={'style':'town','grid':{'columns':10,'rows':10,'cell_m':1.5},
              'rooms':[{'id':'street','x':0,'y':0,'width':10,'height':10,'open':True,'floor':'cobblestone'}]}
        svg,metadata=render_svg(plan,audience='players',reveal_all=True)
        self.assertIn('viewBox="0 0 10 10"',svg)
        self.assertNotIn('stroke-width=".12"',svg)
        self.assertEqual(metadata['visible_floor_area'],100)

    def test_invalid_secret_flags_and_dimensions_are_rejected(self):
        plan=fixture();plan['rooms'][0]['hidden']='false'
        with self.assertRaises(MapError):render_svg(plan,audience='players',reveal_all=True)
        plan=fixture();plan['grid']['columns']=1000
        with self.assertRaises(MapError):render_svg(plan)
        plan=fixture();plan['rooms'][0]['width']=float('nan')
        with self.assertRaises(MapError):render_svg(plan)

    def test_unknown_revelation_id_is_rejected(self):
        with self.assertRaisesRegex(MapError,'ID da rivelare'):
            render_svg(fixture(),audience='players',reveal=['does-not-exist'])

    def test_omitted_prop_warns_only_in_private_metadata(self):
        plan=fixture()
        plan['props'].append({'id':'missing-bridge','type':'bridge','x':0,'y':0,'width':8,'height':2,'rotation':45})
        _,dm=render_svg(plan,audience='dm')
        self.assertTrue(any(warning['id']=='missing-bridge' for warning in dm['warnings']))
        _,public=render_svg(plan,audience='players',reveal_all=True)
        self.assertNotIn('warnings',public)

    def test_local_tool_blocks_private_export_under_web(self):
        target=ROOT/'web'/'assets'/'should-never-exist-dm-map'
        with self.assertRaisesRegex(MapError,'dentro web'):
            export(fixture(),target,audience='dm')
        self.assertFalse(target.with_suffix('.svg').exists())

    def test_svg_labels_are_escaped_and_source_stays_private(self):
        plan=fixture()
        plan['labels'].append({'id':'text','x':3,'y':4,'text':'<script>alert("x")</script>'})
        svg,_=render_svg(plan,audience='players',reveal=['known'])
        root=ET.fromstring(svg)
        self.assertFalse(root.findall('.//{http://www.w3.org/2000/svg}script'))
        self.assertIn('&lt;script&gt;',svg)

    def test_large_curated_example_and_100_by_100_svg(self):
        plan=example_plan()
        svg,metadata=render_svg(plan,audience='players',reveal_all=True)
        self.assertEqual(metadata['width_px'],5120)
        self.assertEqual(metadata['height_px'],3840)
        self.assertGreater(len(plan['rooms']),15)
        ET.fromstring(svg)
        self.assertEqual(svg,render_svg(plan,audience='players',reveal_all=True)[0])
        plan['grid'].update(columns=100,rows=100)
        _,metadata=render_svg(plan,audience='players',reveal_all=True)
        self.assertEqual(metadata['width_px'],6400)

    def test_png_export_has_exact_declared_size(self):
        if importlib.util.find_spec("playwright") is None:
            self.skipTest("PNG export requires optional Playwright and Chromium.")
        with tempfile.TemporaryDirectory(prefix='dnd-map-test-') as temporary:
            result=export(fixture(),Path(temporary)/'map',audience='players',reveal=['known'],png=True,cell_px=16)
            raw=Path(result['png']).read_bytes()
            self.assertEqual(raw[:8],b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II',raw[16:24]),(384,256))
            self.assertEqual(json.loads(Path(result['metadata']).read_text(encoding='utf-8'))['audience'],'players')


if __name__=='__main__':
    unittest.main()
