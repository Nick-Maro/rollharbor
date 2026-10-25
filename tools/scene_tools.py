"""Private DM movement plans: a proposal becomes a position only after adjudication."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import CampaignError, read_json, require
from tools.dnd import emit
from tools.session_ops import SessionOps, entity, ensure_no_pending, public_name


def distance(grid, first, second):
    dx, dy = abs(first['x'] - second['x']), abs(first['y'] - second['y'])
    cells = (dx * dx + dy * dy) ** .5 if grid.get('distance_rule') == 'euclidean' else max(dx, dy)
    return round(cells * grid['cell_m'], 6)


class SceneOps:
    def __init__(self, root):
        from tools.action_toolkit import ToolkitOps
        self.ops = ToolkitOps(root)

    def move(self, plan, request_id, expected_revision):
        started = time.perf_counter()
        require(isinstance(plan, dict) and not set(plan) - {
            'actor', 'x', 'y', 'cost_m', 'mode', 'reactions_checked', 'terrain_checked', 'obstacles_checked'},
            'Piano movimento non valido.')
        for key in ('reactions_checked', 'terrain_checked', 'obstacles_checked'):
            require(plan.get(key) is True, f'Il DM deve prima confermare {key}.')
        mode = plan.get('mode', 'walk')
        require(mode in ('walk', 'dash'), 'Movimento supportato: walk o dash con azione Scatto.')
        cost = plan.get('cost_m')
        require(type(cost) in (int, float) and 0 < cost < 10000, 'cost_m deve essere un costo di movimento positivo già verificato.')

        def apply(state, private):
            ensure_no_pending(state, private)
            actor, _ = entity(state, private, plan.get('actor'))
            combat = state['combat']
            require(combat['active'] and combat['participants'][combat['turn_index']]['id'] == actor['id'],
                    'Serve il turno della creatura; il comando non sposta altri PG o risolve spinte.')
            conditions = {c.casefold() for c in actor.get('conditions', [])}
            blocked = {'afferrato', 'grappled', 'trattenuto', 'restrained', 'paralizzato', 'paralyzed',
                       'stordito', 'stunned', 'pietrificato', 'petrified', 'privo di sensi', 'unconscious', 'morto', 'dead'}
            require(actor.get('hp', 0) > 0 and not blocked.intersection(conditions), 'PF o condizioni impediscono questo movimento.')
            speed = actor.get('speed')
            require(type(speed) in (int, float) and speed > 0, 'Velocità di fonte non registrata: arbitrare prima il movimento.')
            board = state['flags'].get('tactical_scene') or {}
            require(board.get('location_id') == state['location_id'], 'Mappa tattica assente o di un altro luogo.')
            grid = board.get('grid') or {}
            require(grid.get('confirmed') is True and type(grid.get('cell_m')) in (int, float) and grid['cell_m'] > 0,
                    'Serve una griglia con scala confermata dal DM.')
            x, y = plan.get('x'), plan.get('y')
            require(type(x) is int and type(y) is int and 0 <= x < grid.get('columns', 0) and 0 <= y < grid.get('rows', 0),
                    'Destinazione fuori griglia o non intera.')
            tokens = board.get('tokens', [])
            token = next((t for t in tokens if t.get('entity_id', t.get('id')) == actor['id']), None)
            require(token is not None and token.get('confirmed') is True, 'Posizione iniziale non confermata.')
            destination = {'x': x, 'y': y}
            require((x, y) != (token['x'], token['y']), 'La creatura è già nella casella scelta.')
            require(not any(t is not token and t.get('confirmed') is True and t.get('x') == x and t.get('y') == y for t in tokens),
                    'Destinazione occupata: serve arbitraggio specifico prima di terminare lì il movimento.')
            for obstacle in board.get('objects', []):
                if obstacle.get('blocking') is True and obstacle.get('confirmed') is True:
                    require(not (obstacle['x'] <= x < obstacle['x'] + obstacle.get('width', 1)
                                 and obstacle['y'] <= y < obstacle['y'] + obstacle.get('height', 1)),
                            'Destinazione dentro un ostacolo confermato; arrampicarsi richiede un piano specifico.')
            minimum = distance(grid, token, destination)
            if {'a terra', 'prono', 'prone'}.intersection(conditions):
                minimum *= 2  # Crawling; standing up is a separate declared cost.
            require(cost + .000001 >= minimum, 'Il costo dichiarato è minore della distanza minima o del costo di strisciare.')
            usage = copy.deepcopy(private.get('turn_usage') or {})
            require(usage.get('actor_id') == actor['id'], 'Economia del turno non riconciliata.')
            used = usage.get('movement_used_m', 0)
            allowance = usage.get('movement_allowance_m', speed)
            require(type(used) in (int, float) and type(allowance) in (int, float), 'Movimento del turno non valido.')
            if mode == 'dash':
                require(not usage.get('action_used'), 'L’azione è già usata: questo Scatto non è disponibile.')
                allowance += speed
                usage.update(action_used=True, action_kind='dash', martial_arts_eligible=False)
            require(used + cost <= allowance + .000001, 'Movimento insufficiente per il percorso dichiarato.')
            origin = {'x': token['x'], 'y': token['y']}
            token.update(destination)
            usage.update(movement_used_m=used + cost, movement_allowance_m=allowance)
            private['turn_usage'] = usage
            state['flags'].setdefault('combat_context', {})['turn_usage'] = copy.deepcopy(usage)
            private.setdefault('tactical_positions', {})[actor['id']] = destination
            confirmed = [t for t in tokens if t.get('confirmed') is True]
            lookup = {t.get('entity_id', t['id']): t for t in confirmed}
            table = state['flags'].get('table_scene')
            if isinstance(table, dict) and table.get('location_id') == state['location_id']:
                for relation in table.get('distances', []):
                    if actor['id'] in (relation.get('a'), relation.get('b')):
                        first, second = lookup.get(relation.get('a')), lookup.get(relation.get('b'))
                        if first and second:
                            relation['metres'] = distance(grid, first, second)
                            relation.pop('description', None)
            # Keep legacy pairwise notes coherent while the new tactical board is used.
            aliases = {}
            for t in confirmed:
                label = t.get('name', '').split(' ')[0]
                if label:
                    aliases[label] = t
            for key in list(private.get('positions', {})):
                if key.endswith('_m'):
                    pieces = key[:-2].split('_')
                    if len(pieces) == 2 and all(part in aliases for part in pieces):
                        private['positions'][key] = distance(grid, aliases[pieces[0]], aliases[pieces[1]])
            if 'Elia' in aliases and 'other_PCs_within_Elia_m' in private.get('positions', {}):
                pc_ids = {p['id'] for p in state['party']}
                others = [t for t in confirmed if t.get('entity_id', t['id']) in pc_ids and t is not aliases['Elia']]
                if others:
                    private['positions']['other_PCs_within_Elia_m'] = max(distance(grid, aliases['Elia'], t) for t in others)
            message = f"{public_name(state, actor)} si sposta di {cost:g} m di movimento; restano {allowance - used - cost:g} m."
            return {'public': message, 'dm': 'Percorso, terreno e reazioni già arbitrati dal DM; nessun attacco di opportunità o prova risolti automaticamente.',
                    'actor_id': actor['id'], 'from': origin, 'to': destination, 'movement_cost_m': cost,
                    'remaining_m': allowance - used - cost, 'rolls': [], 'pending': [],
                    'references': ['SRD 5.1 (2014): Movement and Position; Dash.']}

        result = self.ops.transact('tactical_move', plan, request_id, expected_revision, apply)
        return {**result, 'tool_elapsed_ms': round((time.perf_counter() - started) * 1000, 3)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('command', choices=['move'])
    parser.add_argument('file', type=Path)
    parser.add_argument('--id', required=True)
    parser.add_argument('--expected-revision', required=True, type=int)
    args = parser.parse_args(argv)
    try:
        emit(SceneOps(args.root).move(read_json(args.file), args.id, args.expected_revision), compact=True)
        return 0
    except (CampaignError, OSError, ValueError, TypeError, KeyError) as exc:
        emit({'error': str(exc), 'code': getattr(exc, 'code', 'storage_error')}, error=True, compact=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
